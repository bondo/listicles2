import {
    assertFails,
    assertSucceeds,
    initializeTestEnvironment,
    type RulesTestEnvironment,
    type TokenOptions,
} from "@firebase/rules-unit-testing";
import * as h from "./harness";

// M1-08, the rules base (PLAN 3.1): the caller's users doc, config/app, the caller's own member path
// and the tombstone read, each in a world seeded with rules off. Every allow test of a rule that needs
// a verified email goes through h.verifiedOnly.
let env: RulesTestEnvironment;
let dbs: Record<h.Client, h.Db>;

const BOB = "bob";
const LIVE = "household00000000001";
const OTHER = "household00000000002";
const TOMB = "household00000000003";
const CONFIG = "config/app";
const user = (uid = h.UID): string => `users/${uid}`;
const member = (hid: string, uid = h.UID): string => `households/${hid}/members/${uid}`;
const T0 = new Date(0);
const MEMBER = { role: "member", displayName: "Alice", joinedAt: T0 };
const HOME = { name: "Home", createdBy: BOB, createdAt: T0, ownerUid: BOB, deleted: false };
const GOOGLE: TokenOptions = { email_verified: true, firebase: { sign_in_provider: "google.com" } };

async function seed(docs: Record<string, object>): Promise<void> {
    await env.withSecurityRulesDisabled(async (admin) => {
        for (const [p, data] of Object.entries(docs)) await admin.firestore().doc(p).set(data);
    });
}

// The caller's users doc pointing at `householdId`, and the caller's member doc in each of `memberOf`.
async function mine(householdId: string | null, ...memberOf: string[]): Promise<void> {
    await seed({
        [user()]: { householdId },
        ...Object.fromEntries(memberOf.map((hid) => [member(hid), MEMBER])),
    });
}

async function check(want: h.Outcome, request: Promise<unknown>): Promise<void> {
    if (want === "allowed") await assertSucceeds(request);
    else await assertFails(request);
}

beforeAll(async () => {
    env = await initializeTestEnvironment({ projectId: h.PROJECT, firestore: { rules: h.RULES } });
    dbs = h.connect(env);
});

afterAll(async () => {
    await env.cleanup();
});

// Two live households of bob's and a tombstone (PLAN 3.1: name cleared; createdBy may be null).
beforeEach(async () => {
    await env.clearFirestore();
    await seed({
        [`households/${LIVE}`]: HOME,
        [`households/${OTHER}`]: HOME,
        [`households/${TOMB}`]: { ...HOME, name: "", createdBy: null, deleted: true },
    });
});

describe("users/{uid}", () => {
    const fifty = "a".repeat(50);
    // 50 code points, 100 UTF-16 units: the rules count code points, as the app does (M1-13).
    const nonBmp = "\u{1F3E0}".repeat(50);

    test("get: the own doc, verified or not; not signed out, nobody else's", async () => {
        await mine(null);
        await seed({ [user(BOB)]: { householdId: null } });
        await assertSucceeds(dbs.unverified.doc(user()).get());
        await assertSucceeds(dbs.verified.doc(user()).get());
        await assertFails(dbs.anonymous.doc(user()).get());
        await assertFails(dbs.verified.doc(user(BOB)).get());
    });

    test.each<[h.Client, string, object]>([
        ["unverified", "householdId null", { householdId: null }],
        ["verified", "householdId null and a name", { householdId: null, name: "Alice" }],
        ["unverified", "a name of 50 characters", { householdId: null, name: fifty }],
        ["verified", "a name of 50 non-BMP code points", { householdId: null, name: nonBmp }],
        ["verified", "a name with a line break", { householdId: null, name: "Ali\nce" }],
    ])("allowed: create by the %s client with %s", async (client, _what, data) => {
        await assertSucceeds(dbs[client].doc(user()).set(data));
    });

    // The caller is a member of LIVE, so only the create rule can deny the create pointing at it.
    test.each<[string, object]>([
        ["a household", { householdId: LIVE }],
        ["no householdId", { name: "Alice" }],
        ["an unknown field", { householdId: null, role: "owner" }],
        ["a name of 51 characters", { householdId: null, name: `${fifty}a` }],
        ["a name of 51 non-BMP code points", { householdId: null, name: `${nonBmp}\u{1F3E0}` }],
        ["an empty name", { householdId: null, name: "" }],
        ["a name of spaces only", { householdId: null, name: "   " }],
        ["a name that is no string", { householdId: null, name: 42 }],
    ])("denied: create with %s", async (_what, data) => {
        await seed({ [member(LIVE)]: MEMBER });
        await assertFails(dbs.verified.doc(user()).set(data));
    });

    test.each<[h.Outcome, h.Client, string, object]>([
        ["allowed", "unverified", "the name alone", { name: "Alice" }],
        ["allowed", "verified", "the name alone", { name: nonBmp }],
        ["allowed", "verified", "a name with a line break", { name: "Ali\nce" }],
        ["denied", "verified", "an unknown field", { role: "owner" }],
        ["denied", "verified", "a name of 51 characters", { name: `${fifty}a` }],
        ["denied", "verified", "a name of spaces only", { name: "   " }],
        ["denied", "verified", "a name that is no string", { name: 42 }],
    ])("%s: update by the %s client of %s", async (want, client, _what, data) => {
        await mine(LIVE, LIVE);
        await check(want, dbs[client].doc(user()).update(data));
    });

    test("denied: an overwrite that drops householdId", async () => {
        await mine(null);
        await assertFails(dbs.verified.doc(user()).set({ name: "Alice" }));
    });

    // name may be missing (PLAN 3.1, P9): the start gate then asks for it again (AUTH-12).
    test("allowed: an overwrite that drops the name", async () => {
        await seed({ [user()]: { householdId: null, name: "Alice" } });
        await assertSucceeds(dbs.verified.doc(user()).set({ householdId: null }));
    });

    // PLAN 3.1 and P5: set only into a live household with the own member doc after the write, clear
    // only without one, never from one household straight to another.
    test.each<[h.Outcome, string, string | null, string[], string | null]>([
        ["allowed", "set, a member of the live household", null, [LIVE], LIVE],
        ["allowed", "clear after removal", LIVE, [], null],
        ["allowed", "clear under a tombstone, the own member doc gone", TOMB, [], null],
        ["denied", "set without membership", null, [], LIVE],
        ["denied", "set to a tombstone, the own member doc still there", null, [TOMB], TOMB],
        ["denied", "move to another household, a member of both", LIVE, [LIVE, OTHER], OTHER],
        ["denied", "clear while a member of the live household", LIVE, [LIVE], null],
        ["denied", "clear under a tombstone, the own member doc still there", TOMB, [TOMB], null],
    ])("%s: householdId %s", async (want, _what, before, memberOf, after) => {
        await mine(before, ...memberOf);
        await check(want, dbs.verified.doc(user()).update({ householdId: after }));
    });

    test.each<[h.Outcome, string, string | null, string[]]>([
        ["allowed", "householdId null", null, []],
        ["denied", "a live household", LIVE, [LIVE]],
        ["denied", "a stale household after removal", LIVE, []],
        ["denied", "a stale household, a tombstone", TOMB, []],
    ])("%s: delete of the own doc holding %s", async (want, _what, householdId, memberOf) => {
        await mine(householdId, ...memberOf);
        await check(want, dbs.verified.doc(user()).delete());
    });

    // P7: an account deletion that crashed after this delete repeats it on resume.
    test("allowed: delete of the own doc when there is none", async () => {
        await assertSucceeds(dbs.verified.doc(user()).delete());
    });

    test("denied: any request to another user's doc, from any client", async () => {
        await seed({ [user(BOB)]: { householdId: null } });
        for (const client of h.CLIENT_NAMES) {
            const db = dbs[client];
            await assertFails(db.doc(user(BOB)).get());
            await assertFails(db.doc(user(BOB)).update({ name: "Bob" }));
            await assertFails(db.doc(user(BOB)).delete());
            await assertFails(db.doc(user("carol")).set({ householdId: null }));
            await assertFails(db.doc(user("carol")).delete());
        }
    });
});

describe("config/app", () => {
    test("anyone reads it, even signed out; no client writes it", async () => {
        for (const client of h.CLIENT_NAMES) {
            await assertFails(dbs[client].doc(CONFIG).set({ minVersionCode: 2 }));
        }
        await seed({ [CONFIG]: { minVersionCode: 1 } });
        for (const client of h.CLIENT_NAMES) {
            await assertSucceeds(dbs[client].doc(CONFIG).get());
            await assertFails(dbs[client].doc(CONFIG).update({ minVersionCode: 2 }));
            await assertFails(dbs[client].doc(CONFIG).delete());
        }
    });
});

describe("the caller's own member path", () => {
    test.each<[string, string | null, string, string[]]>([
        ["the own member doc in a live household", LIVE, LIVE, [LIVE]],
        ["no member doc of mine there", null, LIVE, []],
        ["the own member doc under a tombstone", TOMB, TOMB, [TOMB]],
        ["a household that does not exist", null, "household00000000009", []],
    ])("verified only: get, %s", async (_what, householdId, hid, memberOf) => {
        await mine(householdId, ...memberOf);
        await h.verifiedOnly(dbs, (db) => db.doc(member(hid)).get());
    });

    test("denied: another user's member path, to a non-member", async () => {
        await mine(null);
        await seed({ [member(LIVE, BOB)]: MEMBER });
        for (const client of h.CLIENT_NAMES) {
            await assertFails(dbs[client].doc(member(LIVE, BOB)).get());
        }
    });
});

describe("the household doc", () => {
    test("verified only: get of the tombstone the own householdId points at", async () => {
        await mine(TOMB);
        await h.verifiedOnly(dbs, (db) => db.doc(`households/${TOMB}`).get());
    });

    const bobs = { [user(BOB)]: { householdId: TOMB } };
    test.each<[string, Record<string, object>, string]>([
        ["live, mine points at it, no member doc", { [user()]: { householdId: LIVE } }, LIVE],
        ["bob's tombstone, mine elsewhere", { ...bobs, [user()]: { householdId: OTHER } }, TOMB],
        ["bob's tombstone, no users doc of mine", bobs, TOMB],
    ])("denied: get, %s", async (_what, docs, hid) => {
        await seed(docs);
        for (const client of h.CLIENT_NAMES) {
            await assertFails(dbs[client].doc(`households/${hid}`).get());
        }
    });

    test("verifiedOnly fails when the verified request is denied as well", async () => {
        await mine(LIVE);
        await expect(
            h.verifiedOnly(dbs, (db) => db.doc(`households/${LIVE}`).get()),
        ).rejects.toMatchObject({ code: "permission-denied" });
    });
});

// A Google sign-in (PLAN 3.1: email_verified true) passes every rule a verified password token does.
test("a Google token is a verified caller", async () => {
    const google = env.authenticatedContext(h.UID, GOOGLE).firestore();
    await mine(TOMB);
    await seed({ [CONFIG]: { minVersionCode: 1 }, [user(BOB)]: { householdId: null } });
    await assertSucceeds(google.doc(CONFIG).get());
    await assertSucceeds(google.doc(user()).get());
    await assertFails(google.doc(user(BOB)).get());
    await assertSucceeds(google.doc(`households/${TOMB}`).get());
    await assertSucceeds(google.doc(member(TOMB)).get());
    await assertSucceeds(google.doc(user()).update({ householdId: null }));
});
