import {
    assertFails,
    assertSucceeds,
    initializeTestEnvironment,
    type RulesTestEnvironment,
} from "@firebase/rules-unit-testing";
import firebase from "firebase/compat/app";
import * as h from "./harness";

// M1-95, split from M1-11 (PLAN 3.1 Delete household; #199, #205): the owner's soft delete, which
// must clear the name; no rule deletes a household doc, live or a tombstone; under a tombstone the
// owner's cleanup (get, list and delete of the members, the removed markers and the household's
// invites, one rule each) and a member's delete of her own member doc (P6), and no other write.
// Leave, Remove member and its marker writes are M1-11's; the transfer, the join, a member's
// invite create and the own display name under a tombstone are denied in their own files. Each
// test seeds its world with rules off; every allow test goes through h.verifiedOnly.
// No test can isolate these: `deleted == true` on the cleanup paths of the invite get and delete
// (a live household's invite is anyone's to get and its owner's to revoke), and LIVE on the
// owner's revoke (the cleanup allows the same delete). On the member reads and the invite list it
// is isolated only in a world the app never makes (the last describe). Not pinned: `deleted ==
// true` on the markers' get, list and delete, since M1-11's Remove member lets the owner of a live
// household make them.
type Fields = Record<string, unknown>;
type Clients = Record<h.Client, h.Db>;
type Request = (db: h.Db) => Promise<unknown>;
let env: RulesTestEnvironment;
let alice: Clients;
let bob: Clients;
let dan: Clients;
let erin: Clients;
let frank: Clients;

const ALICE = h.UID;
const BOB = "bob";
const DAN = "dan";
const ERIN = "erin";
const FRANK = "frank";
const GUS = "gus";
const HOME = "household00000000001";
const TOMB = "household00000000003";
const T0 = new Date(0);
const DAY = 86_400_000;
const NOW = firebase.firestore.FieldValue.serverTimestamp();
const code = (hid: string, c: string): string => `${hid}_${c.repeat(22)}`;
const household = (hid: string): string => `households/${hid}`;
const member = (hid: string, uid: string): string => `households/${hid}/members/${uid}`;
const marker = (hid: string, uid: string): string => `households/${hid}/removed/${uid}`;
const invite = (c: string): string => `invites/${c}`;
const user = (uid: string): string => `users/${uid}`;
const membership = (role: string): Fields => ({ role, displayName: "Name", joinedAt: T0 });
const LIVE: Fields = { name: "Home", createdBy: BOB, createdAt: T0, ownerUid: BOB, deleted: false };
// The soft delete as the app sends it (#205: the name cleared).
const SOFT: Fields = { deleted: true, name: "" };
// A stored invite of the tombstone, open for a day or (a negative expiresIn) expired.
const stored = (createdBy: string, expiresIn = DAY): Fields => ({
    householdId: TOMB,
    householdName: "Old home", // the name outlives the household until the cleanup (#281)
    createdBy,
    createdAt: T0,
    expiresAt: new Date(Date.now() + expiresIn),
});
const get =
    (p: string): Request =>
    (db) =>
        db.doc(p).get();
const remove =
    (p: string): Request =>
    (db) =>
        db.doc(p).delete();
const membersOf =
    (hid: string): Request =>
    (db) =>
        db.collection(`${household(hid)}/members`).get();
const markersOf =
    (hid: string): Request =>
    (db) =>
        db.collection(`${household(hid)}/removed`).get();
const invitesOf =
    (hid: string): Request =>
    (db) =>
        db.collection("invites").where("householdId", "==", hid).get();

// One batch deleting each path.
function deleteAll(db: h.Db, paths: string[]): Promise<void> {
    const batch = db.batch();
    for (const p of paths) batch.delete(db.doc(p));
    return batch.commit();
}

async function seed(docs: Record<string, Fields>): Promise<void> {
    await env.withSecurityRulesDisabled(async (admin) => {
        for (const [p, data] of Object.entries(docs)) await admin.firestore().doc(p).set(data);
    });
}

beforeAll(async () => {
    env = await initializeTestEnvironment({ projectId: h.PROJECT, firestore: { rules: h.RULES } });
    alice = h.connect(env);
    bob = h.connect(env, BOB);
    dan = h.connect(env, DAN);
    erin = h.connect(env, ERIN);
    frank = h.connect(env, FRANK);
});

afterAll(async () => {
    await env.cleanup();
});

// HOME: bob's, alice a plain member. TOMB: dan soft-deleted it (createdBy seeded null, PLAN 3.1
// field validation); neither his cleanup nor erin's self-heal has run, so both member docs, gus's
// leftover marker, erin's open invite and dan's expired one are still there, and both users docs
// point at it. Frank is in no household.
beforeEach(async () => {
    await env.clearFirestore();
    await seed({
        [household(HOME)]: LIVE,
        [household(TOMB)]: { ...LIVE, name: "", createdBy: null, ownerUid: DAN, deleted: true },
        [member(HOME, BOB)]: membership("owner"),
        [member(HOME, ALICE)]: membership("member"),
        [member(TOMB, DAN)]: membership("owner"),
        [member(TOMB, ERIN)]: membership("member"),
        [marker(TOMB, GUS)]: { removedAt: T0 },
        [invite(code(TOMB, "e"))]: stored(ERIN),
        [invite(code(TOMB, "d"))]: stored(DAN, -DAY),
        [user(DAN)]: { householdId: TOMB },
        [user(ERIN)]: { householdId: TOMB },
        [user(FRANK)]: { householdId: null },
    });
});

describe("Delete household: the soft delete", () => {
    // #205: deleted false -> true and the name cleared, nothing else; createdBy may be null.
    test.each<[string, Fields]>([
        ["created by its owner", {}],
        ["created by null", { createdBy: null }],
    ])("verified only: the owner's, on a household %s", async (_what, fields) => {
        await seed({ [household(HOME)]: { ...LIVE, ...fields } });
        await h.verifiedOnly(bob, (db) => db.doc(household(HOME)).update(SOFT));
    });

    // O(uid): the name is cleared, so only the caller check can deny.
    test.each<[string, () => h.Db]>([
        ["a plain member", () => alice.verified],
        ["a signed-in non-member", () => frank.verified],
    ])("denied: a soft delete by %s", async (_who, db) => {
        await assertFails(db().doc(household(HOME)).update(SOFT));
    });

    test.each<[string, Fields]>([
        ["the name kept", { deleted: true }],
        ["another name, not cleared", { deleted: true, name: "Gone" }],
        ["the name cleared, deleted still false", { name: "" }],
        ["ownerUid changed too", { ...SOFT, ownerUid: ALICE }],
        ["createdBy nulled too", { ...SOFT, createdBy: null }],
        ["createdAt changed too", { ...SOFT, createdAt: NOW }],
        ["an unknown field", { ...SOFT, color: "red" }],
    ])("denied: the owner's soft delete with %s", async (_what, data) => {
        await assertFails(bob.verified.doc(household(HOME)).update(data));
    });

    // A tombstone stays one: even the same soft delete again is a write under it.
    test.each<[string, Fields]>([
        ["deleted true -> false", { deleted: false }],
        ["deleted true -> false and a name", { deleted: false, name: "Back" }],
        ["a name", { name: "Back" }],
        ["the soft delete again", SOFT],
    ])("denied: the owner's update of his tombstone, %s", async (_what, data) => {
        await assertFails(dan.verified.doc(household(TOMB)).update(data));
    });
});

// #199: no rule deletes a household doc, so an id that has existed is never free again.
test.each<[string, () => h.Db, string]>([
    ["the owner, his tombstone", () => dan.verified, TOMB],
    ["the owner, his live household", () => bob.verified, HOME],
    ["a plain member, the live household", () => alice.verified, HOME],
    ["a plain member, the tombstone", () => erin.verified, TOMB],
    ["a signed-in non-member", () => frank.verified, HOME],
])("denied: a delete of the household doc by %s", async (_who, db, hid) => {
    await assertFails(remove(household(hid))(db()));
});

describe("Delete household: the owner's cleanup under the tombstone", () => {
    // O(uid) while deleted == true, on the tombstone seeded with createdBy null; with the tombstone
    // read (M1-08), the owner's start resumes the cleanup from these.
    test.each<[string, Request]>([
        ["the tombstone", get(household(TOMB))],
        ["a member doc", get(member(TOMB, ERIN))],
        ["the members", membersOf(TOMB)],
        ["a removed marker", get(marker(TOMB, GUS))],
        ["the removed markers", markersOf(TOMB)],
        ["an invite", get(invite(code(TOMB, "e")))],
        ["the invites, by householdId", invitesOf(TOMB)],
    ])("verified only: the owner reads %s", async (_what, read) => {
        await h.verifiedOnly(dan, read);
    });

    // PLAN 3.1: invites, then removed markers, then members, a page each; then the owner's clear
    // of his householdId (M1-08's rule; the own users doc needs no verified email). The tombstone
    // stays.
    test("verified only: the cleanup pages; then the owner's clear; no tombstone delete", async () => {
        const pages = [
            [invite(code(TOMB, "e")), invite(code(TOMB, "d"))],
            [marker(TOMB, GUS)],
            [member(TOMB, ERIN), member(TOMB, DAN)],
        ];
        for (const paths of pages) await h.verifiedOnly(dan, (db) => deleteAll(db, paths));
        await assertSucceeds(dan.verified.doc(user(DAN)).update({ householdId: null }));
        await assertFails(remove(household(TOMB))(dan.verified));
    });

    // Nobody but the owner: a plain member of the tombstone (her own member doc is P6's) and a
    // signed-in non-member.
    test.each<[string, () => h.Db, Request]>([
        [
            "a plain member deletes the owner's member doc",
            () => erin.verified,
            remove(member(TOMB, DAN)),
        ],
        [
            "a plain member deletes the removed marker",
            () => erin.verified,
            remove(marker(TOMB, GUS)),
        ],
        ["a plain member gets the removed marker", () => erin.verified, get(marker(TOMB, GUS))],
        ["a plain member lists the removed markers", () => erin.verified, markersOf(TOMB)],
        ["a plain member lists the invites by householdId", () => erin.verified, invitesOf(TOMB)],
        ["a non-member deletes a member doc", () => frank.verified, remove(member(TOMB, ERIN))],
        ["a non-member deletes an invite", () => frank.verified, remove(invite(code(TOMB, "e")))],
        ["a non-member lists the members", () => frank.verified, membersOf(TOMB)],
    ])("denied: %s", async (_what, db, request) => {
        await assertFails(request(db()));
    });

    // The cleanup needs deleted == true: in a live household the owner deletes a member doc only
    // through Remove member (M1-11), never his own.
    test.each<[string, string]>([
        ["a plain member's, without the removed marker", ALICE],
        ["his own", BOB],
    ])("denied: the owner of a live household deletes %s member doc", async (_what, uid) => {
        await assertFails(remove(member(HOME, uid))(bob.verified));
    });
});

describe("P6: a member deletes her own member doc under the tombstone", () => {
    test("verified only: alone", async () => {
        await h.verifiedOnly(erin, remove(member(TOMB, ERIN)));
    });

    test("verified only: in one batch with her users-doc clear", async () => {
        await h.verifiedOnly(erin, (db) => {
            const batch = db.batch();
            batch.delete(db.doc(member(TOMB, ERIN)));
            batch.update(db.doc(user(ERIN)), { householdId: null });
            return batch.commit();
        });
    });
});

// PLAN 3.1: under a tombstone nothing is written but the cleanup deletes and P6; the cleanup only
// reads, lists and deletes. LIVE alone denies the invite, which names the tombstone's name.
test.each<[string, () => h.Db, Request]>([
    [
        "the owner creates a member doc",
        () => dan.verified,
        (db) => db.doc(member(TOMB, FRANK)).set({ ...membership("member"), joinedAt: NOW }),
    ],
    [
        "the owner updates a member doc",
        () => dan.verified,
        (db) => db.doc(member(TOMB, ERIN)).update({ displayName: "Erin" }),
    ],
    [
        "the owner creates an invite",
        () => dan.verified,
        (db) =>
            db
                .doc(invite(code(TOMB, "n")))
                .set({ ...stored(DAN), householdName: "", createdAt: NOW }),
    ],
    [
        "the owner overwrites a removed marker",
        () => dan.verified,
        (db) => db.doc(marker(TOMB, GUS)).set({ removedAt: NOW }),
    ],
])("denied under the tombstone: %s", async (_what, db, request) => {
    await assertFails(request(db()));
});

// The cleanup reads on their own, in a world the app never makes: frank owns NEST, which is live,
// with no member doc there, so only the cleanup's `deleted == true` can deny his reads; a rule that
// let the owner read without it would let him in.
describe("The cleanup reads need deleted == true", () => {
    const NEST = "household00000000004";

    beforeEach(async () => {
        await seed({
            [household(NEST)]: { ...LIVE, createdBy: FRANK, ownerUid: FRANK },
            [member(NEST, ALICE)]: membership("member"),
            [invite(code(NEST, "a"))]: {
                ...stored(ALICE),
                householdId: NEST,
                householdName: "Home",
            },
        });
    });

    test.each<[string, Request]>([
        ["a member doc", get(member(NEST, ALICE))],
        ["the members", membersOf(NEST)],
        ["the invites, by householdId", invitesOf(NEST)],
    ])("denied: the owner of a live household, no member there, reads %s", async (_what, read) => {
        await assertFails(read(frank.verified));
    });
});
