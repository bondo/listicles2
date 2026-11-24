// The reference model of PLAN section 3.1 (M1-06, P17): who may read and write what, written from
// the PLAN rows, not from firestore.rules, so that fuzz.test.ts can compare the two on random
// cases. ROWS has a row for each allow statement of the rules (fuzz.test.ts checks it). The PLAN
// rows the rules lack are extension points, denied here until their task adds the rule and its row:
// leave, remove member and the marker writes (M1-11). A new allow statement fails that check until
// its row is in; a new path of an existing one fails the fuzz on its base case (fuzz.ts).

export const NOW = Symbol("request.time"); // FieldValue.serverTimestamp() in a write
export const T0 = new Date(0); // every stored timestamp, never request.time
export type Value = string | number | boolean | null | Date | typeof NOW;
export type Doc = Readonly<Record<string, Value>>;
export type World = ReadonlyMap<string, Doc>;
export type Caller = {
    readonly uid: string;
    readonly auth: "anonymous" | "unverified" | "verified";
};
export type Write = { op: "set" | "update" | "delete"; path: string; data: Doc };
// A list query's equality filters are `where` (an invite list must fix householdId, #280).
export type Request =
    { op: "get" | "list"; path: string; where?: Doc } | { op: "commit"; writes: Write[] };
type Method = "get" | "list" | "create" | "update" | "delete";

// What a row sees: the caller, the world before the request (get, exists) and after it (getAfter,
// existsAfter), the document before (resource) and after (request.resource; {} after a delete).
type Ctx = {
    uid: string;
    authed: boolean;
    signedIn: boolean;
    before: World;
    after: World;
    where: Doc;
};
type Row = (x: Ctx & { old: Doc | undefined; doc: Doc }, ...ids: string[]) => boolean;

export const user = (uid: string): string => `users/${uid}`;
export const household = (hid: string): string => `households/${hid}`;
export const member = (hid: string, uid: string): string => `households/${hid}/members/${uid}`;

// P4: 1-50 code points and not blank. Blank is as Firestore's trim() has it: only code points up
// to U+0020 (the app's Kotlin trim also strips Unicode spaces: M1-90).
export function validName(v: Value | undefined): boolean {
    const points = typeof v === "string" ? Array.from(v) : [];
    return points.length <= 50 && points.some((c) => (c.codePointAt(0) ?? 0) > 0x20);
}

const keysAre = (d: Doc, keys: string[]): boolean =>
    Object.keys(d).length === keys.length && keys.every((k) => k in d);
// An update changes no key but `keys` (diff().affectedKeys(), P4).
const only = (old: Doc | undefined, doc: Doc, keys: string[]): boolean =>
    [...Object.keys(old ?? {}), ...Object.keys(doc)].every(
        (k) => keys.includes(k) || old?.[k] === doc[k],
    );
const isMember = (w: World, hid: string, uid: string): boolean => w.has(member(hid, uid));
const live = (w: World, hid: string): boolean => w.get(household(hid))?.deleted === false;
// PLAN 3.1 Reads: a member of the live household, M(uid) and LIVE.
const reader = (x: Ctx, hid: string): boolean =>
    x.signedIn && live(x.before, hid) && isMember(x.before, hid, x.uid);
// Delete household (M1-95): the owner's cleanup reads and deletes under the tombstone, O(uid).
const cleanup = (x: Ctx, hid: string): boolean => {
    const home = x.before.get(household(hid));
    return x.signedIn && home?.deleted === true && home.ownerUid === x.uid;
};

// householdId (P5): unchanged; set (null -> hid) with the caller's member doc in a live household
// after the request; cleared (hid -> null) once that member doc is gone after it; never hid1 -> hid2.
function moves(x: Ctx, from: Value | undefined, to: Value | undefined): boolean {
    const joins = typeof to === "string" && isMember(x.after, to, x.uid) && live(x.after, to);
    if (from === to || (from === null && joins)) return true;
    return typeof from === "string" && to === null && !isMember(x.after, from, x.uid);
}

// The users doc (P5, P9): householdId, always, and name, optional, a valid name when there.
const userDoc = (d: Doc): boolean =>
    keysAre(d, "name" in d ? ["householdId", "name"] : ["householdId"]) &&
    (!("name" in d) || validName(d.name));

// The one-household check of a member create: the caller's users doc holds null before the request
// and `hid` after it.
function oneHousehold(x: Ctx, hid: string): boolean {
    const users = [x.before, x.after].map((w) => w.get(user(x.uid))?.householdId);
    return users[0] === null && users[1] === hid;
}

// The owner's member doc of Create household: the caller's own (P1), role owner, the keys (P4),
// joined now, in a household that does not exist before the request and names the caller as owner
// after it, with the one-household check.
function createsOwner(x: Ctx, d: Doc, hid: string, uid: string): boolean {
    const shape = keysAre(d, ["role", "displayName", "joinedAt"]) && validName(d.displayName);
    const owner = uid === x.uid && d.role === "owner" && d.joinedAt === NOW;
    const created =
        !x.before.has(household(hid)) && x.after.get(household(hid))?.ownerUid === x.uid;
    return x.signedIn && shape && owner && created && oneHousehold(x, hid);
}

// The joiner's member doc of Join: the caller's own (P1) and no member doc before the request,
// role member, joined now, the keys with viaInvite (P4), the code of an invite before the request
// that points at this live household, has not expired, whose creator is still a member and which
// the request deletes (single use), with the one-household check.
function joins(x: Ctx, d: Doc, hid: string, uid: string): boolean {
    const keys = ["role", "displayName", "joinedAt", "viaInvite"];
    const shape = keysAre(d, keys) && validName(d.displayName);
    const own = uid === x.uid && !isMember(x.before, hid, uid);
    const values = own && d.role === "member" && d.joinedAt === NOW;
    const code = `invites/${String(d.viaInvite)}`;
    const invite = typeof d.viaInvite === "string" ? x.before.get(code) : undefined;
    const exp = invite?.expiresAt;
    const valid =
        invite?.householdId === hid &&
        exp instanceof Date &&
        exp.getTime() > Date.now() &&
        isMember(x.before, hid, String(invite.createdBy)) &&
        !x.after.has(code);
    return x.signedIn && shape && values && valid && live(x.before, hid) && oneHousehold(x, hid);
}

// Transfer ownership, the household update: the owner (O(uid), never M(uid)) of the live household
// changes only ownerUid, to a member before and after the request, after which the old owner's role
// is member and the new owner's owner.
function transfers(x: Ctx, old: Doc | undefined, d: Doc, hid: string): boolean {
    const to = d.ownerUid;
    if (typeof to !== "string" || !only(old, d, ["ownerUid"])) return false;
    const role = (uid: string): Value | undefined => x.after.get(member(hid, uid))?.role;
    const owner = x.signedIn && old?.deleted === false && old.ownerUid === x.uid;
    const roles = role(x.uid) === "member" && role(to) === "owner";
    return owner && isMember(x.before, hid, to) && isMember(x.after, hid, to) && roles;
}

// Create invite: a member of the live household as createdBy, now, the household's name (P2), an
// expiry within 7 days, a code of that household and a 22-character secret (P3, #243), the keys (P4).
function createsInvite(x: Ctx, d: Doc, code: string): boolean {
    const hid = String(d.householdId);
    const keys = keysAre(d, [
        "householdId",
        "householdName",
        "createdBy",
        "createdAt",
        "expiresAt",
    ]);
    const id =
        /^[A-Za-z0-9]{20}_[A-Za-z0-9_-]{22}$/.test(code) && code.split("_")[0] === d.householdId;
    const exp = d.expiresAt;
    const week =
        exp === NOW || (exp instanceof Date && exp.getTime() <= Date.now() + 7 * 86_400_000);
    const values = d.createdBy === x.uid && d.createdAt === NOW && week;
    const home = x.before.get(household(hid));
    const own =
        live(x.before, hid) && d.householdName === home?.name && isMember(x.before, hid, x.uid);
    return x.signedIn && keys && id && values && own;
}

export const ROWS: Readonly<Record<string, Partial<Record<Method, Row>>>> = {
    // Only that user, verified or not (AUTH-06, HH-03); created holding no household; deleted only
    // holding none, or when there is no doc (M1-08's rule, not in PLAN 3.1 yet: a repeated delete).
    "users/{uid}": {
        get: (x, uid) => x.authed && x.uid === uid,
        create: (x, uid) =>
            x.authed && x.uid === uid && userDoc(x.doc) && x.doc.householdId === null,
        update: (x, uid) => {
            const keys = userDoc(x.doc) && only(x.old, x.doc, ["householdId", "name"]);
            return (
                x.authed && x.uid === uid && keys && moves(x, x.old?.householdId, x.doc.householdId)
            );
        },
        delete: (x, uid) => x.authed && x.uid === uid && (!x.old || x.old.householdId === null),
    },
    "households/{hid}": {
        // A member's read of the live household, or the tombstone read: the caller's householdId
        // points at it.
        get: (x, hid) =>
            reader(x, hid) ||
            (x.signedIn &&
                x.old?.deleted === true &&
                x.before.get(user(x.uid))?.householdId === hid),
        // Create household: an auto-id (P3), the five keys and a name (P4), the caller as creator and
        // owner, not deleted, the caller's member doc after the request.
        create: (x, hid) => {
            const d = x.doc;
            const shape = keysAre(d, ["name", "createdBy", "createdAt", "ownerUid", "deleted"]);
            const values = validName(d.name) && d.createdAt === NOW && d.deleted === false;
            const own =
                d.createdBy === x.uid && d.ownerUid === x.uid && isMember(x.after, hid, x.uid);
            return x.signedIn && /^[A-Za-z0-9]{20}$/.test(hid) && shape && values && own;
        },
        // Transfer ownership, or the soft delete (M1-95): the owner of the live household sets
        // deleted and clears the name (#205), nothing else.
        update: (x, hid) => {
            const owner = x.signedIn && x.old?.deleted === false && x.old.ownerUid === x.uid;
            const soft = x.doc.deleted === true && x.doc.name === "";
            const softDelete = owner && soft && only(x.old, x.doc, ["deleted", "name"]);
            return softDelete || transfers(x, x.old, x.doc, hid);
        },
    },
    "households/{hid}/members/{uid}": {
        // The caller's own member path in any household (it may not exist), a member's read, or
        // the owner's cleanup.
        get: (x, hid, uid) => (x.signedIn && uid === x.uid) || reader(x, hid) || cleanup(x, hid),
        list: (x, hid) => reader(x, hid) || cleanup(x, hid),
        create: (x, hid, uid) => createsOwner(x, x.doc, hid, uid) || joins(x, x.doc, hid, uid),
        // While the household is live: the caller's own displayName (P4), or, by the owner before
        // the request, the role ownerUid gives the doc after it (Transfer ownership).
        update: (x, hid, uid) => {
            const home = x.before.get(household(hid));
            const role = x.after.get(household(hid))?.ownerUid === uid ? "owner" : "member";
            const name =
                uid === x.uid &&
                only(x.old, x.doc, ["displayName"]) &&
                validName(x.doc.displayName);
            const transfer =
                home?.ownerUid === x.uid && only(x.old, x.doc, ["role"]) && x.doc.role === role;
            return x.signedIn && home?.deleted === false && (name || transfer);
        },
        // Under a tombstone (M1-95): the caller's own, even when it is gone (P6), or the cleanup.
        delete: (x, hid, uid) =>
            (x.signedIn && uid === x.uid && x.before.get(household(hid))?.deleted === true) ||
            cleanup(x, hid),
    },
    // The removed markers: here only the tombstone's cleanup (M1-95).
    "households/{hid}/removed/{uid}": { get: cleanup, list: cleanup, delete: cleanup },
    // Invites (M1-12), each while the household is live: get, any signed-in user (verified; they
    // need the code, HH-03); list, a member whose query fixes householdId and, unless the owner,
    // createdBy as the caller (#280); create (below); delete, its creator or the owner, any member
    // once it has expired, or the joiner in the join batch. Under a tombstone the owner's cleanup gets,
    // lists (on householdId) and deletes them (M1-95).
    "invites/{code}": {
        get: (x) => {
            const hid = String(x.old?.householdId);
            return (x.signedIn && live(x.before, hid)) || cleanup(x, hid);
        },
        list: (x) => {
            const hid = x.where.householdId;
            const own =
                x.where.createdBy === x.uid ||
                x.before.get(household(String(hid)))?.ownerUid === x.uid;
            if (typeof hid !== "string") return false;
            const mine = live(x.before, hid) && isMember(x.before, hid, x.uid) && own;
            return (x.signedIn && mine) || cleanup(x, hid);
        },
        create: (x, code) => createsInvite(x, x.doc, code),
        delete: (x, code) => {
            const hid = String(x.old?.householdId);
            const exp = x.old?.expiresAt;
            const expired =
                exp instanceof Date && exp.getTime() < Date.now() && isMember(x.before, hid, x.uid);
            // The joiner's: no member doc before the request, one after it that names this code.
            const joiner =
                !isMember(x.before, hid, x.uid) &&
                x.after.get(member(hid, x.uid))?.viaInvite === code;
            const who =
                x.old?.createdBy === x.uid ||
                x.before.get(household(hid))?.ownerUid === x.uid ||
                expired ||
                joiner;
            return (x.signedIn && live(x.before, hid) && who) || cleanup(x, hid);
        },
    },
    // Anyone, even signed out (START-01); no client writes.
    "config/app": { get: () => true },
};

// The world after the writes of a request, in order (no request writes one document twice).
function apply(world: World, writes: Write[]): World {
    const after = new Map(world);
    for (const w of writes) {
        const old = after.get(w.path);
        if (w.op === "delete") after.delete(w.path);
        else if (w.op === "set") after.set(w.path, w.data);
        else if (old) after.set(w.path, { ...old, ...w.data });
    }
    return after;
}

// Each read, or each write of a request, with its row and method and whether the row allows it:
// a set is a create when there is no doc, an update when there is, and an update needs the doc.
export function explain(world: World, c: Caller, r: Request): { row: string; allowed: boolean }[] {
    const after = r.op === "commit" ? apply(world, r.writes) : world;
    const signedIn = c.auth === "verified";
    const where = r.op === "list" ? (r.where ?? {}) : {};
    const x = { uid: c.uid, authed: c.auth !== "anonymous", signedIn, before: world, after, where };
    const asks =
        r.op === "commit" ? r.writes : [{ ...r, path: r.op === "list" ? `${r.path}/-` : r.path }];
    return asks.map((w) => {
        const old = world.get(w.path);
        const method = w.op === "set" ? (old ? "update" : "create") : w.op;
        for (const [template, row] of Object.entries(ROWS)) {
            const ids = new RegExp(`^${template.replace(/\{\w+\}/g, "([^/]+)")}$`).exec(w.path);
            const doc = after.get(w.path) ?? {};
            const allowed =
                ids &&
                (method !== "update" || old) &&
                row[method]?.({ ...x, old, doc }, ...ids.slice(1));
            if (ids) return { row: `${template} ${method}`, allowed: allowed === true };
        }
        return { row: `${w.path} ${method}`, allowed: false };
    });
}

export function decide(world: World, caller: Caller, request: Request): "allowed" | "denied" {
    return explain(world, caller, request).every((e) => e.allowed) ? "allowed" : "denied";
}
