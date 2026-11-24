import {
    assertFails,
    initializeTestEnvironment,
    type RulesTestEnvironment,
} from "@firebase/rules-unit-testing";
import * as h from "./harness";

// M1-83, PLAN 3.1 Reads: a member of the live household (M(uid), LIVE) gets the household doc and
// gets and lists its members. The household get shares its allow statement with M1-08's tombstone
// read, the member get with M1-08's own member path (ADR 0002 layout); base.test.ts keeps their
// tests. Under a tombstone the owner's cleanup reads are M1-11's (tombstone.test.ts), so no test
// here reads as the owner there. Each test seeds its world with rules off; every allow test goes
// through h.verifiedOnly, which first shows the request denied to the member's unverified token.
type Clients = Record<h.Client, h.Db>;
type Read = (db: h.Db) => Promise<unknown>;
let env: RulesTestEnvironment;
let alice: Clients;
let bob: Clients;
let erin: Clients;
let eve: Clients;
let frank: Clients;
let gus: Clients;

const ALICE = h.UID;
const BOB = "bob";
const DAN = "dan";
const ERIN = "erin";
const EVE = "eve";
const FRANK = "frank";
const GUS = "gus";
const HOME = "household00000000001";
const AWAY = "household00000000002";
const TOMB = "household00000000003";
const T0 = new Date(0);
const user = (uid: string): string => `users/${uid}`;
const member = (hid: string, uid: string): string => `households/${hid}/members/${uid}`;
const membership = (role: string, displayName: string): object => ({
    role,
    displayName,
    joinedAt: T0,
});
const household = (ownerUid: string): object => ({
    name: "Home",
    createdBy: ownerUid,
    createdAt: T0,
    ownerUid,
    deleted: false,
});

// PLAN 3.1's member reads of `hid`: the household doc, the member doc of `uid`, the members query.
const membersOf = (db: h.Db, hid: string) => db.collection(`households/${hid}/members`);
function householdDoc(hid: string): Read {
    return (db) => db.doc(`households/${hid}`).get();
}
function memberDoc(hid: string, uid: string): Read {
    return (db) => db.doc(member(hid, uid)).get();
}
function members(hid: string): Read {
    return (db) => membersOf(db, hid).get();
}
const READS: [string, Read][] = [
    ["the household doc", householdDoc(HOME)],
    ["the owner's member doc", memberDoc(HOME, BOB)],
    ["the members query", members(HOME)],
];

async function seed(docs: Record<string, object>): Promise<void> {
    await env.withSecurityRulesDisabled(async (admin) => {
        for (const [p, data] of Object.entries(docs)) await admin.firestore().doc(p).set(data);
    });
}

beforeAll(async () => {
    env = await initializeTestEnvironment({ projectId: h.PROJECT, firestore: { rules: h.RULES } });
    alice = h.connect(env);
    bob = h.connect(env, BOB);
    erin = h.connect(env, ERIN);
    eve = h.connect(env, EVE);
    frank = h.connect(env, FRANK);
    gus = h.connect(env, GUS);
});

afterAll(async () => {
    await env.cleanup();
});

// HOME: bob owns it, alice is a plain member; gus was removed from it, the marker is still there and
// gus has not self-healed yet. AWAY: eve's. TOMB: dan's tombstone, erin a plain member of it; neither
// the owner's cleanup nor erin's self-heal has run, so both member docs are still there. Frank is in
// no household.
beforeEach(async () => {
    await env.clearFirestore();
    await seed({
        [`households/${HOME}`]: household(BOB),
        [`households/${AWAY}`]: household(EVE),
        [`households/${TOMB}`]: { ...household(DAN), name: "", deleted: true },
        [member(HOME, BOB)]: membership("owner", "Bob"),
        [member(HOME, ALICE)]: membership("member", "Alice"),
        [member(AWAY, EVE)]: membership("owner", "Eve"),
        [member(TOMB, DAN)]: membership("owner", "Dan"),
        [member(TOMB, ERIN)]: membership("member", "Erin"),
        [`households/${HOME}/removed/${GUS}`]: { removedAt: T0 },
        [user(ALICE)]: { householdId: HOME },
        [user(BOB)]: { householdId: HOME },
        [user(GUS)]: { householdId: HOME },
        [user(EVE)]: { householdId: AWAY },
        [user(DAN)]: { householdId: TOMB },
        [user(ERIN)]: { householdId: TOMB },
        [user(FRANK)]: { householdId: null },
    });
});

describe("a member of the live household (M(uid), LIVE)", () => {
    const callers: [string, () => Clients][] = [
        ["a plain member", () => alice],
        ["the owner", () => bob],
    ];

    test.each(callers)("verified only: %s gets the household doc", async (_who, caller) => {
        await h.verifiedOnly(caller(), householdDoc(HOME));
    });

    test.each<[string, () => Clients, string]>([
        ["a plain member gets the owner's", () => alice, BOB],
        ["the owner gets a plain member's", () => bob, ALICE],
    ])("verified only: %s member doc", async (_who, caller, uid) => {
        await h.verifiedOnly(caller(), memberDoc(HOME, uid));
    });

    test.each(callers)("verified only: %s lists the members, all of them", async (_who, caller) => {
        await h.verifiedOnly(caller(), members(HOME));
        const listed = await membersOf(caller().verified, HOME).get();
        expect(listed.docs.map((d) => d.id)).toEqual([ALICE, BOB]);
    });
});

// Not M(uid): a householdId pointing at the household, or a membership elsewhere, makes no member.
describe("not a member of the live household", () => {
    const outsiders: [string, () => Clients][] = [
        ["in no household", () => frank],
        ["removed, the householdId still pointing at it", () => gus],
        ["a member of another household", () => eve],
    ];

    test.each(
        outsiders.flatMap(([who, caller]) =>
            READS.map(([what, read]): [string, string, () => Clients, Read] => [
                who,
                what,
                caller,
                read,
            ]),
        ),
    )("denied: a caller %s, %s", async (_who, _what, caller, read) => {
        await assertFails(read(caller().verified));
    });

    test.each(READS)("denied: signed out, %s", async (_what, read) => {
        await assertFails(read(alice.anonymous));
    });
});

// LIVE (PLAN 3.1): erin's member doc is still there, but under a tombstone a member's reads are
// denied; the tombstone read is the one exception.
describe("a plain member under a tombstone", () => {
    test.each<[string, Read]>([
        ["the owner's member doc", memberDoc(TOMB, DAN)],
        ["the members query", members(TOMB)],
    ])("denied: %s", async (_what, read) => {
        await assertFails(read(erin.verified));
    });

    // The tombstone read (M1-08) shares the household doc's allow statement: while erin's
    // householdId points at the tombstone, the get is allowed, for the HH-06 dialog and the self-heal.
    test("verified only: the household doc, through the tombstone read", async () => {
        await h.verifiedOnly(erin, householdDoc(TOMB));
    });

    // Seeded only to show the check: the P5 clear needs the member doc gone first. With the
    // householdId cleared only the member path could allow the get, and it needs LIVE.
    test("denied: the household doc, the householdId cleared, the member doc still there", async () => {
        await seed({ [user(ERIN)]: { householdId: null } });
        await assertFails(householdDoc(TOMB)(erin.verified));
    });
});

// PLAN 3.1: the removed markers are owner-only (M1-11) and no recursive member read rule covers the
// household, so a member's reads end at the household doc and its member docs.
test.each<[string, Read]>([
    ["a removed marker", (db) => db.doc(`households/${HOME}/removed/${GUS}`).get()],
    ["the removed markers query", (db) => db.collection(`households/${HOME}/removed`).get()],
    ["a doc of an unplanned subcollection", (db) => db.doc(`households/${HOME}/unplanned/x`).get()],
    ["a doc under a member doc", (db) => db.doc(`${member(HOME, BOB)}/unplanned/x`).get()],
    ["a collection-group query on members", (db) => db.collectionGroup("members").get()],
])("denied: a member's read of %s", async (_what, read) => {
    await seed({
        [`households/${HOME}/unplanned/x`]: { name: "x" },
        [`${member(HOME, BOB)}/unplanned/x`]: { name: "x" },
    });
    await assertFails(read(alice.verified));
});
