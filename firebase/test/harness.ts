import * as fs from "node:fs";
import * as path from "node:path";
import { type RulesTestContext, type RulesTestEnvironment } from "@firebase/rules-unit-testing";

// The default-deny harness (M1-52, see #202): every client tries every operation on one document of every
// collection in PLAN section 3 and on one unplanned path. rules.test.ts expects each probe to be denied;
// mutants.test.ts shows that opening any one of those collections turns that suite red.

// The rules-unit-testing contexts hand out the compat Firestore type, so the harness uses the compat calls
// (doc().get(), set(), update(), delete(), collection().get(), collectionGroup().get()): the same operations
// as the modular getDoc, setDoc, updateDoc, deleteDoc and getDocs, with no type casts.
export type Db = ReturnType<RulesTestContext["firestore"]>;

const read = (...parts: string[]): string =>
    fs.readFileSync(path.join(__dirname, ...parts), "utf8");
export const RULES = read("..", "firestore.rules");
export const PLAN = read("..", "..", "docs", "PLAN.md");
// Both test files load their rules into this one emulator project, which is why `npm test` runs Jest
// with --runInBand (scripts/test_firebase_ts.py checks it): one file at a time.
export const PROJECT = "demo-tally";

const UID = "alice";

// Every planned top-level and nested path (rules.test.ts checks this against PLAN both ways), and one path that
// no rule plans, which only the default deny covers.
export const PLANNED = [
    "users/alice",
    "households/h1",
    "households/h1/members/alice",
    "households/h1/lists/l1",
    "households/h1/lists/l1/items/i1",
    "households/h1/invites/inv1",
];
export const UNPLANNED = "anything/else";
export const PATHS = [...PLANNED, UNPLANNED];

export const CLIENT_NAMES = ["anonymous", "signed-in"] as const;
export type Client = (typeof CLIENT_NAMES)[number];

export function connect(env: RulesTestEnvironment): Record<Client, Db> {
    return {
        anonymous: env.unauthenticatedContext().firestore(),
        "signed-in": env.authenticatedContext(UID).firestore(),
    };
}

// The document operations, a query on its collection and a collection-group query on its collection id.
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

export function collectionOf(path: string): string {
    return path.slice(0, path.lastIndexOf("/"));
}

export function collectionIdOf(path: string): string {
    const collection = collectionOf(path);
    return collection.slice(collection.lastIndexOf("/") + 1);
}

const REQUESTS: Record<Op, (db: Db, path: string) => Promise<unknown>> = {
    get: (db, path) => db.doc(path).get(),
    list: (db, path) => db.collection(collectionOf(path)).get(),
    group: (db, path) => db.collectionGroup(collectionIdOf(path)).get(),
    create: (db, path) => db.doc(path).set({ name: "y", ownerUid: UID, deleted: false }),
    update: (db, path) => db.doc(path).update({ name: "z" }),
    delete: (db, path) => db.doc(path).delete(),
};

// One probe, self-contained: `admin` (a context with rules off) seeds the document, or removes it for create,
// then the client asks.
export async function attempt(admin: Db, db: Db, probe: Probe): Promise<unknown> {
    const ref = admin.doc(probe.path);
    await (probe.op === "create" ? ref.delete() : ref.set({ name: "seed" }));
    return REQUESTS[probe.op](db, probe.path);
}

export type Outcome = "allowed" | "denied";

// "denied" only for a permission-denied error; any other error is thrown, so a broken probe never counts
// as denied.
export async function outcome(request: Promise<unknown>): Promise<Outcome> {
    try {
        await request;
    } catch (e) {
        if (e instanceof Error && "code" in e && e.code === "permission-denied") return "denied";
        throw e;
    }
    return "allowed";
}

// The collection templates of the data-model block in PLAN section 3: the first word of each unindented
// line (`users/{uid}`, `config/app`). A missing block, no line or a word that is not a document path throws,
// so a changed PLAN layout cannot make the PLAN check pass with fewer collections.
export function planTemplates(plan: string): string[] {
    const block = /^## 3\. Data model \(Firestore\)\n+```\n([\s\S]*?)\n```/m.exec(plan)?.[1];
    if (block === undefined) throw new Error("PLAN section 3 has no data-model block");
    const templates = block
        .split("\n")
        .filter((line) => /^\S/.test(line))
        .map((line) => line.split(/\s/)[0] ?? "");
    const bad = templates.filter(
        (t) => !/^[\w{}-]+(\/[\w{}-]+)*$/.test(t) || t.split("/").length % 2 === 1,
    );
    if (templates.length === 0 || bad.length > 0) {
        throw new Error(`PLAN section 3: no collections, or not document paths: ${bad.join(", ")}`);
    }
    return templates;
}

// Whether a path is a document of a template: the same collection ids, and any id where the template has
// a {variable}.
export function matches(template: string, path: string): boolean {
    const t = template.split("/");
    const p = path.split("/");
    return (
        t.length === p.length &&
        t.every((s, i) => (/^\{\w+\}$/.test(s) && (p[i] ?? "") !== "") || s === p[i])
    );
}

// What keeps PLANNED from holding exactly one document of each PLAN template, or UNPLANNED from being
// unplanned.
export function pathProblems(
    templates: readonly string[],
    planned: readonly string[],
    unplanned: string,
): string[] {
    const problems = templates.length === 0 ? ["PLAN section 3 names no collection"] : [];
    for (const t of templates) {
        const n = planned.filter((p) => matches(t, p)).length;
        if (n !== 1) problems.push(`${t}: ${String(n)} documents in PLANNED, expected 1`);
    }
    for (const p of planned) {
        if (!templates.some((t) => matches(t, p))) problems.push(`${p} is not in PLAN section 3`);
    }
    if (templates.some((t) => matches(t, unplanned))) problems.push(`${unplanned} is planned`);
    return problems;
}

// Whom a mutant opens a collection to: its rules condition and the clients that condition lets in.
export interface Audience {
    readonly name: string;
    readonly condition: string;
    readonly clients: readonly string[];
}

export const EVERYONE: Audience = { name: "everyone", condition: "true", clients: CLIENT_NAMES };
export const AUDIENCES: readonly Audience[] = [
    EVERYONE,
    { name: "anonymous", condition: "request.auth == null", clients: ["anonymous"] },
    {
        name: "unverified",
        condition: "request.auth != null && request.auth.token.email_verified == false",
        clients: ["unverified"],
    },
    {
        name: "verified",
        condition: "request.auth != null && request.auth.token.email_verified == true",
        clients: ["verified"],
    },
];

// The rules methods, and the one each probe needs (a collection-group query is a list).
export const METHODS = ["get", "list", "create", "update", "delete"] as const;
export type Method = (typeof METHODS)[number];
const METHOD_OF: Record<Op, Method> = {
    get: "get",
    list: "list",
    group: "list",
    create: "create",
    update: "update",
    delete: "delete",
};

// A mutant opens one collection for some methods: all of it (every document id a variable, so `config/app`
// opens `config`) or, with group, every collection with that id at any depth, as a collection-group query needs.
export interface Mutant {
    readonly template: string;
    readonly group: boolean;
    readonly audience: Audience;
    readonly methods: readonly Method[];
}

// Each collection opened to each audience, and its collection group to everyone.
export function mutantsOf(templates: readonly string[]): Mutant[] {
    return templates.flatMap((template) => [
        ...AUDIENCES.map((audience) => ({ template, group: false, audience, methods: METHODS })),
        { template, group: true, audience: EVERYONE, methods: METHODS },
    ]);
}

// One collection opened to everyone for one method at a time, so each probe must use the method it is named for.
export function methodMutants(template: string): Mutant[] {
    return [
        ...METHODS.map((method) => ({
            template,
            group: false,
            audience: EVERYONE,
            methods: [method],
        })),
        { template, group: true, audience: EVERYONE, methods: ["list"] },
    ];
}

const wholeCollection = (template: string): string =>
    template
        .split("/")
        .map((s, i) => (i % 2 === 1 ? `{d${String(i)}}` : s))
        .join("/");

export function matchOf(mutant: Mutant): string {
    return mutant.group
        ? `/{path=**}/${collectionIdOf(mutant.template)}/{doc}`
        : `/${wholeCollection(mutant.template)}`;
}

const ANCHOR = "match /databases/{database}/documents {";

// The rules with the mutant's open match block added as the first statement under the documents match.
export function mutate(rules: string, mutant: Mutant): string {
    const at = rules.indexOf(ANCHOR);
    if (at < 0 || rules.includes(ANCHOR, at + 1)) throw new Error(`need exactly one "${ANCHOR}"`);
    const end = at + ANCHOR.length;
    const allow = `allow ${mutant.methods.join(", ")}: if ${mutant.audience.condition};`;
    const block = `\n    match ${matchOf(mutant)} {\n      ${allow}\n    }`;
    return rules.slice(0, end) + block + rules.slice(end);
}

// What a probe gets under a mutant, as Firestore decides it: an exact match opens the documents of its
// collection and queries on it, not a collection-group query; a group match opens all three.
export function expected(mutant: Mutant, probe: Probe): Outcome {
    const opened = mutant.group
        ? collectionIdOf(probe.path) === collectionIdOf(mutant.template)
        : probe.op !== "group" && matches(wholeCollection(mutant.template), probe.path);
    const lets = mutant.audience.clients.includes(probe.client);
    return opened && lets && mutant.methods.includes(METHOD_OF[probe.op]) ? "allowed" : "denied";
}
