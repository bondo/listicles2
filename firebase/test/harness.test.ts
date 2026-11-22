import {
    type Audience,
    type Client,
    CLIENT_NAMES,
    EVERYONE,
    expected,
    matches,
    matchOf,
    METHODS,
    methodMutants,
    type Mutant,
    mutantsOf,
    mutate,
    type Op,
    outcome,
    pathProblems,
    planTemplates,
    type Probe,
    PROBES,
    RULES,
} from "./harness";

// Negative cases for the harness itself (no emulator): each check fails on the input it exists to catch.

const SAMPLE = [
    "## 3. Data model (Firestore)",
    "",
    "```",
    "users/{uid}         { householdId }   // a note",
    "lists/{lid}         { kind,",
    "                      name }",
    "config/app          { minVersionCode }",
    "```",
].join("\n");

describe("planTemplates", () => {
    test("reads the first word of every unindented line of the data-model block", () => {
        expect(planTemplates(SAMPLE)).toEqual(["users/{uid}", "lists/{lid}", "config/app"]);
    });

    test.each([
        ["no data-model block", "## 3. Data model (Firestore)\n\nno block\n"],
        ["an empty block", "## 3. Data model (Firestore)\n\n```\n\n```\n"],
        ["a collection path", SAMPLE.replace("config/app", "config")],
        ["a word that is no path", SAMPLE.replace("config/app", "//")],
    ])("throws on %s", (_name, plan) => {
        expect(() => planTemplates(plan)).toThrow();
    });
});

describe("pathProblems", () => {
    const templates = ["users/{uid}", "households/{hid}/removed/{uid}", "config/app"];
    const planned = ["users/alice", "households/h/removed/alice", "config/app"];

    test("accepts one document per template and an unplanned path", () => {
        expect(pathProblems(templates, planned, "anything/else")).toEqual([]);
    });

    test.each([
        ["a missing collection", templates, planned.slice(1), "anything/else", "users/{uid}: 0"],
        [
            "a stale path",
            templates,
            [...planned, "households/h/lists/l1"],
            "anything/else",
            "lists/l1 is",
        ],
        [
            "two documents of one collection",
            templates,
            [...planned, "users/bob"],
            "anything/else",
            ": 2",
        ],
        [
            "another id under a literal",
            templates,
            ["config/x", ...planned.slice(0, 2)],
            "a/b",
            "config/x is",
        ],
        ["a planned UNPLANNED", templates, planned, "users/bob", "users/bob is planned"],
        ["no template at all", [], [], "anything/else", "PLAN section 3 names no collection"],
    ])("reports %s", (_name, t, p, unplanned, problem) => {
        expect(pathProblems(t, p, unplanned).join("\n")).toContain(problem);
    });

    test("matches needs the same collection ids and depth", () => {
        expect(matches("lists/{lid}/items/{iid}", "lists/l1/items/i1")).toBe(true);
        expect(matches("lists/{lid}/items/{iid}", "households/h/lists/l1/items/i1")).toBe(false);
        expect(matches("lists/{lid}", "lists/")).toBe(false);
        expect(matches("config/app", "config/other")).toBe(false);
    });
});

describe("mutants", () => {
    const exact: Mutant = {
        template: "lists/{lid}/items/{iid}",
        group: false,
        audience: EVERYONE,
        methods: METHODS,
    };
    const group: Mutant = { ...exact, group: true };
    const anchor = "match /databases/{database}/documents {";
    const name = (m: Mutant): string => `${m.methods.join(",")} ${matchOf(m)} ${m.audience.name}`;
    const [first, second] = CLIENT_NAMES;
    const probe = (op: Op, client: Client = first, path = "lists/l1/items/i1"): Probe => ({
        client,
        op,
        path,
    });

    test("each collection is opened to every audience, and its collection group to everyone", () => {
        const all = METHODS.join(",");
        expect(mutantsOf(["a/{b}"]).map(name)).toEqual([
            `${all} /a/{d1} everyone`,
            `${all} /a/{d1} anonymous`,
            `${all} /a/{d1} unverified`,
            `${all} /a/{d1} verified`,
            `${all} /{path=**}/a/{doc} everyone`,
        ]);
        expect(matchOf({ ...exact, template: "config/app" })).toBe("/config/{d1}");
    });

    test("the method mutants open one method at a time, and the collection group for list", () => {
        expect(methodMutants("a/{b}").map(name)).toEqual([
            "get /a/{d1} everyone",
            "list /a/{d1} everyone",
            "create /a/{d1} everyone",
            "update /a/{d1} everyone",
            "delete /a/{d1} everyone",
            "list /{path=**}/a/{doc} everyone",
        ]);
    });

    test("mutate adds one open block right under the documents match and changes nothing else", () => {
        const block = "\n    match /{path=**}/items/{doc} {\n      allow list: if true;\n    }";
        const mutated = mutate(RULES, { ...group, methods: ["list"] });
        expect(mutated).toContain(anchor + block);
        expect(mutated.replace(block, "")).toBe(RULES);
    });

    test.each([
        ["no documents match", RULES.replace(anchor, "match /databases/{database}/x {")],
        ["two documents matches", `${RULES}\n${anchor}`],
    ])("mutate throws when the rules have %s", (_name, rules) => {
        expect(() => mutate(rules, exact)).toThrow();
    });

    test("expected follows Firestore: exact opens documents and queries, group also the group query", () => {
        expect(expected(exact, probe("get"))).toBe("allowed");
        expect(expected(exact, probe("list"))).toBe("allowed");
        expect(expected(exact, probe("group"))).toBe("denied");
        expect(expected(group, probe("group"))).toBe("allowed");
        expect(expected(exact, probe("get", first, "lists/l1"))).toBe("denied");
    });

    test("expected lets in only the audience's clients, for only the mutant's methods", () => {
        const firstOnly: Audience = { name: first, condition: "", clients: [first] };
        expect(expected({ ...exact, audience: firstOnly }, probe("get", first))).toBe("allowed");
        expect(expected({ ...exact, audience: firstOnly }, probe("get", second))).toBe("denied");
        const listOnly: Mutant = { ...exact, methods: ["list"] };
        expect(expected(listOnly, probe("list"))).toBe("allowed");
        expect(expected(listOnly, probe("get"))).toBe("denied");
        expect(expected({ ...group, methods: ["list"] }, probe("group"))).toBe("allowed");
        expect(expected({ ...exact, methods: ["create"] }, probe("update"))).toBe("denied");
    });

    test("a collection no probe touches has no killing probe, which fails the mutant check", () => {
        const mutants = [...mutantsOf(["nowhere/{id}"]), ...methodMutants("nowhere/{id}")];
        expect(mutants.flatMap((m) => PROBES.filter((p) => expected(m, p) === "allowed"))).toEqual(
            [],
        );
    });
});

describe("outcome", () => {
    const error = (code: string): Error => Object.assign(new Error(code), { code });

    test("is allowed for a success and denied for a permission-denied error", async () => {
        await expect(outcome(Promise.resolve())).resolves.toBe("allowed");
        await expect(outcome(Promise.reject(error("permission-denied")))).resolves.toBe("denied");
    });

    test("throws any other error, so a broken probe never counts as denied", async () => {
        await expect(outcome(Promise.reject(error("not-found")))).rejects.toThrow("not-found");
        await expect(outcome(Promise.reject(new Error("permission-denied")))).rejects.toThrow();
    });
});
