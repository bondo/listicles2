import {
    assertFails,
    assertSucceeds,
    initializeTestEnvironment,
    type RulesTestEnvironment,
} from "@firebase/rules-unit-testing";
import firebase from "firebase/compat/app";
import * as h from "./harness";

// M1-11 (PLAN 3.1 Leave, Remove member): a plain member leaves in one batch (her member doc, her
// invites, her users-doc clear); the owner removes a member in one batch that also deletes the
// member's open invites and writes the removed marker, a create or an overwrite of a leftover one
// (only removedAt, the request time, P4); only the owner gets, lists and deletes markers. Under a
// tombstone: tombstone.test.ts. Each test seeds its world with rules off; every allow test goes
// through h.verifiedOnly.
// No test can isolate these: on Remove's member delete O(uid) (the marker needs it too) and the
// target not the owner before and not after the batch (each alone denies the owner's own removal,
// and a batch that moves ownerUid needs the old and the new owner's member docs after it); the
// marker's hasAll and removedAt (the member delete reads removedAt after the batch); LIVE on Leave,
// on Remove's member delete and on the marker reads (P6 and the owner's cleanup allow the same
// under a tombstone).
type Fields = Record<string, unknown>;
type Clients = Record<h.Client, h.Db>;
type Request = (db: h.Db) => Promise<unknown>;
let env: RulesTestEnvironment;
let alice: Clients;
let bob: Clients;
let carol: Clients;
let frank: Clients;
let gus: Clients;

const ALICE = h.UID;
const BOB = "bob";
const CAROL = "carol";
const FRANK = "frank";
const GUS = "gus";
const HOME = "household00000000001";
const T0 = new Date(0);
const DAY = 86_400_000;
const NOW = firebase.firestore.FieldValue.serverTimestamp();
const code = (c: string): string => `${HOME}_${c.repeat(22)}`;
const household = `households/${HOME}`;
const member = (uid: string): string => `${household}/members/${uid}`;
const marker = (uid: string): string => `${household}/removed/${uid}`;
const invite = (c: string): string => `invites/${c}`;
const user = (uid: string): string => `users/${uid}`;
const HOUSEHOLD = { name: "Home", createdBy: ALICE, createdAt: T0, ownerUid: BOB, deleted: false };
const membership = (role: string): Fields => ({ role, displayName: "Name", joinedAt: T0 });
const stored = (createdBy: string): Fields => ({
    householdId: HOME,
    householdName: "Home",
    createdBy,
    createdAt: T0,
    expiresAt: new Date(Date.now() + DAY),
});
const get = (p: string) => (db: h.Db) => db.doc(p).get();
const remove = (p: string) => (db: h.Db) => db.doc(p).delete();
const markers: Request = (db) => db.collection(`${household}/removed`).get();

// One Leave batch by `uid`: the own member doc, each of `invites`, the users-doc clear, and with
// `mark` a removed marker for oneself.
function leave(db: h.Db, uid: string, invites: string[] = [], mark = false): Promise<void> {
    const batch = db.batch();
    batch.delete(db.doc(member(uid)));
    for (const c of invites) batch.delete(db.doc(invite(c)));
    if (mark) batch.set(db.doc(marker(uid)), { removedAt: NOW });
    batch.update(db.doc(user(uid)), { householdId: null });
    return batch.commit();
}

// One Remove batch of `target`: the member doc (kept with keep), the marker {removedAt: request
// time} or `mark` (none with null), each of `invites`; with `to`, also a transfer from bob to `to`
// (the household update and the role update of each of the two who is not the target).
interface Remove {
    keep?: true;
    mark?: Fields | null;
    invites?: string[];
    to?: string;
}

function removal(db: h.Db, target: string, r: Remove = {}): Promise<void> {
    const batch = db.batch();
    if (r.to !== undefined) {
        batch.update(db.doc(household), { ownerUid: r.to });
        for (const [uid, role] of Object.entries({ [BOB]: "member", [r.to]: "owner" })) {
            if (uid !== target) batch.update(db.doc(member(uid)), { role });
        }
    }
    if (r.keep !== true) batch.delete(db.doc(member(target)));
    if (r.mark !== null) batch.set(db.doc(marker(target)), r.mark ?? { removedAt: NOW });
    for (const c of r.invites ?? []) batch.delete(db.doc(invite(c)));
    return batch.commit();
}

// Carol's rejoin (M1-54) with alice's invite: her member doc, the invite delete, her users-doc set.
function rejoin(db: h.Db): Promise<void> {
    const via = code("a");
    const batch = db.batch();
    const doc = { role: "member", displayName: "Carol", joinedAt: NOW, viaInvite: via };
    batch.set(db.doc(member(CAROL)), doc);
    batch.delete(db.doc(invite(via)));
    batch.update(db.doc(user(CAROL)), { householdId: HOME });
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
    carol = h.connect(env, CAROL);
    frank = h.connect(env, FRANK);
    gus = h.connect(env, GUS);
});

afterAll(async () => {
    await env.cleanup();
});

// HOME as a transfer leaves it: alice created it, bob owns it, so a rule that took createdBy for
// O(uid) fails the tests. Alice and carol are plain members with an open invite each. Gus was
// removed; bob's client did not get to delete the marker, and gus has not self-healed. Frank is in
// no household.
beforeEach(async () => {
    await env.clearFirestore();
    await seed({
        [household]: HOUSEHOLD,
        [member(BOB)]: membership("owner"),
        [member(ALICE)]: membership("member"),
        [member(CAROL)]: membership("member"),
        [marker(GUS)]: { removedAt: T0 },
        [invite(code("a"))]: stored(ALICE),
        [invite(code("c"))]: stored(CAROL),
        ...Object.fromEntries(
            [ALICE, BOB, CAROL, GUS].map((u) => [user(u), { householdId: HOME }]),
        ),
        [user(FRANK)]: { householdId: null },
    });
});

describe("Leave (one batch)", () => {
    // PLAN 3.1: the users-doc clear is allowed in the batch that deletes the member doc (P5).
    test("verified only: a plain member's: her member doc, her invite, her users-doc clear", async () => {
        await h.verifiedOnly(alice, (db) => leave(db, ALICE, [code("a")]));
    });

    // !O(uid): the owner transfers ownership or deletes the household instead. Leave deletes only
    // the caller's own member doc, and only while there is one (M(uid)): gus was removed.
    test.each<[string, () => h.Db, Request]>([
        ["the owner's Leave batch", () => bob.verified, (db) => leave(db, BOB)],
        ["a plain member deletes carol's member doc", () => alice.verified, remove(member(CAROL))],
        ["a non-member deletes a member doc", () => frank.verified, remove(member(CAROL))],
        ["a removed member's Leave batch", () => gus.verified, (db) => leave(db, GUS)],
    ])("denied: %s", async (_what, db, request) => {
        await assertFails(request(db()));
    });
});

describe("Remove member (one batch)", () => {
    test("verified only: the owner's: carol's member doc, her open invite, the marker", async () => {
        await h.verifiedOnly(bob, (db) => removal(db, CAROL, { invites: [code("c")] }));
    });

    // PLAN 3.1: the marker is created, or a leftover one overwritten, so a member can be removed
    // again after a rejoin. Carol self-heals in between (M1-08); bob's client never deletes the
    // first marker.
    test("verified only: remove, rejoin, remove again", async () => {
        await h.verifiedOnly(bob, (db) => removal(db, CAROL, { invites: [code("c")] }));
        await assertSucceeds(carol.verified.doc(user(CAROL)).update({ householdId: null }));
        await assertSucceeds(rejoin(carol.verified));
        await h.verifiedOnly(bob, (db) => removal(db, CAROL));
    });

    // The member delete needs the marker written in the batch (removedAt the request time); the
    // marker needs the target a member before the batch and not after it, and holds only
    // removedAt (P4). Zoe was never a member: only M(target) denies her marker.
    test.each<[string, string, Remove]>([
        ["without the marker", CAROL, { mark: null }],
        ["with removedAt not the request time", CAROL, { mark: { removedAt: T0 } }],
        ["with a marker without removedAt", CAROL, { mark: {} }],
        ["with a marker holding another field", CAROL, { mark: { removedAt: NOW, by: BOB } }],
        ["of the marker alone, carol staying a member", CAROL, { keep: true }],
        ["of a user who never was a member", "zoe", {}],
        ["of the owner himself", BOB, {}],
        ["of himself, handing ownership to carol in the batch", BOB, { to: CAROL }],
        ["of carol, handing her ownership in the batch", CAROL, { to: CAROL }],
    ])("denied: the owner's batch %s", async (_what, target, r) => {
        await assertFails(removal(bob.verified, target, r));
    });

    // A leftover marker of carol's: the member delete reads removedAt, not just the marker, and
    // the overwrite changes only removedAt too (P4).
    test.each<[string, Remove]>([
        ["the member delete alone", { mark: null }],
        ["an overwrite holding another field", { mark: { removedAt: NOW, by: BOB } }],
    ])("denied: with a leftover marker, the owner's batch with %s", async (_what, r) => {
        await seed({ [marker(CAROL)]: { removedAt: T0 } });
        await assertFails(removal(bob.verified, CAROL, r));
    });

    // The overwrite of a leftover marker alone, no member delete in the batch (PLAN 3.1: deny a
    // non-owner write, a write while the target stays a member): carol's, seeded here, and gus's,
    // who is no member.
    test.each<[string, () => h.Db, string]>([
        ["a non-member's of gus's", () => frank.verified, GUS],
        ["a plain member's of carol's", () => alice.verified, CAROL],
        ["the owner's of carol's, carol staying a member", () => bob.verified, CAROL],
        ["the owner's of gus's, who is no member", () => bob.verified, GUS],
    ])("denied: a marker overwrite alone, %s", async (_what, db, uid) => {
        await seed({ [marker(CAROL)]: { removedAt: T0 } });
        await assertFails(db().doc(marker(uid)).set({ removedAt: NOW }));
    });

    // O(uid), never M(uid) or createdBy (alice created HOME). In the last row only the marker's
    // O(uid) denies: alice may leave, and she is a member before the batch, not after it.
    test.each<[string, () => h.Db, Request]>([
        ["a plain member's Remove batch", () => alice.verified, (db) => removal(db, CAROL)],
        ["a non-member's Remove batch", () => frank.verified, (db) => removal(db, CAROL)],
        [
            "a plain member's Leave with a marker",
            () => alice.verified,
            (db) => leave(db, ALICE, [], true),
        ],
    ])("denied: %s", async (_what, db, request) => {
        await assertFails(request(db()));
    });

    // Alice's leftover marker (removed, then rejoined): only the overwrite's O(uid) denies her
    // Leave that overwrites it.
    test("denied: a plain member's Leave overwriting her leftover marker", async () => {
        await seed({ [marker(ALICE)]: { removedAt: T0 } });
        await assertFails(leave(alice.verified, ALICE, [], true));
    });
});

describe("The removed markers: only the owner gets, lists and deletes them", () => {
    test.each<[string, Request]>([
        ["gets one", get(marker(GUS))],
        ["lists them", markers],
        ["deletes one", remove(marker(GUS))],
    ])("verified only: the owner %s", async (_what, request) => {
        await h.verifiedOnly(bob, request);
    });

    test.each<[string, () => h.Db, Request]>([
        ["a plain member gets one", () => alice.verified, get(marker(GUS))],
        ["a plain member lists them", () => alice.verified, markers],
        ["a plain member deletes one", () => alice.verified, remove(marker(GUS))],
        ["the removed member gets his own", () => gus.verified, get(marker(GUS))],
        ["the removed member deletes his own", () => gus.verified, remove(marker(GUS))],
        ["a non-member gets one", () => frank.verified, get(marker(GUS))],
    ])("denied: %s", async (_what, db, request) => {
        await assertFails(request(db()));
    });
});
