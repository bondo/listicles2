import { initializeTestEnvironment, type RulesTestEnvironment } from "@firebase/rules-unit-testing";
import * as h from "./harness";
import * as m from "./model";

// M1-90 (PLAN 3.1 field validation, P4): one definition of a blank name for the rules and the app. A
// code point is blank when it is U+0000 to U+0020 (what the rules' trim() strips) or Unicode
// White_Space; a name is blank when all its code points are. The rules (validName), the model and
// core/domain's Validation each hold it; Validation's property tests check every code point there.
let env: RulesTestEnvironment;
let dbs: Record<h.Client, h.Db>;

const range = (from: number, to: number): number[] =>
    Array.from({ length: to - from + 1 }, (_, i) => from + i);
// The PLAN's list.
const BLANK = new Set([
    ...range(0x0, 0x20),
    0x85,
    0xa0,
    0x1680,
    ...range(0x2000, 0x200a),
    0x2028,
    0x2029,
    0x202f,
    0x205f,
    0x3000,
]);
// Each code point next to a blank one that is not blank itself.
const NEIGHBOURS = [...new Set([...BLANK].flatMap((c) => [c - 1, c + 1]))].filter(
    (c) => c >= 0 && !BLANK.has(c),
);
const U = (c: number): string => `U+${c.toString(16).toUpperCase().padStart(4, "0")}`;
// The code points of all of Unicode on which `blank` and the PLAN's list disagree.
const mismatches = (blank: (c: number) => boolean): string[] =>
    range(0, 0x10ffff)
        .filter((c) => blank(c) !== BLANK.has(c))
        .map(U);

test("the PLAN's blank code points are U+0000 to U+0020 and Unicode White_Space", () => {
    expect(BLANK.size).toBe(52);
    const white = /^\p{White_Space}$/u;
    expect(mismatches((c) => c <= 0x20 || white.test(String.fromCodePoint(c)))).toEqual([]);
});

test("the model calls a name of one code point blank exactly when the PLAN does", () => {
    expect(mismatches((c) => !m.validName(String.fromCodePoint(c)))).toEqual([]);
});

// validName's blank regex in firestore.rules, read as written: a class of \x{..} escapes and ranges.
test("the rules' blank regex lists exactly the PLAN's code points", () => {
    const escapes = /\\\\x\{([0-9A-F]+)\}(?:-\\\\x\{([0-9A-F]+)\})?/g;
    const body = /function validName\(name\) \{([\s\S]*?)\n {4}\}/.exec(h.RULES)?.[1] ?? "";
    const set = /!name\.matches\('\[(.*?)\]\*'\)/.exec(body)?.[1] ?? "";
    expect(set.replace(escapes, "")).toBe("");
    const listed = new Set(
        [...set.matchAll(escapes)].flatMap(([, from = "", to = from]) =>
            range(parseInt(from, 16), parseInt(to, 16)),
        ),
    );
    expect(mismatches((c) => listed.has(c))).toEqual([]);
});

describe("on the emulator, through the users doc", () => {
    const name = (n: string): Promise<h.Outcome> =>
        h.outcome(dbs.verified.doc(`users/${h.UID}`).update({ name: n }));

    beforeAll(async () => {
        env = await initializeTestEnvironment({
            projectId: h.PROJECT,
            firestore: { rules: h.RULES },
        });
        dbs = h.connect(env);
    });

    afterAll(async () => {
        await env.cleanup();
    });

    beforeEach(async () => {
        await env.clearFirestore();
        await env.withSecurityRulesDisabled(async (admin) => {
            await admin.firestore().doc(`users/${h.UID}`).set({ householdId: null });
        });
    });

    // validName is the one check of every name (users doc, household, display names), so one path
    // stands for all; each path's own deny rows are in its test file.
    test("a name of one blank code point is denied, of one next to them allowed", async () => {
        const got: string[] = [];
        for (const c of [...BLANK, ...NEIGHBOURS]) {
            got.push(`${U(c)} ${await name(String.fromCodePoint(c))}`);
        }
        expect(got).toEqual([
            ...[...BLANK].map((c) => `${U(c)} denied`),
            ...NEIGHBOURS.map((c) => `${U(c)} allowed`),
        ]);
    });

    // The first row is what the two trims let through before M1-90: trim() keeps U+0085 and U+3000.
    test.each<[h.Outcome, string, string]>([
        ["denied", "blank code points of every kind", "\u0001\u0085\u3000 \t"],
        ["denied", "50 blank code points", "\u3000".repeat(50)],
        [
            "allowed",
            "blank code points around and inside visible ones",
            "\u3000\u0001Ann\u0085Lee \u00a0",
        ],
        ["allowed", "49 blank code points and a visible one", `${"\u2003".repeat(49)}a`],
        ["allowed", "a zero-width space, which is not White_Space", "\u200b"],
    ])("%s: a name of %s", async (want, _what, n) => {
        await expect(name(n)).resolves.toBe(want);
    });
});
