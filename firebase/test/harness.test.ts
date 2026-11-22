import * as h from "./harness";

// Negative cases for the harness itself (no emulator): each check fails on the input it exists to catch.

const SAMPLE = `## 3. Data model (Firestore)

\`\`\`
users/{uid}         { householdId }   // a note
lists/{lid}         { kind,
                      name }
config/app          { minVersionCode }
\`\`\``;

test("planTemplates reads the first word of every unindented line of the data-model block", () => {
    expect(h.planTemplates(SAMPLE)).toEqual(["users/{uid}", "lists/{lid}", "config/app"]);
});

test.each([
    ["no data-model block", "## 3. Data model (Firestore)\n\nno block\n"],
    ["an empty block", "## 3. Data model (Firestore)\n\n```\n\n```\n"],
    ["a collection path", SAMPLE.replace("config/app", "config")],
    ["a word that is no path", SAMPLE.replace("config/app", "//")],
])("planTemplates throws on %s", (_name, plan) => {
    expect(() => h.planTemplates(plan)).toThrow();
});

test("instantiate gives each variable the id of its name and throws on an unknown name", () => {
    expect(h.instantiate("lists/{lid}/items/{iid}")).toBe("lists/l1/items/i1");
    expect(h.instantiate("config/app")).toBe("config/app");
    expect(h.instantiate("users/{uid}/unplanned/{doc}", { uid: "bob", doc: "x" })).toBe(
        "users/bob/unplanned/x",
    );
    expect(() => h.instantiate("lists/{xid}")).toThrow("{xid}");
});

test("mutants: each audience, the collection group, and one method at a time", () => {
    const all = h.METHODS.join(",");
    const names = [...h.mutantsOf("a/{b}"), ...h.methodMutants("a/{b}")].map(
        (m) => `${m.methods.join(",")} ${h.matchOf(m)} ${m.who}`,
    );
    expect(names).toEqual([
        `${all} /a/{d1} everyone`,
        `${all} /a/{d1} anonymous`,
        `${all} /a/{d1} unverified`,
        `${all} /a/{d1} verified`,
        `${all} /{path=**}/a/{doc} everyone`,
        "get /a/{d1} everyone",
        "list /a/{d1} everyone",
        "create /a/{d1} everyone",
        "update /a/{d1} everyone",
        "delete /a/{d1} everyone",
        "list /{path=**}/a/{doc} everyone",
    ]);
    expect(h.mutantsOf("a/{uid}").map((m) => m.who)).toEqual([
        "everyone",
        "anonymous",
        "unverified",
        "verified",
        "others",
        "self",
        "everyone",
    ]);
});

const exact: h.Mutant = {
    template: "lists/{lid}/items/{iid}",
    group: false,
    who: "everyone",
    methods: h.METHODS,
};
const group: h.Mutant = { ...exact, group: true };

test("mutate adds one block right under the documents match and changes nothing else", () => {
    const anchor = "match /databases/{database}/documents {";
    const block = "\n    match /{path=**}/items/{doc} {\n      allow list: if true;\n    }";
    const mutated = h.mutate(h.RULES, { ...group, methods: ["list"] });
    expect(mutated).toContain(anchor + block);
    expect(mutated.replace(block, "")).toBe(h.RULES);
    expect(() => h.mutate(h.RULES.replace(anchor, "match /x {"), exact)).toThrow();
    expect(() => h.mutate(`${h.RULES}\n${anchor}`, exact)).toThrow();
});

const others: h.Mutant = { ...exact, template: "users/{uid}", who: "others" };
const self: h.Mutant = { ...others, who: "self" };
const [first, second] = h.CLIENT_NAMES;
const probe = (op: h.Op, client: h.Client = first, path = "lists/l1/items/i1"): h.Probe => ({
    client,
    op,
    path,
});
const cases: [string, h.Mutant, h.Probe, h.Outcome][] = [
    ["exact, a document", exact, probe("get"), "allowed"],
    ["exact, a query on the collection", exact, probe("list"), "allowed"],
    ["exact, no collection-group query", exact, probe("group"), "denied"],
    ["group, the collection-group query", group, probe("group"), "allowed"],
    ["exact, another collection", exact, probe("get", first, "lists/l1"), "denied"],
    ["one client, that client", { ...exact, who: first }, probe("get", first), "allowed"],
    ["one client, another client", { ...exact, who: first }, probe("get", second), "denied"],
    ["list only, a query", { ...exact, methods: ["list"] }, probe("list"), "allowed"],
    ["list only, a get", { ...exact, methods: ["list"] }, probe("get"), "denied"],
    ["create only, an update", { ...exact, methods: ["create"] }, probe("update"), "denied"],
    ["others, another user's document", others, probe("get", "verified", "users/bob"), "allowed"],
    ["others, an unverified caller", others, probe("create", "unverified", "users/bob"), "allowed"],
    [
        "others, the caller's own document",
        others,
        probe("get", "verified", "users/alice"),
        "denied",
    ],
    ["others, a signed-out caller", others, probe("get", "anonymous", "users/bob"), "denied"],
    ["others, a query", others, probe("list", "verified", "users/bob"), "denied"],
    ["self, the caller's own document", self, probe("get", "verified", "users/alice"), "allowed"],
    ["self, an unverified caller", self, probe("delete", "unverified", "users/alice"), "allowed"],
    ["self, another user's document", self, probe("get", "verified", "users/bob"), "denied"],
    ["self, a signed-out caller", self, probe("get", "anonymous", "users/alice"), "denied"],
    ["self, a query", self, probe("list", "verified", "users/alice"), "denied"],
];

test.each(cases)("expected: %s", (_name, mutant, p, want) => {
    expect(h.expected(mutant, p)).toBe(want);
});

test("a collection no probe touches has no killing probe, so the mutant check fails on it", () => {
    const mutants = [...h.mutantsOf("nowhere/{id}"), ...h.methodMutants("nowhere/{id}")];
    expect(mutants.flatMap((m) => h.PROBES.filter((p) => h.expected(m, p) === "allowed"))).toEqual(
        [],
    );
});

test("outcome: allowed, denied for permission-denied only, and any other error thrown", async () => {
    const error = (code: string): Error => Object.assign(new Error(code), { code });
    await expect(h.outcome(Promise.resolve())).resolves.toBe("allowed");
    await expect(h.outcome(Promise.reject(error("permission-denied")))).resolves.toBe("denied");
    await expect(h.outcome(Promise.reject(error("not-found")))).rejects.toThrow("not-found");
    await expect(h.outcome(Promise.reject(new Error("permission-denied")))).rejects.toThrow();
});
