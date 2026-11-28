import fc from "fast-check";
import { BASES, build, cases, EXTENSIONS, fuzz, type Case } from "./fuzz";
import * as h from "./harness";
import * as m from "./model";

// M1-06 (P17): the rules fuzz (fuzz.ts) against the model of PLAN 3.1 (model.ts): the base case of
// every template, then RUNS random cases on a new seed each time. Replay a failure with FUZZ_SEED
// and FUZZ_PATH (it prints both); FUZZ_RUNS raises the number of random cases, never below RUNS.
const RUNS = 3000;
jest.setTimeout(Math.max(300_000, 50 * (Number(process.env.FUZZ_RUNS) || 0))); // 50 ms a case

const ROWS = Object.entries(m.ROWS)
    .flatMap(([path, row]) => Object.keys(row).map((method) => `${path} ${method}`))
    .sort();

// A rule without a row, or a row without a rule, fails here: the model follows the rules.
test("the model has a row for each method an allow statement of firestore.rules grants", () => {
    expect(ROWS).toEqual(h.allowedMethods(h.RULES));
});

test("the row check sees rules the model lacks (read, write) and a row the rules lack", () => {
    const added = h.underDocuments(h.RULES, "match /x/{id} { allow read, write: if false; }");
    const methods = ["get", "list", "create", "update", "delete"].map((k) => `x/{id} ${k}`);
    expect(h.allowedMethods(added)).toEqual([...ROWS, ...methods].sort());
    const noList = h.RULES.replace("allow list: if signedIn() && readsMembers(hid);", "");
    const members = "households/{hid}/members/{uid} list";
    expect(h.allowedMethods(noList)).toEqual(ROWS.filter((r) => r !== members));
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
// allow a case the model denies, which the fuzz must find. Measured again on the rules with both
// M1-90's blank names and M1-11's templates: seed 1 finds each within 1726 cases (M1-90's at
// 1228, and at 491 and 119 on seeds 2 and 3), seeds 2 and 3 within 8275; any of seeds 1 to 100
// found #372's within 8672 on #372's rules (PR #372 has the reach per seed; not measured again).
// All under the cap of 3 * RUNS.
const MUTANTS: [string, string, string][] = [
    ["Signed in without a verified email", "token.email_verified == true", "token != null"],
    ["Create household: an id of 21 characters (P3)", "{20}$", "{20,21}$"],
    ["users doc: from one household to another (P5)", "(before == null && after", "(after"],
    ["Display name: any value (P4)", "&& validName(doc.displayName))", ")"],
    ["Display name update: the role too (P4)", "['displayName'])", "['displayName', 'role'])"],
    [
        "Member reads under a tombstone (LIVE)",
        "(household.deleted == false && exists(memberDoc(hid, request.auth.uid)))\n        || cleansUp",
        "(exists(memberDoc(hid, request.auth.uid)))\n        || cleansUp",
    ],
    ["Transfer: the old owner keeps the role", "data.role == 'member'", "data.role != null"],
    ["Member doc: another uid (P1)", "uid == request.auth.uid && validName", "validName"],
    ["Household name: any length (P4)", "validName(data.name) &&", "data.name.trim() != '' &&"],
    [
        "Names: Unicode White_Space not blank, as trim() has it (P4, M1-90)",
        String.raw`\\x{85}\\x{A0}\\x{1680}\\x{2000}-\\x{200A}\\x{2028}\\x{2029}\\x{202F}\\x{205F}\\x{3000}`,
        "",
    ],
    ["Tombstone read: of a live household too", "household.deleted == true && get(", "get("],
    [
        "Invite list: all, by any member (#280)",
        "invite.createdBy == request.auth.uid ||",
        "true ||",
    ],
    ["Invite create: another household's code (P3)", "[0] == invite.householdId", "[0] != ''"],
    ["Invite create: a secret of 21 or 23 characters (P3)", "_-]{22}", "_-]{21,23}"],
    ["Invite create: an expiry up to 9 days ahead (HH-02)", "value(7, 'd')", "value(9, 'd')"],
    ["Invite cleanup under a tombstone (LIVE)", "time && household.deleted == false", "time"],
    [
        "Tombstone cleanup by anyone, not only its owner (O(uid))",
        "return household.deleted == true && household.ownerUid == request.auth.uid;",
        "return household.deleted == true;",
    ],
    ["Soft delete: the name kept (#205)", "after.name == ''", "after.name is string"],
    [
        "P6: another member's doc under a tombstone",
        "(uid == request.auth.uid && household.deleted",
        "(household.deleted",
    ],
    [
        "Invite delete: the expired cleanup by a non-member",
        "household.deleted == false\n          && exists(memberDoc(invite.householdId, request.auth.uid)))",
        "household.deleted == false)",
    ],
    ["Join: through an expired invite", "invite.expiresAt > request.time", "true"],
    ["Join: through another household's invite", "invite.householdId == hid && ", ""],
    ["Join: the invite not deleted (single use)", "&& !existsAfter(inviteDoc(code))", "&& true"],
    ["Join: through a former member's invite", "exists(memberDoc(hid, invite.createdBy))", "true"],
    [
        "Invite delete: a member whose doc names the code burns it",
        "&& !exists(memberDoc(invite.householdId, request.auth.uid))",
        "&& true",
    ],
    [
        "Invite delete: a joiner burns another invite in the join batch",
        ".data.viaInvite == code",
        ".data.viaInvite != null",
    ],
    [
        "Invite list: by a non-member who created them or owns the household",
        "uid)\n          && exists(memberDoc(invite.householdId, request.auth.uid)))",
        "uid))",
    ],
    ["Leave: by the owner (!O(uid))", "household.ownerUid != request.auth.uid", "true"],
    ["Leave: another member's doc", "(uid == request.auth.uid && resource", "(resource"],
    ["Leave: no member doc of the caller (M(uid))", "resource != null &&", ""],
    [
        "Remove member: the member delete without the marker",
        "getAfter(markerDoc(hid, uid)).data.removedAt == request.time",
        "true",
    ],
    [
        "Remove member: with a leftover marker",
        "getAfter(markerDoc(hid, uid)).data.removedAt == request.time",
        "getAfter(markerDoc(hid, uid)).data.removedAt != null",
    ],
    [
        "Remove member: the owner removes himself",
        "\n          && uid != household.ownerUid\n          && uid != getAfter(householdDoc(hid)).data.ownerUid",
        "",
    ],
    [
        "Marker: by a plain member (O(uid))",
        "household.ownerUid == request.auth.uid\n        && keys.hasOnly",
        "true\n        && keys.hasOnly",
    ],
    [
        "Marker: under a tombstone (LIVE)",
        "return household.deleted == false && household.ownerUid == request.auth.uid\n        && keys",
        "return household.ownerUid == request.auth.uid\n        && keys",
    ],
    ["Marker: another field (P4)", "keys.hasOnly(['removedAt'])", "true"],
    ["Marker: of a non-member (M(target))", "&& exists(memberDoc(hid, uid)) &&", "&&"],
    ["Marker: the target still a member", "&& !existsAfter(memberDoc(hid, uid))", ""],
    [
        "Markers: any member of the live household reads them (O(uid))",
        "(household.deleted == false && household.ownerUid == request.auth.uid)\n        || cleansUp",
        "(household.deleted == false)\n        || cleansUp",
    ],
];

// Each mutant's `from` occurs once in the rules, so a later rules edit cannot retarget it unseen.
test.each(MUTANTS)("the fuzz finds the mutant: %s", async (_what, from, to) => {
    expect(h.RULES.split(from)).toHaveLength(2);
    const rules = h.RULES.replace(from, to);
    const run = fuzz(rules, { seed: 1, numRuns: 3 * RUNS, endOnFailure: true });
    await expect(run).rejects.toThrow("the emulator says allowed, the model denied");
});
