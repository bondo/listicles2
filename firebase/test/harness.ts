import * as fs from "node:fs";
import * as path from "node:path";
import {
    type RulesTestContext,
    type RulesTestEnvironment,
    type TokenOptions,
} from "@firebase/rules-unit-testing";

// The default-deny harness (M1-52, see #202): every client tries every operation on the caller's own
// document of every collection in PLAN section 3, on another user's of each {uid} one, and on the
// unplanned paths. rules.test.ts expects each probe to be denied; mutants.test.ts shows that opening
// any one of those collections turns that suite red.
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
const UID = "alice";
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
// of every planned document, which a recursive or wildcard match there would open (#199).
export const UNPLANNED_ROOT = "anything/{doc}";
export const UNPLANNED = [UNPLANNED_ROOT, ...TEMPLATES.map((t) => `${t}/unplanned/{doc}`)];
// The caller's own document of every template, another user's (bob) of each {uid} one, and the unplanned.
export const PATHS = [
    ...TEMPLATES.map((t) => instantiate(t)),
    ...TEMPLATES.filter((t) => t.endsWith("/{uid}")).map((t) => instantiate(t, OTHER)),
    ...UNPLANNED.map((t) => instantiate(t)),
];

const token = (emailVerified: boolean): TokenOptions => ({
    email: `${UID}@example.com`,
    email_verified: emailVerified,
    firebase: { sign_in_provider: "password" },
});

// Signed out, signed in with an unverified email (PLAN 3.1 "Signed in"), and signed in and verified.
export const CLIENT_NAMES = ["anonymous", "unverified", "verified"] as const;
export type Client = (typeof CLIENT_NAMES)[number];

export function connect(env: RulesTestEnvironment): Record<Client, Db> {
    return {
        anonymous: env.unauthenticatedContext().firestore(),
        unverified: env.authenticatedContext(UID, token(false)).firestore(),
        verified: env.authenticatedContext(UID, token(true)).firestore(),
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

export const PROBES: readonly Probe[] = PATHS.flatMap((path) =>
    OPS.flatMap((op) => CLIENT_NAMES.map((client) => ({ client, op, path }))),
);

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

// The rules with the mutant's block as the first statement under the documents match.
export function mutate(rules: string, m: Mutant): string {
    const at = rules.indexOf(ANCHOR);
    if (at < 0 || rules.includes(ANCHOR, at + 1)) throw new Error(`need exactly one "${ANCHOR}"`);
    const end = at + ANCHOR.length;
    const doc = `d${String(m.template.split("/").length - 1)}`;
    const who =
        m.who === "others" || m.who === "self"
            ? `request.auth != null && request.auth.uid ${m.who === "self" ? "==" : "!="} ${doc}`
            : WHO[m.who];
    const allow = `allow ${m.methods.join(", ")}: if ${who};`;
    return `${rules.slice(0, end)}\n    match ${matchOf(m)} {\n      ${allow}\n    }${rules.slice(end)}`;
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
