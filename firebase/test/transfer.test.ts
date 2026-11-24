import {
    assertFails,
    initializeTestEnvironment,
    type RulesTestEnvironment,
} from "@firebase/rules-unit-testing";
import * as h from "./harness";

// M1-53 (PLAN 3.1): Transfer ownership, one batch that updates the household's ownerUid and the
// role of both member docs; the caller check is O(uid), never M(uid) (#234). Each test seeds its
// world with rules off; every allow test goes through h.verifiedOnly.
// No test can isolate these (ADR 0002): M(new) before the batch and existsAfter(new) (the new
// owner's member doc cannot be created in the batch, and the getAfter of its role fails without it).
type Fields = Record<string, unknown>;
type Clients = Record<h.Client, h.Db>;
let env: RulesTestEnvironment;
let bob: Clients;
let carol: Clients;
let dan: Clients;

const BOB = "bob";
const CAROL = "carol";
const DAN = "dan";
const FAY = "fay";
const HOME = "household00000000001";
const TOMB = "household00000000003";
const T0 = new Date(0);
const member = (hid: string, uid: string): string => `households/${hid}/members/${uid}`;
const membership = (role: string, displayName: string): Fields => ({
    role,
    displayName,
    joinedAt: T0,
});
const HOUSEHOLD: Fields = {
    name: "Home",
    createdBy: BOB,
    createdAt: T0,
    ownerUid: BOB,
    deleted: false,
};
// The roles after a transfer from bob to carol.
const FULL: Record<string, string> = { [BOB]: "member", [CAROL]: "owner" };

// One batch by the caller in `hid` (HOME unless named): the household update, ownerUid to `to`
// (carol unless named) and the fields of `household`, or none with null; and a role update for each
// uid of `roles` (FULL unless named) to the role it names, with the fields of `doc`.
interface Batch {
    hid?: string;
    to?: string;
    household?: Fields | null;
    roles?: Record<string, string>;
    doc?: Fields;
}

function transfer(db: h.Db, b: Batch = {}): Promise<void> {
    const hid = b.hid ?? HOME;
    const batch = db.batch();
    if (b.household !== null) {
        batch.update(db.doc(`households/${hid}`), { ownerUid: b.to ?? CAROL, ...b.household });
    }
    for (const [uid, role] of Object.entries(b.roles ?? FULL)) {
        batch.update(db.doc(member(hid, uid)), { role, ...b.doc });
    }
    return batch.commit();
}

// Documents set with rules off.
async function seed(docs: Record<string, Fields>): Promise<void> {
    await env.withSecurityRulesDisabled(async (admin) => {
        for (const [p, data] of Object.entries(docs)) await admin.firestore().doc(p).set(data);
    });
}

beforeAll(async () => {
    env = await initializeTestEnvironment({ projectId: h.PROJECT, firestore: { rules: h.RULES } });
    bob = h.connect(env, BOB);
    carol = h.connect(env, CAROL);
    dan = h.connect(env, DAN);
});

afterAll(async () => {
    await env.cleanup();
});

// HOME: bob owns it, carol and fay are plain members. TOMB: bob's tombstone, its cleanup not done,
// so bob's and carol's member docs are still there. Dan is signed in and a member of neither.
beforeEach(async () => {
    await env.clearFirestore();
    await seed({
        [`households/${HOME}`]: HOUSEHOLD,
        [`households/${TOMB}`]: { ...HOUSEHOLD, name: "", deleted: true },
        [member(HOME, BOB)]: membership("owner", "Bob"),
        [member(HOME, CAROL)]: membership("member", "Carol"),
        [member(HOME, FAY)]: membership("member", "Fay"),
        [member(TOMB, BOB)]: membership("owner", "Bob"),
        [member(TOMB, CAROL)]: membership("member", "Carol"),
    });
});

describe("Transfer ownership (one batch)", () => {
    // PLAN 3.1 field validation: a stored createdBy of null passes (#205), ownerUid stays a uid.
    test.each<[string, Record<string, Fields>]>([
        ["the owner", {}],
        ["null", { [`households/${HOME}`]: { ...HOUSEHOLD, createdBy: null } }],
    ])("verified only: the owner's batch on a household created by %s", async (_what, docs) => {
        await seed(docs);
        await h.verifiedOnly(bob, (db) => transfer(db));
    });

    // The household update checks both roles after the batch, each role update the ownerUid after
    // it, so there is always exactly one owner: a partial transfer is denied (#234).
    test.each<[string, Batch]>([
        ["the household update with no role updates", { roles: {} }],
        ["only the old owner's role update (no owner)", { roles: { [BOB]: "member" } }],
        ["only the new owner's role update (two owners)", { roles: { [CAROL]: "owner" } }],
        ["both role updates without the household update", { household: null }],
        ["the new owner's role update alone", { household: null, roles: { [CAROL]: "owner" } }],
        ["the old owner's role update alone", { household: null, roles: { [BOB]: "member" } }],
        ["a third member made owner too", { roles: { ...FULL, [FAY]: "owner" } }],
        ["a third member's role neither owner nor member", { roles: { ...FULL, [FAY]: "admin" } }],
    ])("denied: by the owner, %s", async (_what, b) => {
        await assertFails(transfer(bob.verified, b));
    });

    // O(uid), never M(uid): only the owner transfers. The role checks deny any household update
    // without both role updates, so the full batches test the caller checks of both documents.
    test.each<[string, () => h.Db, Batch]>([
        [
            "a plain member setting ownerUid to herself, the household update alone",
            () => carol.verified,
            { to: CAROL, roles: {} },
        ],
        ["a plain member's full batch, to herself", () => carol.verified, { to: CAROL }],
        [
            "a signed-in non-member setting ownerUid to a plain member, the household update alone",
            () => dan.verified,
            { roles: {} },
        ],
        ["a signed-in non-member's full batch, to a plain member", () => dan.verified, {}],
    ])("denied: %s", async (_what, db, b) => {
        await assertFails(transfer(db(), b));
    });

    test("denied: the owner's transfer to a signed-in user who is no member", async () => {
        await assertFails(transfer(bob.verified, { to: DAN, roles: { [BOB]: "member" } }));
    });

    // P4: a transfer changes only ownerUid on the household and role on each member doc.
    test.each<[string, Batch]>([
        ["role added to the household doc", { household: { role: "owner" } }],
        ["an unknown field added to the household doc", { household: { color: "red" } }],
        ["the household name changed too", { household: { name: "Away" } }],
        ["an unknown field added to each member doc", { doc: { color: "red" } }],
        ["the display names changed too", { doc: { displayName: "Owner" } }],
    ])("denied: the owner's batch with %s", async (_what, b) => {
        await assertFails(transfer(bob.verified, b));
    });

    // LIVE (PLAN 3.1): under a tombstone only the owner's cleanup and the P6 delete write (M1-11).
    test("denied: the owner's batch under a tombstone", async () => {
        await assertFails(transfer(bob.verified, { hid: TOMB }));
    });
});

// Each caller check, LIVE and the type of ownerUid on its own, in worlds the app never makes: a
// member's cached role is already owner while ownerUid is still bob, so the role checks pass and
// only the named check can deny.
describe("Transfer ownership: each check on its own", () => {
    test.each<[string, () => h.Db, Batch]>([
        [
            "O(uid) of the household update: a plain member's, to herself",
            () => carol.verified,
            { to: CAROL, roles: {} },
        ],
        [
            "LIVE of the household update: the owner's, under a tombstone",
            () => bob.verified,
            { hid: TOMB, roles: {} },
        ],
        [
            "O(uid) of the role update: a plain member's, the owner's role back to owner",
            () => carol.verified,
            { household: null, roles: { [BOB]: "owner" } },
        ],
        [
            "LIVE of the role update: the owner's own role back to owner, under a tombstone",
            () => bob.verified,
            { hid: TOMB, household: null, roles: { [BOB]: "owner" } },
        ],
    ])("denied: %s", async (_what, db, b) => {
        const hid = b.hid ?? HOME;
        await seed({
            [member(hid, BOB)]: membership("member", "Bob"),
            [member(hid, CAROL)]: membership("owner", "Carol"),
        });
        await assertFails(transfer(db(), b));
    });

    // P4 types: ownerUid stays a string. A path takes the number 42 as the document id "42", so
    // with that member's role owner already, only the type check denies.
    test("denied: the type of ownerUid: a number that names a member doc", async () => {
        await seed({ [member(HOME, "42")]: membership("owner", "Number") });
        const b: Batch = { household: { ownerUid: 42 }, roles: { [BOB]: "member" } };
        await assertFails(transfer(bob.verified, b));
    });
});
