import { initializeTestEnvironment } from "@firebase/rules-unit-testing";
import fc from "fast-check";
import firebase from "firebase/compat/app";
import * as h from "./harness";
import * as m from "./model";

// The rules fuzz (M1-06, P17): random cases (a world seeded with rules off, a caller, a request)
// sent to the emulator and to the reference model (model.ts), which must agree. A case is a
// template's n-th variant (n = 0: its base case, which PLAN 3.1 allows in a minimal world; an
// extension point's once its task adds the row), a few generic tweaks, each of one write, document
// or the caller, so most cases sit next to a rule's boundary, and a random background. A new row
// needs only its template.
const [ALICE, BOB, CAROL, DAN] = ["alice", "bob", "carol", "dan"];
const UIDS = [ALICE, BOB, CAROL, DAN];
// Firestore auto-ids (P3), and ids that are not: 19 and 21 characters, a `_`, a `-`.
const [H1, H2, H3] = ["Kq3ZtW9xLm2RbV7nPc4D", "Pz8YwV2nQs5TxK1mRc7B", "Mx4UvB6tRw9QaZ3nLk2C"];
const HIDS = [H1, H2, H3, H1.slice(1), `${H1}x`, `${H1.slice(1)}_`, `${H1.slice(1)}-`];
const CODE = `${H1}_${"s".repeat(22)}`;
const CODE2 = CODE.replace(H1, H2); // an invite to dan's tombstone in the read world
const CODE3 = `${H1}_${"t".repeat(22)}`; // another of carol's invites, in the join
// The codes of the id and rename tweaks: P3's, and with a secret of 21 or 23 characters or a `.`.
const CODES = [CODE, CODE2, CODE.slice(0, -1), `${CODE}s`, `${CODE.slice(0, -1)}.`];

type Op = m.Write["op"];
type Draft = { world: Map<string, m.Doc>; caller: m.Caller; writes: m.Write[]; read?: m.Request };
const set = (path: string, data: m.Doc): m.Write => ({ op: "set", path, data });
const up = (path: string, data: m.Doc): m.Write => ({ op: "update", path, data });
const del = (path: string): m.Write => ({ op: "delete", path, data: {} });
const draft = (uid: string, world: Record<string, m.Doc>, ...writes: m.Write[]): Draft => ({
    world: new Map(Object.entries(world)),
    caller: { uid, auth: "verified" },
    writes,
});

// bob's live household with his member doc, and carol's; the base docs of a create and a join.
const LIVE = { name: "Home", createdBy: BOB, createdAt: m.T0, ownerUid: BOB, deleted: false };
const MEMBER = { role: "member", displayName: "Name", joinedAt: m.T0 };
const HOME = { [m.household(H1)]: LIVE, [m.member(H1, BOB)]: { ...MEMBER, role: "owner" } };
const CAROLS = { ...HOME, [m.member(H1, CAROL)]: MEMBER };
const NEW: m.Doc = { ...LIVE, createdBy: ALICE, createdAt: m.NOW, ownerUid: ALICE };
const OWNER: m.Doc = { role: "owner", displayName: "Ann", joinedAt: m.NOW };
const LATER = new Date("2999-01-01T00:00:00Z"); // after any request time: an unexpired invite
const [SOON, LATE] = [new Date(Date.now() + 6 * 86_400_000), new Date(Date.now() + 8 * 86_400_000)];
const INVITE = { householdId: H1, householdName: "Home", createdBy: CAROL, expiresAt: LATER };
const ASKED: m.Doc = { ...INVITE, createdAt: m.NOW, expiresAt: SOON }; // carol's invite create
// The invite readers: each user with a verified email, and bob without one.
const UNVERIFIED: m.Caller = { uid: BOB, auth: "unverified" };
const JOINED: m.Doc[] = [{}, {}, {}, {}, { role: "owner" }, { joinedAt: m.T0 }, { color: 1 }];
const READERS = [...UIDS.map((uid): m.Caller => ({ uid, auth: "verified" })), UNVERIFIED];
const points = (householdId: string | null): m.Doc => ({ householdId });
// For reads: bob's household with carol (alice, removed, still names it) and dan's tombstone (his
// member doc not yet cleaned up, M1-95), with an invite to each.
const TOMB = { ...LIVE, ownerUid: DAN, name: "", deleted: true };
const SEEN = {
    ...CAROLS,
    [m.user(CAROL)]: points(H1),
    [m.household(H2)]: TOMB,
    [m.member(H2, DAN)]: { ...MEMBER, role: "owner" },
    [m.user(DAN)]: points(H2),
    [m.user(ALICE)]: points(H1),
    [`invites/${CODE}`]: INVITE,
    [`invites/${CODE2}`]: { ...INVITE, householdId: H2 },
};

// The n-th variant of a document: users doc holding null or an id, member doc of either role,
// household live or a tombstone of any owner.
function variant(path: string, n: number): m.Doc {
    if (path.startsWith("users/")) return { householdId: [null, H1, H2, H3][n % 4] ?? null };
    if (path.includes("/members/")) return { ...MEMBER, role: n % 2 ? "owner" : "member" };
    const tomb = n % 3 === 0;
    return { ...LIVE, ownerUid: UIDS[n % 4] ?? BOB, name: tomb ? "" : "Home", deleted: tomb };
}
// The documents a background may hold, and every get and list a read may make.
const DOCS = [
    ...UIDS.map(m.user),
    ...[H1, H2, H3].flatMap((hid) => [m.household(hid), ...UIDS.map((u) => m.member(hid, u))]),
];
const LISTS = [...[H1, H2, H3].map((hid) => `${m.household(hid)}/members`), "users", "households"];
const READS: m.Request[] = [
    ...[...DOCS, "config/app"].map((path) => ({ op: "get" as const, path })),
    ...LISTS.map((path) => ({ op: "list" as const, path })),
];
// Invite reads: both codes, and lists without a filter, of H1, of carol's and of alice's (removed)
// in H1, of H2 (#280).
const INVITE_READS: m.Request[] = [
    ...[CODE, CODE2].map((code) => ({ op: "get" as const, path: `invites/${code}` })),
    ...Array.of<m.Doc>(
        {},
        { householdId: H1 },
        { householdId: H1, createdBy: CAROL },
        { householdId: H1, createdBy: ALICE },
        { householdId: H2 },
    ).map((where) => ({ op: "list" as const, path: "invites", where })),
];

export const TEMPLATES: Record<string, (n: number) => Draft> = {
    // A read by any user of any document.
    read: (n) => ({ ...draft(UIDS[n % 4] ?? ALICE, SEEN), read: READS[(n >> 2) % READS.length] }),
    "create household": () =>
        draft(
            ALICE,
            { [m.user(ALICE)]: points(null) },
            set(m.household(H2), NEW),
            set(m.member(H2, ALICE), OWNER),
            up(m.user(ALICE), points(H2)),
        ),
    transfer: () =>
        draft(
            BOB,
            CAROLS,
            up(m.household(H1), { ownerUid: CAROL }),
            up(m.member(H1, BOB), { role: "member" }),
            up(m.member(H1, CAROL), { role: "owner" }),
        ),
    "display name": () => draft(CAROL, CAROLS, up(m.member(H1, CAROL), { displayName: "C" })),
    "users doc: set": () =>
        draft(CAROL, { ...CAROLS, [m.user(CAROL)]: points(null) }, up(m.user(CAROL), points(H1))),
    "users doc: clear": () =>
        draft(DAN, { ...HOME, [m.user(DAN)]: points(H1) }, up(m.user(DAN), points(null))),
    "users doc: create": () => draft(BOB, {}, set(m.user(BOB), { householdId: null, name: "B" })),
    "users doc: name": () => draft(CAROL, SEEN, up(m.user(CAROL), { name: "C" })),
    // Each invite reader (n % 5) and each invite read.
    "invite: read": (n) => ({
        ...draft(ALICE, SEEN),
        caller: READERS[n % READERS.length] ?? UNVERIFIED,
        read: INVITE_READS[Math.floor(n / READERS.length) % INVITE_READS.length],
    }),
    // By n % 16: the base case (0, 6 to 15); an expiry after 7 days, now or past (1 to 3); the
    // household a tombstone that keeps its name, so P2 holds (4); alice's own, not a member (5).
    "invite: create": (n) => {
        const v = n % 16;
        const expiresAt = ([SOON, LATE, m.NOW, m.T0] as const)[v] ?? SOON;
        const by = v === 5 ? ALICE : CAROL;
        const world = { ...CAROLS, [m.household(H1)]: { ...LIVE, deleted: v === 4 } };
        return draft(by, world, set(`invites/${CODE}`, { ...ASKED, createdBy: by, expiresAt }));
    },
    // By n % 16, carol's invite deleted by: her (0, 7 to 15); the owner (1); dan, a plain member,
    // once it has expired or before (2, 3); alice, not a member, once expired (4); under a
    // tombstone, carol once expired or the owner (5, 6).
    "invite: delete": (n) => {
        const v = n % 16;
        const invite = { ...INVITE, expiresAt: [2, 4, 5].includes(v) ? m.T0 : LATER };
        const home = { ...LIVE, deleted: v === 5 || v === 6 };
        const dans = { ...MEMBER, viaInvite: CODE }; // he joined through it; it was made again (P3)
        const world = { ...CAROLS, [m.member(H1, DAN)]: dans, [m.household(H1)]: home };
        const uid = [CAROL, BOB, DAN, DAN, ALICE, CAROL, BOB][v] ?? CAROL;
        return draft(uid, { ...world, [`invites/${CODE}`]: invite }, del(`invites/${CODE}`));
    },
    "users doc: delete": () => draft(ALICE, { [m.user(ALICE)]: points(null) }, del(m.user(ALICE))),
    // dan joins bob's household through carol's invite (M1-54): his member doc, the invite's delete
    // and his users doc in one batch. By n % 16: the base case (0, 11, 13 to 15); the invite
    // expired (1); its creator, carol, no longer a member (2, and 12 since M1-11's templates share
    // the ninth weight); the invite kept (3); dan's doc with role owner, an earlier joinedAt or an
    // unknown key (4 to 6); an invite to H2, which dan owns, so he may delete it (7); the household
    // a tombstone that keeps its name (8); dan already a member, his doc set again unchanged, so
    // only the delete's !M(uid) denies (9); another of carol's invites deleted too, which his doc
    // does not name (10).
    join: (n) => {
        const v = n % 16;
        const code = v === 7 ? CODE2 : CODE;
        const joinedAt = v === 9 ? m.T0 : m.NOW; // 9: a stored time, as his doc already has it
        const doc: m.Doc = { ...MEMBER, joinedAt, viaInvite: code, ...JOINED[v] };
        const expiresAt = v === 1 ? m.T0 : LATER;
        const world: Record<string, m.Doc> = {
            ...(v === 2 || v === 12 ? HOME : CAROLS),
            [m.household(H1)]: { ...LIVE, deleted: v === 8 },
            [`invites/${code}`]: { ...INVITE, householdId: v === 7 ? H2 : H1, expiresAt },
        };
        if (v === 7) world[m.household(H2)] = { ...LIVE, ownerUid: DAN };
        if (v === 9) world[m.member(H1, DAN)] = doc;
        if (v === 10) world[`invites/${CODE3}`] = INVITE;
        const deleted: string[] = v === 3 ? [] : v === 10 ? [code, CODE3] : [code];
        const writes = [set(m.member(H1, DAN), doc), ...deleted.map((c) => del(`invites/${c}`))];
        return draft(
            DAN,
            { ...world, [m.user(DAN)]: points(null) },
            ...writes,
            up(m.user(DAN), points(H1)),
        );
    },
    // M1-95, once the soft delete's extension point: bob's soft delete of H1 (the base case); by
    // n % 8 under dan's tombstone H2: dan's cleanup of carol's member doc, alice's marker or the
    // invite (1 to 3), his get and list of the markers (4, 5); carol's own member doc deleted with
    // her users-doc clear (P6), there (6) or already gone (7).
    tombstone: (n) => {
        const v = n % 8;
        const marker = `${m.household(H2)}/removed/${ALICE}`;
        const carols = v === 7 ? {} : { [m.member(H2, CAROL)]: MEMBER };
        const world = {
            ...SEEN,
            ...carols,
            [marker]: { removedAt: m.T0 },
            [m.user(CAROL)]: points(H2),
        };
        const reads: m.Request[] = [
            { op: "get", path: marker },
            { op: "list", path: `${m.household(H2)}/removed` },
        ];
        const gone = [m.member(H2, CAROL), marker, `invites/${CODE2}`][v - 1];
        if (v === 0) return draft(BOB, HOME, up(m.household(H1), { deleted: true, name: "" }));
        if (v === 4 || v === 5) return { ...draft(DAN, world), read: reads[v - 4] };
        if (gone !== undefined) return draft(DAN, world, del(gone));
        return draft(CAROL, world, del(m.member(H2, CAROL)), up(m.user(CAROL), points(null)));
    },
    // M1-11, Leave: carol, a plain member of bob's H1, deletes her member doc and her invite and
    // clears her users doc (the base case). By n % 8: bob, the owner, leaves (1); carol's member
    // doc already gone (2); she deletes dan's alone (3); she writes her own marker in it (4).
    leave: (n) => {
        const v = n % 8;
        const by = v === 1 ? BOB : CAROL;
        const carols = v === 2 ? {} : { [m.member(H1, CAROL)]: MEMBER };
        const dans = { [m.member(H1, DAN)]: MEMBER, [`invites/${CODE}`]: INVITE };
        const world = { ...HOME, ...carols, ...dans, [m.user(by)]: points(H1) };
        if (v === 3) return draft(CAROL, world, del(m.member(H1, DAN)));
        const mark = v === 4 ? [set(m.marker(H1, CAROL), { removedAt: m.NOW })] : [];
        const invites = by === CAROL ? [del(`invites/${CODE}`)] : [];
        const writes = [del(m.member(H1, by)), ...invites, ...mark];
        return draft(by, world, ...writes, up(m.user(by), points(null)));
    },
    // M1-11, Remove member: bob deletes carol's member doc and her invite and writes her marker
    // (the base case). By n % 8: an overwrite of her leftover marker (1); the member delete with
    // the leftover marker and no marker write (2), or with neither (3); bob removes himself (4);
    // the marker alone, carol staying a member (5); carol's member doc already gone (6); the
    // marker with another field (7).
    "remove member": (n) => {
        const v = n % 8;
        const target = v === 4 ? BOB : CAROL;
        const leftover = v === 1 || v === 2 ? { [m.marker(H1, CAROL)]: { removedAt: m.T0 } } : {};
        const carols = v === 6 ? {} : { [m.member(H1, CAROL)]: MEMBER };
        const world = { ...HOME, ...carols, ...leftover, [`invites/${CODE}`]: INVITE };
        const member = v === 5 ? [] : [del(m.member(H1, target))];
        const marker: m.Doc = { removedAt: m.NOW, ...(v === 7 ? { by: BOB } : {}) };
        const mark = v === 2 || v === 3 ? [] : [set(m.marker(H1, target), marker)];
        return draft(BOB, world, ...member, ...mark, del(`invites/${CODE}`));
    },
    // M1-11: in his live household bob gets, lists or deletes (n % 3) alice's marker (the base
    // case); carol, a plain member, tries the same (n % 6 > 2).
    markers: (n) => {
        const marker = m.marker(H1, ALICE);
        const d = draft(n % 6 > 2 ? CAROL : BOB, { ...CAROLS, [marker]: { removedAt: m.T0 } });
        const list = `${m.household(H1)}/removed`;
        const reads: m.Request[] = [
            { op: "get", path: marker },
            { op: "list", path: list },
        ];
        const read = reads[n % 3];
        return read ? { ...d, read } : { ...d, writes: [del(marker)] };
    },
};
export const EXTENSIONS = Object.keys(TEMPLATES).filter((t) => t.startsWith("M1-"));

// A written value: names around the P4 bounds (blank ones of each kind, non-BMP ones), ids, times,
// the other role, and values of the wrong type.
const CHARS = ["a", " ", "\t", "\n", "\u0001", "\u{a0}", "\u{3000}", "\u{1F3E0}"];
const NAME = fc.oneof(
    fc.constantFrom("Ann", "a".repeat(50), "a".repeat(51), "\u{1F3E0}".repeat(50), "", "  "),
    fc.string({ unit: fc.constantFrom(...CHARS), maxLength: 3 }),
    fc.string({ unit: fc.constantFrom(...CHARS.slice(1, 5)), minLength: 1, maxLength: 3 }),
    fc.string({ unit: fc.constantFrom(...CHARS), minLength: 49, maxLength: 51 }),
);
const TIMES: m.Value[] = [m.T0, m.NOW, SOON, LATE];
const VALUES: m.Value[] = [...UIDS, ...HIDS, "owner", "member", ...TIMES, true, false, null, 42];
// A stored value keeps its PLAN section 3 type: another id, the other role, a tombstone, null.
const STORED: Record<string, m.Value[]> = {
    householdId: [null, H1, H2, H3],
    ownerUid: UIDS,
    createdBy: [null, ALICE],
    deleted: [true, false],
    role: ["owner", "member"],
    displayName: ["Name", " "],
    name: ["Home", ""],
    expiresAt: [m.T0, LATER],
};
// An `extra` key: one of PLAN section 3 for the collection that the write lacks (P4), or unknown.
const KEYS: Record<string, string[]> = {
    users: ["householdId", "name"],
    households: Object.keys(LIVE),
    members: [...Object.keys(MEMBER), "viaInvite"],
    invites: Object.keys(ASKED),
};

const KINDS = "value value value field field field rename rename clone clone drop extra op id omit";
const tweak = fc.record({
    kind: fc.constantFrom(...`${KINDS} name name alone tomb gone add auth caller`.split(" ")),
    at: fc.nat(),
    key: fc.nat(),
    value: fc.oneof(NAME, fc.constantFrom(...VALUES)),
    name: NAME,
    v: fc.nat(),
});
type Tweak = typeof tweak extends fc.Arbitrary<infer T> ? T : never;

const pick = <T>(items: readonly T[], i: number): T | undefined => items[i % items.length];
// Another id of the same kind (a uid, a household id or a code); the ids of a path; one id swapped,
// in an invite's path also as its code's prefix, so a renamed household keeps its invites (P3).
const other = (id: string, i: number): string =>
    pick([HIDS, CODES].find((kind) => kind.includes(id)) ?? UIDS, i) ?? ALICE;
const ids = (path: string): string[] => path.split("/").filter((_, i) => i % 2 === 1);
const swap = (path: string, from: string, to: string): string =>
    `/${path}/`.replace(`/${from}/`, `/${to}/`).replace(`/${from}_`, `/${to}_`).slice(1, -1);
const swapped = (d: m.Doc, from: string, to: string): m.Doc =>
    Object.fromEntries(Object.entries(d).map(([k, v]) => [k, v === from ? to : v]));

// One tweak. A write: a field's value, its name, a field dropped or added, its op, an id of its
// path, a copy under another id, the write left out or alone. A template document: a stored
// field, gone or added; an id renamed everywhere; households tombstoned; the caller's auth or uid.
function change(d: Draft, t: Tweak, paths: string[]): void {
    const w = pick(d.writes, t.at);
    const path = pick(paths, t.at) ?? "";
    const doc = d.world.get(path);
    const key = (data: m.Doc): string => pick(Object.keys(data), t.key) ?? "color";
    const reid = (p: string, id = pick(ids(p), t.key) ?? ""): string =>
        swap(p, id, other(id, t.at));
    const value = doc && pick(STORED[key(doc)] ?? [], t.v);
    const data = w?.data ?? {};
    const absent = (KEYS[w?.path.split("/").at(-2) ?? ""] ?? []).filter((k) => !(k in data));
    const extra = pick([...absent, "color"], t.key) ?? "color";
    const named = Object.keys(data).find((k) => k.endsWith("ame")); // name, displayName
    if (t.kind === "value" && w) w.data = { ...w.data, [key(w.data)]: t.value };
    if (t.kind === "name" && w && named) w.data = { ...w.data, [named]: t.name };
    if (t.kind === "drop" && w)
        w.data = Object.fromEntries(Object.entries(w.data).filter(([k]) => k !== key(w.data)));
    if (t.kind === "extra" && w) w.data = { ...w.data, [extra]: t.value };
    if (t.kind === "alone" && w) d.writes = [w];
    if (t.kind === "op" && w) w.op = pick<Op>(["set", "update", "delete"], t.key) ?? "set";
    if (t.kind === "id" && w) w.path = reid(w.path);
    if (t.kind === "clone" && w) d.writes.push({ ...w, path: reid(w.path) });
    if (t.kind === "omit") d.writes = d.writes.filter((x) => x !== w);
    if (t.kind === "field" && doc && value !== undefined)
        d.world.set(path, { ...doc, [key(doc)]: value });
    if (t.kind === "gone") d.world.delete(path);
    if (t.kind === "add" && !doc && path) d.world.set(path, variant(path, t.key));
    if (t.kind === "auth") d.caller = { ...d.caller, auth: t.key % 2 ? "unverified" : "anonymous" };
    if (t.kind === "caller") d.caller = { ...d.caller, uid: pick(UIDS, t.key) ?? ALICE };
    for (const [p, x] of t.kind === "tomb" ? d.world : [])
        if (x.deleted === false) d.world.set(p, { ...x, deleted: true, name: "" });
    if (t.kind !== "rename") return;
    const from = pick([...new Set(paths.flatMap(ids))], t.at) ?? "";
    const to = other(from, t.key);
    const re = (p: string): string => swap(p, from, to);
    const moved = [...d.world].map(([p, x]): [string, m.Doc] =>
        paths.includes(p) ? [re(p), swapped(x, from, to)] : [p, x],
    );
    d.world = new Map(moved);
    d.writes = d.writes.map((x) => ({ ...x, path: re(x.path), data: swapped(x.data, from, to) }));
    if (d.caller.uid === from) d.caller = { ...d.caller, uid: to };
}

// Row templates; Create household (most conditions: P1, P3, P4) is drawn 3x as often, read 2x.
// Former extension points (the tombstone's soft delete, the join, M1-11's leave, remove member
// and markers) share the ninth weight, so the other templates' draws stay as #372 measured them.
const FORMER = ["tombstone", "join", "leave", "remove member", "markers"];
const ROWS = Object.keys(TEMPLATES).filter((t) => !EXTENSIONS.includes(t) && !FORMER.includes(t));
const DRAWN = [...ROWS, "create household", "create household", "read"];
export const cases = fc.record({
    template: fc.oneof(
        { weight: 8, arbitrary: fc.constantFrom(...DRAWN) },
        { weight: 1, arbitrary: fc.constantFrom(...EXTENSIONS, ...FORMER) },
    ),
    n: fc.nat(),
    tweaks: fc.oneof({ weight: 2, arbitrary: fc.tuple(tweak) }, fc.array(tweak, { maxLength: 3 })),
    // The background: documents of the planned paths, each a variant; the template's replace it.
    background: fc.array(fc.tuple(fc.constantFrom(...DOCS), fc.nat()), { maxLength: 12 }),
});
export type Case = typeof cases extends fc.Arbitrary<infer T> ? T : never;
const base = (template: string): Case => ({ template, n: 0, tweaks: [], background: [] });
export const BASES = Object.keys(TEMPLATES).map(base);

export function build(c: Case): { world: m.World; caller: m.Caller; request: m.Request } {
    const make = TEMPLATES[c.template];
    if (make === undefined) throw new Error(`no template ${c.template}`);
    const d = make(c.n);
    const paths = [...d.world.keys(), ...d.writes.map((w) => w.path)];
    const background = c.background.filter(([p]) => !paths.includes(p));
    const docs = background.map(([p, n]): [string, m.Doc] => [p, variant(p, n)]);
    d.world = new Map([["config/app", { minVersionCode: 1 }], ...docs, ...d.world]);
    for (const t of c.tweaks) change(d, t, paths);
    // A request writes a document once (model.ts): a tweak that repeats a path drops the write.
    const writes = d.writes.filter((w, i) => d.writes.findIndex((x) => x.path === w.path) === i);
    return { world: d.world, caller: d.caller, request: d.read ?? { op: "commit", writes } };
}

// The SDK form of a document: the request time as a FieldValue.
function sdk(d: m.Doc): Record<string, unknown> {
    const now = firebase.firestore.FieldValue.serverTimestamp();
    return Object.fromEntries(Object.entries(d).map(([k, v]) => [k, v === m.NOW ? now : v]));
}

type Query = ReturnType<ReturnType<h.Db["collection"]>["where"]>;
function send(db: h.Db, r: m.Request): Promise<unknown> {
    if (r.op !== "commit") {
        if (r.op === "get") return db.doc(r.path).get();
        let query: Query = db.collection(r.path);
        for (const [k, v] of Object.entries(r.where ?? {})) query = query.where(k, "==", v);
        return query.get();
    }
    const batch = db.batch();
    for (const { op, path, data } of r.writes)
        if (op === "delete") batch.delete(db.doc(path));
        else if (op === "set") batch.set(db.doc(path), sdk(data));
        else batch.update(db.doc(path), sdk(data));
    return batch.commit();
}

const symbols = (_k: string, v: unknown): unknown => (typeof v === "symbol" ? v.toString() : v);

// The fuzz on `rules`: for every case the emulator's verdict must be the model's. A failure names
// both, the case built and fast-check's seed and path, which replay it.
export async function fuzz(rules: string, params: fc.Parameters<[Case]>): Promise<void> {
    firebase.firestore.setLogLevel("error"); // no SDK warning per denied request in the CI log
    const env = await initializeTestEnvironment({ projectId: h.PROJECT, firestore: { rules } });
    try {
        const clients = new Map(UIDS.map((u) => [u, h.connect(env, u)]));
        await env.clearFirestore();
        await env.withSecurityRulesDisabled(async (ctx) => {
            const admin = ctx.firestore();
            let last: string[] = []; // the documents the case before may have left
            const check = async (c: Case): Promise<void> => {
                const { world, caller, request } = build(c);
                const seed = admin.batch();
                for (const p of last) if (!world.has(p)) seed.delete(admin.doc(p));
                for (const [path, doc] of world) seed.set(admin.doc(path), sdk(doc));
                await seed.commit();
                const writes = request.op === "commit" ? request.writes.map((w) => w.path) : [];
                last = [...new Set([...world.keys(), ...writes])];
                const db = clients.get(caller.uid)?.[caller.auth];
                if (db === undefined) throw new Error(`no client for ${caller.uid}`);
                const got = await h.outcome(send(db, request));
                const want = m.decide(world, caller, request);
                if (got === want) return;
                const rows = m.explain(world, caller, request);
                const text = JSON.stringify({ caller, request, rows, world: [...world] }, symbols);
                throw new Error(`the emulator says ${got}, the model ${want}: ${text}`);
            };
            const property = fc.asyncProperty(cases, check);
            await fc.assert(property, { includeErrorInReport: true, ...params });
        });
    } finally {
        await env.cleanup();
    }
}
