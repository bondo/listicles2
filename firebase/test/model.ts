// The reference model of PLAN section 3.1 (M1-06, P17): who may read and write what, written from
// the PLAN rows, not from firestore.rules, so that fuzz.test.ts can compare the two on random
// cases. ROWS has a row for each allow statement of the rules (fuzz.test.ts checks it). The PLAN
// rows the rules lack are extension points, denied here until their task adds the rule and its row:
// invites (M1-12), the join batch (M1-54), leave, remove member, the removed markers, the soft
// delete, its cleanup and P6 (M1-11). A new allow statement fails that check until its row is in;
// a new path of an existing one (the join, the soft delete) fails the fuzz on its base case (fuzz.ts).

export const NOW = Symbol("request.time"); // FieldValue.serverTimestamp() in a write
export const DELETE = Symbol("FieldValue.delete()"); // drops the field in an update
export const T0 = new Date(0); // every stored timestamp, never request.time
export type Value = string | number | boolean | null | Date | typeof NOW | typeof DELETE;
export type Doc = Readonly<Record<string, Value>>;
export type World = ReadonlyMap<string, Doc>;
export type Caller = {
    readonly uid: string;
    readonly auth: "anonymous" | "unverified" | "verified";
};
export type Write = { op: "set" | "update" | "delete"; path: string; data: Doc };
export type Request = { op: "get" | "list"; path: string } | { op: "commit"; writes: Write[] };
type Method = "get" | "list" | "create" | "update" | "delete";

// What a row sees: the caller, the world before the request (get, exists) and after it (getAfter,
// existsAfter), the document before (resource) and after (request.resource; {} for reads, deletes).
type Ctx = { uid: string; authed: boolean; signedIn: boolean; before: World; after: World };
type Row = (x: Ctx & { old: Doc | undefined; doc: Doc }, ...ids: string[]) => boolean;

export const user = (uid: string): string => `users/${uid}`;
export const household = (hid: string): string => `households/${hid}`;
export const member = (hid: string, uid: string): string => `households/${hid}/members/${uid}`;

export const ROWS: Readonly<Record<string, Partial<Record<Method, Row>>>> = {};

// The world after the writes of a request, in order (no request writes one document twice).
function apply(world: World, writes: Write[]): World {
    const after = new Map(world);
    for (const w of writes) {
        const old = after.get(w.path);
        const merged = Object.entries({ ...old, ...w.data }).filter(([, v]) => v !== DELETE);
        if (w.op === "delete") after.delete(w.path);
        else if (w.op === "set") after.set(w.path, w.data);
        else if (old) after.set(w.path, Object.fromEntries(merged));
    }
    return after;
}

// Each read, or each write of a request, with its row and method and whether the row allows it:
// a set is a create when there is no doc, an update when there is, and an update needs the doc.
export function explain(world: World, c: Caller, r: Request): { row: string; allowed: boolean }[] {
    const after = r.op === "commit" ? apply(world, r.writes) : world;
    const signedIn = c.auth === "verified";
    const x = { uid: c.uid, authed: c.auth !== "anonymous", signedIn, before: world, after };
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
