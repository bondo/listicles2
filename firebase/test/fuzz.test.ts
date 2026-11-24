import fc from "fast-check";
import { BASES, build, cases, EXTENSIONS, fuzz, type Case } from "./fuzz";
import * as h from "./harness";
import * as m from "./model";

// M1-06 (P17): the rules fuzz (fuzz.ts) against the reference model of PLAN 3.1 (model.ts). The
// fuzz runs the base case of every template, then RUNS random cases on a new seed each time. To
// replay a failure, set FUZZ_SEED and FUZZ_PATH to the seed and path it prints; FUZZ_RUNS raises
// the number of random cases (never below RUNS).
const RUNS = 1000;
jest.setTimeout(300_000);

const ROWS = Object.entries(m.ROWS)
    .flatMap(([path, row]) => Object.keys(row).map((method) => `${path} ${method}`))
    .sort();

// A rule without a row, or a row without a rule, fails here: the model follows the rules.
test("the model has a row for each method an allow statement of firestore.rules grants", () => {
    expect(ROWS).toEqual(h.allowedMethods(h.RULES));
});

test("the row check sees a rule the model lacks and a row the rules lack", () => {
    const invites = h.underDocuments(h.RULES, "match /invites/{code} { allow read: if false; }");
    expect(h.allowedMethods(invites)).toEqual(
        [...ROWS, "invites/{code} get", "invites/{code} list"].sort(),
    );
    const noList = h.RULES.replace("allow list: if signedIn() && readsMembers(hid);", "");
    expect(h.allowedMethods(noList)).toEqual(ROWS.filter((r) => !r.endsWith("{uid} list")));
});

// A row template's base case is a request PLAN 3.1 allows; an extension point's is denied until
// its task adds the path to the rules and the model.
test.each(BASES)("the model on the base case of $template", (c) => {
    const { world, caller, request } = build(c);
    const want = EXTENSIONS.includes(c.template) ? "denied" : "allowed";
    expect(m.decide(world, caller, request)).toBe(want);
});

// Not vacuous: in a sample of the cases each row allows a request that is allowed and each row
// that can deny (all but config/app's) denies one, so a new row needs a template (fuzz.ts).
test("in a sample of the cases every row allows and denies", () => {
    const met = new Set<string>();
    for (const c of fc.sample(cases, { seed: 1, numRuns: 3000 })) {
        const { world, caller, request } = build(c);
        const rows = m.explain(world, caller, request);
        const allowed = rows.every((r) => r.allowed);
        for (const r of rows) if (r.allowed === allowed) met.add(`${r.row} ${String(allowed)}`);
    }
    const want = ROWS.flatMap((r) => [`${r} true`, `${r} false`]);
    expect(want.filter((w) => !met.has(w))).toEqual(["config/app get false"]);
});

test("the emulator and the model agree on every case", async () => {
    const { FUZZ_SEED: seed, FUZZ_PATH: path, FUZZ_RUNS: runs } = process.env;
    const examples = BASES.map((c): [Case] => [c]);
    const numRuns = Math.max(RUNS, Number(runs) || 0);
    await fuzz(h.RULES, { numRuns, examples, ...(seed ? { seed: Number(seed), path } : {}) });
});

// The negative case (P17): each mutant weakens one condition of firestore.rules, so the rules
// allow a case the model denies, which the fuzz must find (on a fixed seed, so it is stable).
const MUTANTS: [string, string, string][] = [
    ["Signed in without a verified email", "token.email_verified == true", "token != null"],
    ["Create household: any id (P3)", "hid.matches('^[A-Za-z0-9]{20}$')\n        && ", ""],
    ["users doc: from one household to another (P5)", "(before == null && after", "(after"],
    ["Display name: any value (P4)", "&& validName(doc.displayName))", ")"],
    ["Member reads under a tombstone (LIVE)", "return household.deleted == false && ", "return "],
    ["Transfer: the old owner keeps the role (two owners)", "role == 'member'", "role != null"],
];

test.each(MUTANTS)("the fuzz finds the mutant: %s", async (_what, from, to) => {
    const rules = h.RULES.replace(from, to);
    expect(rules).not.toBe(h.RULES);
    const run = fuzz(rules, { seed: 1, numRuns: RUNS, endOnFailure: true });
    await expect(run).rejects.toThrow("the emulator says allowed, the model denied");
});
