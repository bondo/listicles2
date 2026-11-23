import {
    assertFails,
    initializeTestEnvironment,
    type RulesTestEnvironment,
} from "@firebase/rules-unit-testing";
import firebase from "firebase/compat/app";
import * as h from "./harness";

// M1-10 (PLAN 3.1): Create household + owner, one batch with the one-household check (P1, P3, P4,
// #199), and the update of the caller's own member doc (displayName, P4). Each test seeds its world
// with rules off; every allow test goes through h.verifiedOnly. The transfer is M1-53's.
// No test can isolate these (a scratch mutation pass dropped each condition in turn): hasAll (each
// key's value is checked too), the household's own !exists (implied by create), ownerUid == caller
// on either doc (the other doc checks it), deleted == false and exists(users/uid) (the users-doc set
// and the get() that follows check them).
type Fields = Record<string, unknown>;
let env: RulesTestEnvironment;
let alice: Record<h.Client, h.Db>;
let carol: Record<h.Client, h.Db>;
let dan: Record<h.Client, h.Db>;

const ALICE = h.UID;
const BOB = "bob";
const CAROL = "carol";
const DAN = "dan";
const NEW = "Kq3ZtW9xLm2RbV7nPc4D"; // a Firestore auto-id: 20 of [A-Za-z0-9] (P3)
const NEW2 = "Pz8YwV2nQs5TxK1mRc7B";
const HOME = "household00000000001";
const AWAY = "household00000000002";
const TOMB = "household00000000003";
const T0 = new Date(0);
const NOW = firebase.firestore.FieldValue.serverTimestamp();
const FIFTY = "a".repeat(50);
const NON_BMP = "\u{1F3E0}".repeat(50); // 50 code points, 100 UTF-16 units
const user = (uid = ALICE): string => `users/${uid}`;
const member = (hid: string, uid = ALICE): string => `households/${hid}/members/${uid}`;
const household = (uid = ALICE): Fields => ({
    name: "Home",
    createdBy: uid,
    createdAt: NOW,
    ownerUid: uid,
    deleted: false,
});
const OWNER: Fields = { role: "owner", displayName: "Alice", joinedAt: NOW };
const without = (fields: Fields, key: string): Fields =>
    Object.fromEntries(Object.entries(fields).filter(([k]) => k !== key));

// One Create household batch by `uid`: the household doc, the caller's owner member doc and the
// users-doc set; each can be replaced, or left out with null.
interface Create {
    hid?: string;
    household?: Fields | null;
    owner?: Fields | null;
    ownerId?: string; // the owner member doc's id: the caller's unless named (P1)
    second?: Fields; // a member doc for bob as well (P1)
    twin?: string; // a second household, with the caller's owner member doc, in the same batch
    users?: "update" | "set" | null; // set: a create when there is no users doc
}

function create(db: h.Db, c: Create = {}, uid = ALICE): Promise<void> {
    const hid = c.hid ?? NEW;
    const batch = db.batch();
    if (c.household !== null) batch.set(db.doc(`households/${hid}`), c.household ?? household(uid));
    if (c.owner !== null) batch.set(db.doc(member(hid, c.ownerId ?? uid)), c.owner ?? OWNER);
    if (c.second !== undefined) batch.set(db.doc(member(hid, BOB)), c.second);
    if (c.twin !== undefined) {
        batch.set(db.doc(`households/${c.twin}`), household(uid));
        batch.set(db.doc(member(c.twin, uid)), OWNER);
    }
    if (c.users === "set") batch.set(db.doc(user(uid)), { householdId: hid });
    else if (c.users !== null) batch.update(db.doc(user(uid)), { householdId: hid });
    return batch.commit();
}

// Documents set, or deleted where null, with rules off.
async function seed(docs: Record<string, Fields | null>): Promise<void> {
    await env.withSecurityRulesDisabled(async (admin) => {
        for (const [p, data] of Object.entries(docs)) {
            const ref = admin.firestore().doc(p);
            await (data === null ? ref.delete() : ref.set(data));
        }
    });
}

beforeAll(async () => {
    env = await initializeTestEnvironment({ projectId: h.PROJECT, firestore: { rules: h.RULES } });
    alice = h.connect(env);
    carol = h.connect(env, CAROL);
    dan = h.connect(env, DAN);
});

afterAll(async () => {
    await env.cleanup();
});

// HOME: bob owns it, carol is a plain member; seeded with createdBy null (PLAN 3.1 field validation).
// AWAY: eve's. TOMB: alice created and deleted it; its cleanup and her clear are done. Alice and dan
// are in no household.
beforeEach(async () => {
    await env.clearFirestore();
    const live = { name: "Home", createdBy: BOB, createdAt: T0, ownerUid: BOB, deleted: false };
    await seed({
        [`households/${HOME}`]: { ...live, createdBy: null },
        [`households/${AWAY}`]: { ...live, createdBy: "eve", ownerUid: "eve" },
        [`households/${TOMB}`]: {
            ...live,
            name: "",
            createdBy: ALICE,
            ownerUid: ALICE,
            deleted: true,
        },
        [member(HOME, BOB)]: { role: "owner", displayName: "Bob", joinedAt: T0 },
        [member(HOME, CAROL)]: { role: "member", displayName: "Carol", joinedAt: T0 },
        [member(AWAY, "eve")]: { role: "owner", displayName: "Eve", joinedAt: T0 },
        [user()]: { householdId: null },
        [user(CAROL)]: { householdId: HOME },
        [user(DAN)]: { householdId: null },
    });
});

describe("Create household + owner (one batch)", () => {
    test.each<[string, Create]>([
        ["the household, the owner's member doc and the users-doc set", {}],
        [
            "names of exactly 50 characters",
            { household: { ...household(), name: FIFTY }, owner: { ...OWNER, displayName: FIFTY } },
        ],
        [
            "names of 50 non-BMP code points",
            {
                household: { ...household(), name: NON_BMP },
                owner: { ...OWNER, displayName: NON_BMP },
            },
        ],
    ])("verified only: %s", async (_what, c) => {
        await h.verifiedOnly(alice, (db) => create(db, c));
    });

    // P1 (#206) and P3 (#243): the member doc is the caller's own, the id a 20-character auto-id.
    // The first row is also denied by the household's existsAfter and the users-doc set, the third
    // by its role; the second, an owner's doc for bob next to alice's, isolates P1.
    test.each<[string, Create]>([
        ["the owner's member doc for another uid", { ownerId: BOB }],
        ["a second member doc, an owner's, for another uid", { second: OWNER }],
        ["a second member doc, a plain member's", { second: { ...OWNER, role: "member" } }],
        ["a household id of 19 characters", { hid: NEW.slice(1) }],
        ["a household id of 21 characters", { hid: `${NEW}a` }],
        ...["_", "-", ".", "*"].map((ch): [string, Create] => [
            `a household id with ${ch}`,
            { hid: `${NEW.slice(1)}${ch}` },
        ]),
    ])("denied: %s", async (_what, c) => {
        await assertFails(create(alice.verified, c));
    });

    // P4 and PLAN 3.1 field validation, the household doc.
    test.each<[string, Fields]>([
        ["an unknown field", { ...household(), color: "red" }],
        ...Object.keys(household()).map((k): [string, Fields] => [
            `no ${k}`,
            without(household(), k),
        ]),
        ["a name of 51 characters", { ...household(), name: `${FIFTY}a` }],
        ["a name of spaces only", { ...household(), name: "   " }],
        ["an empty name (only a tombstone's may be)", { ...household(), name: "" }],
        ["a name that is no string", { ...household(), name: 42 }],
        ["createdBy another user", { ...household(), createdBy: BOB }],
        ["ownerUid another user", { ...household(), ownerUid: BOB }],
        ["createdAt not the request time", { ...household(), createdAt: T0 }],
        ["deleted true", { ...household(), deleted: true }],
    ])("denied: a household doc with %s", async (_what, data) => {
        await assertFails(create(alice.verified, { household: data }));
    });

    // P4, the owner's member doc: role, displayName and joinedAt; viaInvite is the joiner's.
    test.each<[string, Fields]>([
        ["an unknown field", { ...OWNER, viaInvite: `${NEW}_${"s".repeat(22)}` }],
        ...Object.keys(OWNER).map((k): [string, Fields] => [`no ${k}`, without(OWNER, k)]),
        ["role member", { ...OWNER, role: "member" }],
        ["a display name of 51 characters", { ...OWNER, displayName: `${FIFTY}a` }],
        ["a display name of spaces only", { ...OWNER, displayName: "   " }],
        ["joinedAt not the request time", { ...OWNER, joinedAt: T0 }],
    ])("denied: the owner's member doc with %s", async (_what, data) => {
        await assertFails(create(alice.verified, { owner: data }));
    });

    // The batch: the household needs its owner's member doc after it, the member doc a household
    // that the batch creates.
    test.each<[string, Create]>([
        ["the household doc alone", { owner: null, users: null }],
        ["the member doc and the users-doc set without the household doc", { household: null }],
    ])("denied: %s", async (_what, c) => {
        await assertFails(create(alice.verified, c));
    });

    // The one-household check (PLAN 3.1): the users doc exists and holds null before the batch, the
    // new household after it; a stale value must be self-healed first. The users-doc rule also denies
    // the rows with a users-doc write (hid1 -> hid2, or a create with a household). The second row
    // isolates householdId == hid after the batch (not just a value), the last householdId == null
    // before it.
    test.each<[string, Record<string, Fields | null>, Create]>([
        ["without the users-doc write", {}, { users: null }],
        ["with a second household and her owner member doc in it (HH-01)", {}, { twin: NEW2 }],
        ["with no users doc, the batch creating it", { [user()]: null }, { users: "set" }],
        ["with no users doc and no users-doc write", { [user()]: null }, { users: null }],
        [
            "while householdId names another live household she is a member of",
            {
                [user()]: { householdId: AWAY },
                [member(AWAY)]: { ...OWNER, role: "member", joinedAt: T0 },
            },
            {},
        ],
        [
            "while householdId is stale: removed from another",
            { [user()]: { householdId: AWAY } },
            {},
        ],
        ["while householdId is stale: a tombstone", { [user()]: { householdId: TOMB } }, {}],
        // Seeded only to show the check itself: a users doc never names a household before it exists.
        [
            "while householdId already names the new id",
            { [user()]: { householdId: NEW } },
            { users: null },
        ],
    ])("denied: %s", async (_what, docs, c) => {
        await seed(docs);
        await assertFails(create(alice.verified, c));
    });

    // #199: no rule deletes a household doc, so an id that has existed is never created again.
    test.each<[string, () => h.Db, string]>([
        [
            "by its former owner, with her owner member doc in the same batch",
            () => alice.verified,
            ALICE,
        ],
        ["by another user", () => dan.verified, DAN],
    ])("denied: re-creating a deleted household's id %s", async (_what, db, uid) => {
        await assertFails(create(db(), { hid: TOMB }, uid));
    });

    // Only the member doc's !exists(household) can deny this batch: the household (seeded) is live and
    // names alice as owner but holds no member doc of hers, so her users-doc set into it is allowed.
    test("denied: an owner's member doc for a household that exists already", async () => {
        await seed({ [`households/${NEW}`]: { ...household(), createdAt: T0 } });
        await assertFails(create(alice.verified, { household: null }));
    });
});

describe("Update own member doc: displayName only", () => {
    const own = member(HOME, CAROL);

    test.each<[string, string]>([
        ["exactly 50 characters", FIFTY],
        ["50 non-BMP code points", NON_BMP],
    ])("verified only: a display name of %s", async (_what, displayName) => {
        await h.verifiedOnly(carol, (db) => db.doc(own).update({ displayName }));
    });

    test.each<[string, Fields]>([
        ["a display name of 51 characters", { displayName: `${FIFTY}a` }],
        ["a display name of spaces only", { displayName: "   " }],
        ["an added field", { displayName: "Caro", color: "red" }],
        ["the role: a plain member to owner", { role: "owner" }],
    ])("denied: an update of %s", async (_what, data) => {
        await assertFails(carol.verified.doc(own).update(data));
    });

    test("denied: another member's display name", async () => {
        await assertFails(carol.verified.doc(member(HOME, BOB)).update({ displayName: "Rob" }));
    });

    // LIVE (PLAN 3.1): under a tombstone the owner's cleanup and the P6 delete are the only writes.
    test("denied: the own display name under a tombstone", async () => {
        await seed({ [member(TOMB)]: { ...OWNER, joinedAt: T0 } });
        await assertFails(alice.verified.doc(member(TOMB)).update({ displayName: "Ally" }));
    });
});
