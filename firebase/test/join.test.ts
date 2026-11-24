import {
    assertFails,
    initializeTestEnvironment,
    type RulesTestEnvironment,
} from "@firebase/rules-unit-testing";
import firebase from "firebase/compat/app";
import * as h from "./harness";

// M1-54 (PLAN 3.1): Join, one batch that creates the caller's own member doc (P1, #206), deletes
// the invite it names (single use) and sets the caller's users doc (the one-household check); each
// rule sees the others' writes through existsAfter and getAfter. Each test seeds its world with
// rules off; every allow test goes through h.verifiedOnly. Spike (b) stays in spike.test.ts.
// No test can isolate these (a scratch mutation pass dropped each condition in turn; ADR 0002):
// hasAll (each key's value has its own check), the invite's householdId == hid (the joiner's
// delete reads the member doc in the invite's household after the batch), LIVE in the member
// create and in the joiner's delete (the users-doc set's P5 check) and exists(users/uid) (a get()
// of no document fails).
type Fields = Record<string, unknown>;
type Clients = Record<h.Client, h.Db>;
let env: RulesTestEnvironment;
let carol: Clients;
let dan: Clients;
let frank: Clients;
let gus: Clients;

const ALICE = h.UID;
const BOB = "bob";
const CAROL = "carol";
const DAN = "dan";
const EVE = "eve";
const ERIN = "erin";
const FRANK = "frank";
const GUS = "gus";
const HOME = "household00000000001";
const AWAY = "household00000000002";
const TOMB = "household00000000003";
const T0 = new Date(0);
const DAY = 86_400_000;
const NOW = firebase.firestore.FieldValue.serverTimestamp();
const FIFTY = "a".repeat(50);
const NON_BMP = "\u{1F3E0}".repeat(50); // 50 code points, 100 UTF-16 units
// A code (P3): <householdId>_<secret>, the secret 22 characters, here `c` 22 times.
const code = (hid: string, c: string): string => `${hid}_${c.repeat(22)}`;
const JOIN = code(HOME, "j");
const user = (uid: string): string => `users/${uid}`;
const inviteDoc = (c: string): string => `invites/${c}`;
const member = (hid: string, uid: string): string => `households/${hid}/members/${uid}`;
const household = (ownerUid: string, name = "Home", deleted = false): Fields => ({
    name,
    createdBy: ownerUid,
    createdAt: T0,
    ownerUid,
    deleted,
});
const membership = (role: string): Fields => ({ role, displayName: "Name", joinedAt: T0 });
// A stored invite, open for a day or (a negative expiresIn) expired.
const stored = (hid: string, createdBy: string, expiresIn = DAY): Fields => ({
    householdId: hid,
    householdName: "Home",
    createdBy,
    createdAt: T0,
    expiresAt: new Date(Date.now() + expiresIn),
});
// The joiner's member doc as the app writes it, but viaInvite (M1-18 copies the name).
const JOINER: Fields = { role: "member", displayName: "Dan", joinedAt: NOW };
const without = (fields: Fields, key?: string): Fields =>
    Object.fromEntries(Object.entries(fields).filter(([k]) => k !== key));

// One join batch by `uid` (dan unless named), as the app sends it: the caller's member doc in `hid`
// (HOME) naming `via` (JOIN), the delete of that invite and the users-doc set to `hid`. `doc`
// replaces fields of the member doc and `drop` removes one; `members` names the uids whose member
// docs the batch creates; `invite: false` leaves the delete out and `burn` deletes another invite
// too; `users: null` leaves the users-doc write out and "set" creates the doc; `twin` joins a
// second household, with its code, in the same batch.
interface Join {
    hid?: string;
    via?: string;
    doc?: Fields;
    drop?: string;
    members?: string[];
    invite?: false;
    burn?: string;
    users?: "set" | null;
    twin?: [string, string];
}

function join(db: h.Db, j: Join = {}, uid = DAN): Promise<void> {
    const hid = j.hid ?? HOME;
    const via = j.via ?? JOIN;
    const doc = without({ ...JOINER, viaInvite: via, ...j.doc }, j.drop);
    const batch = db.batch();
    for (const m of j.members ?? [uid]) batch.set(db.doc(member(hid, m)), doc);
    if (j.invite !== false) batch.delete(db.doc(inviteDoc(via)));
    if (j.burn !== undefined) batch.delete(db.doc(inviteDoc(j.burn)));
    if (j.twin !== undefined) {
        const [hid2, via2] = j.twin;
        batch.set(db.doc(member(hid2, uid)), { ...JOINER, viaInvite: via2 });
        batch.delete(db.doc(inviteDoc(via2)));
    }
    if (j.users === "set") batch.set(db.doc(user(uid)), { householdId: hid });
    else if (j.users !== null) batch.update(db.doc(user(uid)), { householdId: hid });
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
    carol = h.connect(env, CAROL);
    dan = h.connect(env, DAN);
    frank = h.connect(env, FRANK);
    gus = h.connect(env, GUS);
});

afterAll(async () => {
    await env.cleanup();
});

// HOME: bob owns it, alice and carol are plain members; carol joined with JOIN's code, which a
// member then created again (P3's accepted residual). Gus was removed and has self-healed; his
// invite is left over. Open invites: JOIN by bob, alice's, gus's and one by lee, who left; an
// expired one by bob. AWAY: eve's, with her open invite. TOMB: erin's tombstone, its cleanup not
// done, so her member doc and her open invite are still there. Dan and frank, who join, are in no
// household; their users docs hold a name (P9).
beforeEach(async () => {
    await env.clearFirestore();
    await seed({
        [`households/${HOME}`]: household(BOB),
        [`households/${AWAY}`]: household(EVE, "Away"),
        [`households/${TOMB}`]: household(ERIN, "", true),
        [member(HOME, BOB)]: membership("owner"),
        [member(HOME, ALICE)]: membership("member"),
        [member(HOME, CAROL)]: { ...membership("member"), viaInvite: JOIN },
        [member(AWAY, EVE)]: membership("owner"),
        [member(TOMB, ERIN)]: membership("owner"),
        [user(DAN)]: { householdId: null, name: "Dan" },
        [user(FRANK)]: { householdId: null, name: "Frank" },
        [user(GUS)]: { householdId: null, name: "Gus" },
        [inviteDoc(JOIN)]: stored(HOME, BOB),
        [inviteDoc(code(HOME, "a"))]: stored(HOME, ALICE),
        [inviteDoc(code(HOME, "g"))]: stored(HOME, GUS),
        [inviteDoc(code(HOME, "l"))]: stored(HOME, "lee"),
        [inviteDoc(code(HOME, "x"))]: stored(HOME, BOB, -DAY),
        [inviteDoc(code(AWAY, "e"))]: stored(AWAY, EVE),
        [inviteDoc(code(TOMB, "t"))]: stored(TOMB, ERIN),
    });
});

describe("Join (one batch)", () => {
    // The invite's creator is still a member: the owner or a plain member. P4: names of exactly 50
    // characters and of 50 non-BMP code points.
    test.each<[string, Join]>([
        ["with the owner's invite", {}],
        ["with a plain member's invite", { via: code(HOME, "a") }],
        ["with a display name of exactly 50 characters", { doc: { displayName: FIFTY } }],
        ["with a display name of 50 non-BMP code points", { doc: { displayName: NON_BMP } }],
    ])("verified only: the batch %s", async (_what, j) => {
        await h.verifiedOnly(dan, (db) => join(db, j));
    });

    // OQ-5: once self-healed, a removed member may rejoin through another member's invite, but not
    // alone with one he created: its creator is no longer a member.
    test("verified only: a removed member's rejoin with another member's invite", async () => {
        await h.verifiedOnly(gus, (db) => join(db, { via: code(HOME, "a") }, GUS));
    });

    test("denied: a removed member's rejoin with his own leftover invite", async () => {
        await assertFails(join(gus.verified, { via: code(HOME, "g") }, GUS));
    });

    // Single use: the join deletes the invite, so a used code joins nobody else.
    test("denied: a used code, a second join with it after dan's", async () => {
        await h.verifiedOnly(dan, (db) => join(db));
        await assertFails(join(frank.verified, {}, FRANK));
    });

    // P1 (#206): the member doc is the caller's own. The first row isolates it: zoe's doc meets
    // every other condition (the one-household check reads the caller's users doc).
    test.each<[string, Join]>([
        ["the #206 batch, a member doc for another uid next to his own", { members: [DAN, "zoe"] }],
        ["a batch whose only member doc is for another uid", { members: ["zoe"] }],
    ])("denied: %s", async (_what, j) => {
        await assertFails(join(dan.verified, j));
    });

    // The invite exists, points at the household, has not expired, its creator is still a member,
    // and the same batch deletes it and no other invite (M1.md section 5). A revoked code names no
    // invite, so its batch has no delete.
    test.each<[string, Join]>([
        ["without the invite delete", { invite: false }],
        ["with a revoked code", { via: code(HOME, "r"), invite: false }],
        ["with an expired invite", { via: code(HOME, "x") }],
        ["with an invite whose creator left", { via: code(HOME, "l") }],
        ["with another household's invite", { via: code(AWAY, "e") }],
        ["deleting another invite of the household too", { burn: code(HOME, "a") }],
    ])("denied: a join %s", async (_what, j) => {
        await assertFails(join(dan.verified, j));
    });

    // The joiner's delete: no member doc before the batch, one after it that names the code, so an
    // existing member cannot burn another's invite. Carol's member doc names JOIN (P3's re-created
    // code), so only her membership denies hers.
    test.each<[string, () => h.Db]>([
        ["an existing member whose member doc names its code", () => carol.verified],
        ["a user in no household, outside a join batch", () => dan.verified],
    ])("denied: the delete of an open invite by %s", async (_what, db) => {
        await assertFails(db().doc(inviteDoc(JOIN)).delete());
    });

    // The one-household check (PLAN 3.1): the users doc exists and holds null before the batch, this
    // household after it; a stale value must be self-healed first (OQ-5). The users-doc rule also
    // denies the rows that create the doc or move it from another household. Isolated: the first row
    // the value after the batch, the second that it is this household (HH-01), the last the null
    // before it.
    test.each<[string, Record<string, Fields | null>, Join]>([
        ["without the users-doc write", {}, { users: null }],
        ["into a second household in the same batch", {}, { twin: [AWAY, code(AWAY, "e")] }],
        ["with no users doc, the batch creating it", { [user(DAN)]: null }, { users: "set" }],
        ["with no users doc and no users-doc write", { [user(DAN)]: null }, { users: null }],
        [
            "while householdId names another live household he is a member of",
            { [user(DAN)]: { householdId: AWAY }, [member(AWAY, DAN)]: membership("member") },
            {},
        ],
        [
            "while householdId is stale: removed from another",
            { [user(DAN)]: { householdId: AWAY } },
            {},
        ],
        ["while householdId is stale: a tombstone", { [user(DAN)]: { householdId: TOMB } }, {}],
        [
            "while householdId still names this household, from before a removal",
            { [user(DAN)]: { householdId: HOME } },
            { users: null },
        ],
    ])("denied: a join %s", async (_what, docs, j) => {
        await seed(docs);
        await assertFails(join(dan.verified, j));
    });

    // LIVE (PLAN 3.1): erin's member doc and her invite are still there, but under a tombstone only
    // the owner's cleanup and the P6 delete write (M1-11).
    test("denied: a join under a tombstone, with an open invite", async () => {
        await assertFails(join(dan.verified, { hid: TOMB, via: code(TOMB, "t") }));
    });

    // P4 and PLAN 3.1 field validation, the joiner's member doc: role, displayName, joinedAt and
    // viaInvite (Join only).
    test.each<[string, Join]>([
        ["an unknown field", { doc: { color: "red" } }],
        ...Object.keys({ ...JOINER, viaInvite: JOIN }).map((k): [string, Join] => [
            `no ${k}`,
            { drop: k },
        ]),
        ["role owner", { doc: { role: "owner" } }],
        ["a role neither owner nor member", { doc: { role: "admin" } }],
        ["joinedAt not the request time", { doc: { joinedAt: T0 } }],
        ["a display name of 51 characters", { doc: { displayName: `${FIFTY}a` } }],
        ["a display name of spaces only", { doc: { displayName: "   " } }],
    ])("denied: the joiner's member doc with %s", async (_what, j) => {
        await assertFails(join(dan.verified, j));
    });

    // P4 types, in a world the app never makes: frank owns NEST without a member doc there, so the
    // owner's path of Delete invite deletes the invite with the id "42", and only the type check
    // denies a viaInvite of the number 42 (a path takes it as the id "42").
    test("denied: the type of viaInvite, a number that names an invite", async () => {
        const NEST = "household00000000004";
        await seed({
            [`households/${NEST}`]: household(FRANK),
            [member(NEST, ALICE)]: membership("member"),
            [inviteDoc("42")]: stored(NEST, ALICE),
        });
        const j: Join = { hid: NEST, via: "42", doc: { viaInvite: 42 } };
        await assertFails(join(frank.verified, j, FRANK));
    });
});
