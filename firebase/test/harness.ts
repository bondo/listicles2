import * as fs from "node:fs";
import * as path from "node:path";
import {
    assertFails,
    assertSucceeds,
    type RulesTestContext,
    type RulesTestEnvironment,
    type TokenOptions,
} from "@firebase/rules-unit-testing";

// The default-deny harness (M1-52, see #202): every client tries every operation on one document of
// every collection in PLAN section 3 (two for a {uid} one: the caller's own and another user's) and on
// the unplanned paths. rules.test.ts expects each probe to be denied, except the few that ALLOWED
// carves out (M1-08 on), which it expects allowed; mutants.test.ts shows that opening any one of those
// collections turns that suite red.
// Their limit: each probe seeds at most its own document (`{ name: "seed" }`), writes a fixed generic
// payload and queries without a filter, so both catch only a path that is open whatever the stored
// data, payload and query filter. A rule that reads stored data (resource, get, exists), the payload
// or a query filter can be a hole and still pass both, denied by this setup and not by its
// authorization logic: it needs its own allow and deny tests in a seeded world (M1-08 on), and each
// allow test of a rule that needs a verified email goes through verifiedOnly (below).
// The contexts hand out the compat Firestore type, used as is (no type casts).
export type Db = ReturnType<RulesTestContext["firestore"]>;

const read = (...parts: string[]): string =>
    fs.readFileSync(path.join(__dirname, ...parts), "utf8");
export const RULES = read("..", "firestore.rules");
export const PLAN = read("..", "..", "docs", "PLAN.md");
// One emulator project for both test files: `npm test` runs Jest with --runInBand.
export const PROJECT = "demo-tally";

// The collections of the data-model block of PLAN section 3: the first word of each unindented line.
// No block, no line or a word that is not a document path throws, so the suite cannot shrink unseen.
export function planTemplates(plan: string): string[] {
    const block = /^## 3\. Data model \(Firestore\)\n+```\n([\s\S]*?)\n```/m.exec(plan)?.[1] ?? "";
    const templates = [...block.matchAll(/^\S+/gm)].map((m) => m[0]);
    const path = /^[\w-]+\/[\w{}-]+(\/[\w-]+\/[\w{}-]+)*$/;
    if (templates.length === 0 || !templates.every((t) => path.test(t))) {
        throw new Error(`PLAN section 3: no data-model block of paths: ${templates.join()}`);
    }
    return templates;
}

// Ids of the planned shapes (PLAN 3.1, P3): a 20-character auto-id, `<householdId>_<22-character secret>`.
export const UID = "alice";
const HID = "household00000000001";
const CODE = `${HID}_${"s".repeat(22)}`;
const IDS: Record<string, string> = {
    uid: UID,
    hid: HID,
    code: CODE,
    lid: "l1",
    iid: "i1",
    doc: "x",
};
const OTHER = { ...IDS, uid: "bob" };

// A document of a template: each {variable} becomes the id of that name; an unknown name throws.
export function instantiate(template: string, ids = IDS): string {
    return template.replace(/\{(\w+)\}/g, (_match, name: string) => {
        const id = ids[name];
        if (id === undefined) throw new Error(`no id for {${name}} in ${template}`);
        return id;
    });
}

export const TEMPLATES = planTemplates(PLAN);
// Paths no rule plans, so only the default deny covers them: a top-level collection, and a subcollection
// of every planned document, which a recursive or wildcard match there would open. Not when its
// condition reads stored data, as the cleanup match of #199 does: see the limit at the top.
export const UNPLANNED_ROOT = "anything/{doc}";
export const UNPLANNED = [UNPLANNED_ROOT, ...TEMPLATES.map((t) => `${t}/unplanned/{doc}`)];
// One document of every template (the caller's own for a {uid} one), another user's (bob) of each
// {uid} one, and the unplanned paths.
export const PATHS = [
    ...TEMPLATES.map((t) => instantiate(t)),
    ...TEMPLATES.filter((t) => t.endsWith("/{uid}")).map((t) => instantiate(t, OTHER)),
    ...UNPLANNED.map((t) => instantiate(t)),
];

const token = (uid: string, emailVerified: boolean): TokenOptions => ({
    email: `${uid}@example.com`,
    email_verified: emailVerified,
    firebase: { sign_in_provider: "password" },
});

// Signed out, signed in with an unverified email (PLAN 3.1 "Signed in"), and signed in and verified.
export const CLIENT_NAMES = ["anonymous", "unverified", "verified"] as const;
export type Client = (typeof CLIENT_NAMES)[number];

// The clients of `uid` (alice unless another user is named, as in the spike's batches of M1-09).
export function connect(env: RulesTestEnvironment, uid = UID): Record<Client, Db> {
    return {
        anonymous: env.unauthenticatedContext().firestore(),
        unverified: env.authenticatedContext(uid, token(uid, false)).firestore(),
        verified: env.authenticatedContext(uid, token(uid, true)).firestore(),
    };
}

// The document operations, a query on its collection and a collection-group query on that id.
export const OPS = ["get", "list", "group", "create", "update", "delete"] as const;
export type Op = (typeof OPS)[number];

export interface Probe {
    readonly client: Client;
    readonly op: Op;
    readonly path: string;
}

const PROBED: readonly Probe[] = PATHS.flatMap((path) =>
    OPS.flatMap((op) => CLIENT_NAMES.map((client) => ({ client, op, path }))),
);

// The probes the rules allow, carved out one by one, never a whole path (#301), so the self and
// others mutants still find their probes: anyone's get of config/app; a get of the caller's own users
// doc, verified or not (PLAN 3.1: the own-doc exception); a verified get of the own member path.
export const ALLOWED: readonly Probe[] = [
    ...CLIENT_NAMES.map((client): Probe => ({ client, op: "get", path: "config/app" })),
    { client: "unverified", op: "get", path: instantiate("users/{uid}") },
    { client: "verified", op: "get", path: instantiate("users/{uid}") },
    { client: "verified", op: "get", path: instantiate("households/{hid}/members/{uid}") },
];
const named = (p: Probe): string => `${p.client} ${p.op} ${p.path}`;
const allowed = new Set(ALLOWED.map(named));
export const PROBES: readonly Probe[] = PROBED.filter((p) => !allowed.has(named(p)));

const collectionOf = (path: string): string => path.slice(0, path.lastIndexOf("/"));
export const collectionIdOf = (path: string): string => collectionOf(path).split("/").at(-1) ?? "";

const REQUESTS: Record<Op, (db: Db, path: string) => Promise<unknown>> = {
    get: (db, path) => db.doc(path).get(),
    list: (db, path) => db.collection(collectionOf(path)).get(),
    group: (db, path) => db.collectionGroup(collectionIdOf(path)).get(),
    create: (db, path) => db.doc(path).set({ name: "y", ownerUid: UID, deleted: false }),
    update: (db, path) => db.doc(path).update({ name: "z" }),
    delete: (db, path) => db.doc(path).delete(),
};

// One probe, self-contained: `admin` (rules off) seeds the document, or removes it for create; then
// the client asks.
export async function attempt(admin: Db, db: Db, probe: Probe): Promise<unknown> {
    const ref = admin.doc(probe.path);
    await (probe.op === "create" ? ref.delete() : ref.set({ name: "seed" }));
    return REQUESTS[probe.op](db, probe.path);
}

export type Outcome = "allowed" | "denied";

// M1-08 (PLAN 3.1 "Signed in"): every rule but the own users doc's and config/app's needs a verified
// email. One request, twice, in the world the test seeded: unverified first, which must be denied (a
// denied request writes nothing), then verified, which must be allowed, so it cannot pass vacuously.
// Verified first would be vacuous for a create or delete: the second request would meet a new world.
export async function verifiedOnly(
    clients: Record<Client, Db>,
    request: (db: Db) => Promise<unknown>,
): Promise<void> {
    await assertFails(request(clients.unverified));
    await assertSucceeds(request(clients.verified));
}

// The allow statements of a rules text, each with the path of its match blocks, and the paths of each
// `function signedIn`. A comment becomes a space and a string (escapes included) ''. It fails closed:
// a quote, a brace, a match path of other than plain segments or an allow statement not ended by its
// own ; before any brace is left unread, and then it throws (R2-01 to R3-04).
function parseRules(rules: string): {
    allows: { path: string; condition: string }[];
    signedIn: string[];
} {
    const code = rules.replace(
        /\/\/[^\n]*|\/\*[\s\S]*?\*\/|'(?:[^'\\\n]|\\.)*'|"(?:[^"\\\n]|\\.)*"/g,
        (m) => (m.startsWith("/") ? " " : "''"),
    );
    const stack: string[] = [];
    const allows: { path: string; condition: string }[] = [];
    const signedIn: string[] = [];
    let matches = 0;
    for (const m of code.matchAll(
        /\bmatch\s*((?:\/(?:\{\w+(?:=\*\*)?\}|[^\s/{}]+))+)\s*\{|\ballow\b[^:;{}]*(?::\s*if\b([^;{}]*))?;|\bfunction\s+signedIn\b|[{}]/g,
    )) {
        if (m[1] !== undefined) {
            stack.push(m[1]);
            matches += 1;
        } else if (m[0].startsWith("allow")) {
            allows.push({
                path: stack.join(""),
                condition: (m[2] ?? "").replace(/\s+/g, " ").trim(),
            });
        } else if (m[0].startsWith("function")) signedIn.push(stack.join(""));
        else if (m[0] === "{") stack.push("");
        else if (stack.pop() === undefined) throw new Error("rules: a } without its {");
    }
    const words = (word: RegExp): number => (code.match(word) ?? []).length;
    const unread =
        allows.length !== words(/\ballow\b/g) ||
        matches !== words(/\bmatch\b/g) ||
        /['"]/.test(code.replaceAll("''", ""));
    if (stack.length > 0 || unread) {
        throw new Error(
            "rules: a quote, match, allow statement or brace that parseRules cannot read",
        );
    }
    return { allows, signedIn };
}

// signedIn() is a conjunct of the whole condition: its first term, and no || or ?: outside
// parentheses (both bind more loosely than &&).
function requiresSignedIn(condition: string): boolean {
    if (!/^signedIn\(\)\s*(&&|$)/.test(condition)) return false;
    let depth = 0;
    for (const ch of condition) {
        if (ch === "(") depth += 1;
        else if (ch === ")") depth -= 1;
        else if (depth === 0 && (ch === "|" || ch === "?")) return false;
    }
    return true;
}

// M1-08, so a new rule cannot forget signedIn(): outside the own users doc and config/app (PLAN 3.1),
// each allow statement that does not require it, as `path: condition`; and signedIn() itself unless it
// is declared exactly once, at the documents level, so that no match can redefine it (S1-01).
const DOCUMENTS = "/databases/{database}/documents";
const WITHOUT_SIGN_IN = [`${DOCUMENTS}/users/{uid}`, `${DOCUMENTS}/config/app`];
export function withoutSignedIn(rules: string): string[] {
    const { allows, signedIn } = parseRules(rules);
    const missing = allows
        .filter((s) => !WITHOUT_SIGN_IN.includes(s.path) && !requiresSignedIn(s.condition))
        .map((s) => `${s.path}: ${s.condition}`);
    if (signedIn.length === 1 && signedIn[0] === DOCUMENTS) return missing;
    const found = signedIn.map((path) => path || "the service block").join(", ") || "none";
    return [...missing, `signedIn() must be declared once, at ${DOCUMENTS}; found: ${found}`];
}

// "denied" only for a permission-denied error; any other error is thrown, so a broken probe never
// counts as denied.
export async function outcome(request: Promise<unknown>): Promise<Outcome> {
    try {
        await request;
    } catch (e) {
        if (e instanceof Error && "code" in e && e.code === "permission-denied") return "denied";
        throw e;
    }
    return "allowed";
}

// Whom a mutant lets in, and the rules condition that lets in exactly them.
export const WHO: Record<"everyone" | Client, string> = {
    everyone: "true",
    anonymous: "request.auth == null",
    unverified: "request.auth != null && request.auth.token.email_verified == false",
    verified: "request.auth != null && request.auth.token.email_verified == true",
};
// "others" and "self": signed-in callers on other users' documents of a {uid} collection, or their own.
export type Who = keyof typeof WHO | "others" | "self";
export const METHODS = ["get", "list", "create", "update", "delete"] as const;
export type Method = (typeof METHODS)[number];

// A mutant opens one collection to `who` for `methods`: all of it (every document id a variable, so
// `config/app` opens `config`) or, with group, that collection id at any depth, as a collection-group
// query needs.
export interface Mutant {
    readonly template: string;
    readonly group: boolean;
    readonly who: Who;
    readonly methods: readonly Method[];
}

// A collection opened to everyone, to each client alone and (a {uid} collection) to others and to self,
// and its collection group to everyone.
export function mutantsOf(template: string): Mutant[] {
    const whos: Who[] = ["everyone", ...CLIENT_NAMES];
    if (template.endsWith("/{uid}")) whos.push("others", "self");
    return [
        ...whos.map((who) => ({ template, group: false, who, methods: METHODS })),
        { template, group: true, who: "everyone", methods: METHODS },
    ];
}

// A collection opened to everyone one method at a time: each probe must use the method it is named for.
export function methodMutants(template: string): Mutant[] {
    return [
        ...METHODS.map((m): Mutant => ({ template, group: false, who: "everyone", methods: [m] })),
        { template, group: true, who: "everyone", methods: ["list"] },
    ];
}

export const wholeCollection = (template: string): string =>
    template
        .split("/")
        .map((s, i) => (i % 2 === 1 ? `{d${String(i)}}` : s))
        .join("/");

export const matchOf = (m: Mutant): string =>
    m.group ? `/{path=**}/${collectionIdOf(m.template)}/{doc}` : `/${wholeCollection(m.template)}`;

const ANCHOR = "match /databases/{database}/documents {";

// The rules with `block` as the first statements under the documents match (a mutant, or the spike's
// blocks of M1-09).
export function underDocuments(rules: string, block: string): string {
    const at = rules.indexOf(ANCHOR);
    if (at < 0 || rules.includes(ANCHOR, at + 1)) throw new Error(`need exactly one "${ANCHOR}"`);
    const end = at + ANCHOR.length;
    return `${rules.slice(0, end)}${block}${rules.slice(end)}`;
}

// The rules with the mutant's block as the first statement under the documents match.
export function mutate(rules: string, m: Mutant): string {
    const doc = `d${String(m.template.split("/").length - 1)}`;
    const who =
        m.who === "others" || m.who === "self"
            ? `request.auth != null && request.auth.uid ${m.who === "self" ? "==" : "!="} ${doc}`
            : WHO[m.who];
    const allow = `allow ${m.methods.join(", ")}: if ${who};`;
    return underDocuments(rules, `\n    match ${matchOf(m)} {\n      ${allow}\n    }`);
}

// What a probe gets under a mutant, as Firestore decides: an exact match opens the documents of its
// collection and queries on it, not a collection-group query (a list); a group match opens all three.
// A rule on the document id (others, self) opens no query, since it cannot hold for every result.
export function expected(m: Mutant, p: Probe): Outcome {
    const opened = m.group
        ? collectionIdOf(p.path) === collectionIdOf(m.template)
        : p.op !== "group" && wholeCollection(p.path) === wholeCollection(m.template);
    const own = p.path.split("/").at(-1) === UID;
    const lets =
        m.who === "others" || m.who === "self"
            ? p.client !== "anonymous" && p.op !== "list" && own === (m.who === "self")
            : m.who === "everyone" || m.who === p.client;
    return opened && lets && m.methods.includes(p.op === "group" ? "list" : p.op)
        ? "allowed"
        : "denied";
}
