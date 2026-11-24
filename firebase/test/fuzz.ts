import { initializeTestEnvironment } from "@firebase/rules-unit-testing";
import fc from "fast-check";
import firebase from "firebase/compat/app";
import * as h from "./harness";
import * as m from "./model";

// The rules fuzz (M1-06, P17): random cases (a world seeded with rules off, a caller, a request)
// sent to the emulator and to the reference model (model.ts), which must agree. A case is a
// template's base case, which PLAN 3.1 allows in a minimal world (an extension point's once its task
// adds the row), a few generic tweaks, each of one write, document or the caller, so most cases sit
// next to a rule's boundary, and a random background. A new row needs only its template.
const [ALICE, BOB, CAROL, DAN] = ["alice", "bob", "carol", "dan"];
const UIDS = [ALICE, BOB, CAROL, DAN];
// Firestore auto-ids (P3), and ids that are not: 19 and 21 characters, a `_`, a `-`.
const [H1, H2, H3] = ["Kq3ZtW9xLm2RbV7nPc4D", "Pz8YwV2nQs5TxK1mRc7B", "Mx4UvB6tRw9QaZ3nLk2C"];
const HIDS = [H1, H2, H3, H1.slice(1), `${H1}x`, `${H1.slice(1)}_`, `${H1.slice(1)}-`];
const CODE = `${H1}_${"s".repeat(22)}`;

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
const INVITE = { householdId: H1, householdName: "Home", createdBy: CAROL, expiresAt: LATER };
const points = (householdId: string | null): m.Doc => ({ householdId });
// For reads: carol's live household of bob's, and dan's tombstone, which his householdId names.
const TOMB = { ...LIVE, ownerUid: DAN, name: "", deleted: true };
const SEEN = {
    ...CAROLS,
    [m.user(CAROL)]: points(H1),
    [m.household(H2)]: TOMB,
    [m.user(DAN)]: points(H2),
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
    "users doc: delete": () => draft(ALICE, { [m.user(ALICE)]: points(null) }, del(m.user(ALICE))),
    // Extension points that add a path to an allow statement the rules have (one with an allow
    // statement of its own fails fuzz.test.ts's row check instead): denied until their task adds it.
    "M1-11 soft delete": () => draft(BOB, HOME, up(m.household(H1), { deleted: true, name: "" })),
    "M1-54 join": () =>
        draft(
            DAN,
            { ...CAROLS, [`invites/${CODE}`]: INVITE, [m.user(DAN)]: points(null) },
            set(m.member(H1, DAN), { ...MEMBER, joinedAt: m.NOW, viaInvite: CODE }),
            del(`invites/${CODE}`),
            up(m.user(DAN), points(H1)),
        ),
};
export const EXTENSIONS = Object.keys(TEMPLATES).filter((t) => t.startsWith("M1-"));

// A written value: names around the P4 bounds (blank ones of each kind, non-BMP ones), ids, times,
// the other role, and values of the wrong type.
const CHARS = ["a", " ", "\t", "\n", "\u0001", "\u{a0}", "\u{3000}", "\u{1F3E0}"];
const NAME = fc.oneof(
    fc.constantFrom("Ann", "a".repeat(50), "a".repeat(51), "\u{1F3E0}".repeat(50), "", "  "),
    fc.string({ unit: fc.constantFrom(...CHARS), maxLength: 3 }),
    fc.string({ unit: fc.constantFrom(...CHARS), minLength: 49, maxLength: 51 }),
);
const VALUES: m.Value[] = [...UIDS, ...HIDS, "owner", "member", m.T0, m.NOW, true, false, null, 42];
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
// The key an `extra` tweak adds: one of the collection's in PLAN section 3 (P4) or an unknown one.
const KEYS: Record<string, string[]> = {
    users: ["householdId", "name", "color"],
    households: [...Object.keys(LIVE), "color"],
    members: [...Object.keys(MEMBER), "viaInvite", "color"],
};

const KINDS = "value value value field field field rename rename clone drop extra op id omit";
const tweak = fc.record({
    kind: fc.constantFrom(...`${KINDS} gone add auth caller`.split(" ")),
    at: fc.nat(),
    key: fc.nat(),
    value: fc.oneof(NAME, fc.constantFrom(...VALUES)),
});
type Tweak = typeof tweak extends fc.Arbitrary<infer T> ? T : never;

const pick = <T>(items: readonly T[], i: number): T | undefined => items[i % items.length];
// Another id of the same kind (a uid or a household id); the ids of a path; one id swapped.
const other = (id: string, i: number): string => pick(HIDS.includes(id) ? HIDS : UIDS, i) ?? ALICE;
const ids = (path: string): string[] => path.split("/").filter((_, i) => i % 2 === 1);
const swap = (path: string, from: string, to: string): string =>
    `/${path}/`.replace(`/${from}/`, `/${to}/`).slice(1, -1);
const swapped = (d: m.Doc, from: string, to: string): m.Doc =>
    Object.fromEntries(Object.entries(d).map(([k, v]) => [k, v === from ? to : v]));

// One tweak. A write: a field's value, a field left out or added, its operation, an id of its path,
// a copy under another id, the write left out. A template document: a stored field, the document
// gone or added; an id renamed in all of them, the writes and the caller. The caller's auth or uid.
function change(d: Draft, t: Tweak, paths: string[]): void {
    const w = pick(d.writes, t.at);
    const path = pick(paths, t.at) ?? "";
    const doc = d.world.get(path);
    const key = (data: m.Doc): string => pick(Object.keys(data), t.key) ?? "color";
    const reid = (p: string, id = pick(ids(p), t.key) ?? ""): string =>
        swap(p, id, other(id, t.at));
    const value = doc && pick(STORED[key(doc)] ?? [], t.at);
    const extra = pick(KEYS[w?.path.split("/").at(-2) ?? ""] ?? [], t.key) ?? "color";
    if (t.kind === "value" && w) w.data = { ...w.data, [key(w.data)]: t.value };
    if (t.kind === "drop" && w)
        w.data = Object.fromEntries(Object.entries(w.data).filter(([k]) => k !== key(w.data)));
    if (t.kind === "extra" && w) w.data = { ...w.data, [extra]: t.value };
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
    if (t.kind !== "rename") return;
    const from = pick([...new Set(paths.flatMap(ids))], t.at) ?? "";
    const to = other(from, t.key);
    const moved = [...d.world].map(([p, x]): [string, m.Doc] =>
        paths.includes(p) ? [swap(p, from, to), swapped(x, from, to)] : [p, x],
    );
    d.world = new Map(moved);
    d.writes = d.writes.map((x) => ({
        ...x,
        path: swap(x.path, from, to),
        data: swapped(x.data, from, to),
    }));
    if (d.caller.uid === from) d.caller = { ...d.caller, uid: to };
}

const ROWS = Object.keys(TEMPLATES).filter((t) => !EXTENSIONS.includes(t));
export const cases = fc.record({
    template: fc.oneof(
        { weight: 8, arbitrary: fc.constantFrom(...ROWS) },
        { weight: 1, arbitrary: fc.constantFrom(...EXTENSIONS) },
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

function send(db: h.Db, r: m.Request): Promise<unknown> {
    if (r.op !== "commit")
        return r.op === "get" ? db.doc(r.path).get() : db.collection(r.path).get();
    const batch = db.batch();
    for (const w of r.writes) {
        const ref = db.doc(w.path);
        if (w.op === "delete") batch.delete(ref);
        else if (w.op === "set") batch.set(ref, sdk(w.data));
        else batch.update(ref, sdk(w.data));
    }
    return batch.commit();
}

const symbols = (_k: string, v: unknown): unknown => (typeof v === "symbol" ? v.toString() : v);

// The fuzz on `rules`: for every case the emulator's verdict must be the model's. A failure names
// both, the case built and fast-check's seed and path, which replay it.
export async function fuzz(rules: string, params: fc.Parameters<[Case]>): Promise<void> {
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
