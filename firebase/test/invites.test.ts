import {
    assertFails,
    initializeTestEnvironment,
    type RulesTestEnvironment,
} from "@firebase/rules-unit-testing";
import firebase from "firebase/compat/app";
import * as h from "./harness";

// M1-12 (PLAN 3.1): the invite rows, each while the household is live. Create invite (P2, P3 #243,
// P4); read one invite, by any verified user with the code (HH-03); query invites, as the owner
// decided on #280 (M1-O12): a plain member lists the invites they created, the owner all of the
// household's; delete invite: its creator's or the owner's revoke, any member's cleanup of an
// expired one; no updates. The joiner's delete is M1-54's (spike.rules (b)); the owner's cleanup
// under a tombstone is M1-11's, so no test here reads or deletes as that owner. Each test seeds its
// world with rules off; every allow test goes through h.verifiedOnly.
type Fields = Record<string, unknown>;
type Clients = Record<h.Client, h.Db>;
type Query = firebase.firestore.Query;
let env: RulesTestEnvironment;
let alice: Clients;
let bob: Clients;
let carol: Clients;
let erin: Clients;
let eve: Clients;
let frank: Clients;
let gus: Clients;

const ALICE = h.UID;
const BOB = "bob";
const CAROL = "carol";
const DAN = "dan";
const ERIN = "erin";
const EVE = "eve";
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
const stored = (hid: string, name: string, createdBy: string, expiresIn = DAY): Fields => ({
    householdId: hid,
    householdName: name,
    createdBy,
    createdAt: T0,
    expiresAt: new Date(Date.now() + expiresIn),
});
// What the app writes (PLAN 3 invites): alice's invite of HOME, expiring a minute inside 7 days.
const fresh = (fields: Fields = {}): Fields => ({
    householdId: HOME,
    householdName: "Home",
    createdBy: ALICE,
    createdAt: NOW,
    expiresAt: new Date(Date.now() + 7 * DAY - 60_000),
    ...fields,
});
const without = (fields: Fields, key: string): Fields =>
    Object.fromEntries(Object.entries(fields).filter(([k]) => k !== key));
const create = (db: h.Db, c: string, data = fresh()): Promise<void> =>
    db.doc(inviteDoc(c)).set(data);

// Documents set, or deleted where null, with rules off.
async function seed(docs: Record<string, Fields | null>): Promise<void> {
    await env.withSecurityRulesDisabled(async (admin) => {
        for (const [p, data] of Object.entries(docs)) {
            const ref = admin.firestore().doc(p);
            await (data === null ? ref.delete() : ref.set(data));
        }
    });
}

// A query through h.verifiedOnly, then the ids the verified client gets.
async function listed(clients: Clients, query: (db: h.Db) => Query): Promise<string[]> {
    await h.verifiedOnly(clients, (db) => query(db).get());
    return (await query(clients.verified).get()).docs.map((d) => d.id);
}

beforeAll(async () => {
    env = await initializeTestEnvironment({ projectId: h.PROJECT, firestore: { rules: h.RULES } });
    alice = h.connect(env);
    bob = h.connect(env, BOB);
    carol = h.connect(env, CAROL);
    erin = h.connect(env, ERIN);
    eve = h.connect(env, EVE);
    frank = h.connect(env, FRANK);
    gus = h.connect(env, GUS);
});

afterAll(async () => {
    await env.cleanup();
});

// HOME: bob owns it, alice and carol are plain members; gus was removed and his invite is left over
// (his householdId not self-healed yet). Open invites (a day left) by alice, bob, carol and gus,
// expired ones by alice and bob. AWAY: eve's. TOMB: dan's tombstone, its cleanup not done, so dan's
// and erin's member docs and their invites are still there. Frank is in no household.
beforeEach(async () => {
    await env.clearFirestore();
    await seed({
        [`households/${HOME}`]: household(BOB),
        [`households/${AWAY}`]: household(EVE, "Away"),
        [`households/${TOMB}`]: household(DAN, "", true),
        [member(HOME, BOB)]: membership("owner"),
        [member(HOME, ALICE)]: membership("member"),
        [member(HOME, CAROL)]: membership("member"),
        [member(AWAY, EVE)]: membership("owner"),
        [member(TOMB, DAN)]: membership("owner"),
        [member(TOMB, ERIN)]: membership("member"),
        [`users/${GUS}`]: { householdId: HOME },
        [inviteDoc(code(HOME, "a"))]: stored(HOME, "Home", ALICE),
        [inviteDoc(code(HOME, "y"))]: stored(HOME, "Home", ALICE, -DAY),
        [inviteDoc(code(HOME, "b"))]: stored(HOME, "Home", BOB),
        [inviteDoc(code(HOME, "x"))]: stored(HOME, "Home", BOB, -DAY),
        [inviteDoc(code(HOME, "c"))]: stored(HOME, "Home", CAROL),
        [inviteDoc(code(HOME, "g"))]: stored(HOME, "Home", GUS),
        [inviteDoc(code(AWAY, "e"))]: stored(AWAY, "Away", EVE),
        [inviteDoc(code(TOMB, "t"))]: stored(TOMB, "Old home", ERIN), // the name outlives it (#281)
        [inviteDoc(code(TOMB, "x"))]: stored(TOMB, "Old home", DAN, -DAY),
    });
});

describe("Create invite", () => {
    // A member's invite of the live household, the code well-formed (P3), the name the household's
    // (P2). A member re-creating a revoked code of her own household is P3's accepted residual.
    test.each<[string, () => Clients, string, Fields]>([
        ["a plain member's", () => alice, code(HOME, "n"), fresh()],
        ["the owner's", () => bob, code(HOME, "n"), fresh({ createdBy: BOB })],
        ["a secret holding _ and -", () => alice, `${HOME}_${"_-".repeat(11)}`, fresh()],
        [
            "a revoked code of the household, again",
            () => carol,
            code(HOME, "r"),
            fresh({ createdBy: CAROL }),
        ],
    ])("verified only: %s", async (_what, caller, c, data) => {
        await h.verifiedOnly(caller(), (db) => create(db, c, data));
    });

    // P4: householdName is the household's name, whatever that name is.
    test.each<[string, string]>([
        ["exactly 50 characters", FIFTY],
        ["50 non-BMP code points", NON_BMP],
    ])("verified only: a household name of %s, copied", async (_what, name) => {
        await seed({ [`households/${HOME}`]: household(BOB, name) });
        await h.verifiedOnly(alice, (db) =>
            create(db, code(HOME, "n"), fresh({ householdName: name })),
        );
    });

    // P2 (#200): the join screen shows the stored name, so it must be the household's.
    test.each<[string, string, string]>([
        ["51 characters, the household's 50 and one more", FIFTY, `${FIFTY}a`],
        ["spaces only", "Home", "   "],
        ["another household's", "Home", "Away"],
    ])("denied: a householdName of %s", async (_what, name, householdName) => {
        await seed({ [`households/${HOME}`]: household(BOB, name) });
        await assertFails(create(alice.verified, code(HOME, "n"), fresh({ householdName })));
    });

    // P4 and PLAN 3.1 field validation.
    test.each<[string, Fields]>([
        ["an unknown field", fresh({ color: "red" })],
        ...Object.keys(fresh()).map((k): [string, Fields] => [`no ${k}`, without(fresh(), k)]),
        ["createdBy another member", fresh({ createdBy: CAROL })],
        ["createdAt not the request time", fresh({ createdAt: T0 })],
        ["expiresAt 8 days ahead", fresh({ expiresAt: new Date(Date.now() + 8 * DAY) })],
        ["expiresAt that is no timestamp", fresh({ expiresAt: Date.now() + DAY })],
    ])("denied: an invite with %s", async (_what, data) => {
        await assertFails(create(alice.verified, code(HOME, "n"), data));
    });

    // P3 (#243): the code binds the invite to its household, so a used or revoked code of HOME
    // cannot come back for another household; the first row is the #243 probe.
    const s = (n: number): string => "s".repeat(n);
    test.each<[string, () => h.Db, string, Fields]>([
        [
            "HOME's revoked code, for AWAY by its owner",
            () => eve.verified,
            code(HOME, "r"),
            fresh({ householdId: AWAY, householdName: "Away", createdBy: EVE }),
        ],
        ["a code of AWAY, for HOME", () => alice.verified, code(AWAY, "n"), fresh()],
        ["a secret of 21 characters", () => alice.verified, `${HOME}_${s(21)}`, fresh()],
        ["a secret of 23 characters", () => alice.verified, `${HOME}_${s(23)}`, fresh()],
        ...[".", "*", "+", "="].map((ch): [string, () => h.Db, string, Fields] => [
            `a secret with ${ch}`,
            () => alice.verified,
            `${HOME}_${s(21)}${ch}`,
            fresh(),
        ]),
        ["the secret alone", () => alice.verified, s(22), fresh()],
        ["no _ before the secret", () => alice.verified, `${HOME}${s(22)}`, fresh()],
    ])("denied: a code, %s", async (_what, db, c, data) => {
        await assertFails(create(db(), c, data));
    });

    // P3: no data goes into the pattern, so the code check holds on its own. Seeded only to show it:
    // households whose ids are no auto-id, alice a member of each; as a regex, `.` and `*` would let
    // their ids match the other household's id.
    test.each<[string, string, string]>([
        ["19 characters, its own code", "household0000000001", "household0000000001"],
        ["21 characters, its own code", "household000000000001", "household000000000001"],
        ["a ., its own code", "househol.00000000001", "househol.00000000001"],
        ["a ., HOME's code", "househol.00000000001", HOME],
        ["a *, another household's code", "householdd*000000001", "householddd000000001"],
    ])("denied: a create in a household whose id has %s", async (_what, hid, prefix) => {
        await seed({
            [`households/${hid}`]: household(BOB),
            [member(hid, ALICE)]: membership("member"),
        });
        await assertFails(create(alice.verified, code(prefix, "n"), fresh({ householdId: hid })));
    });

    // M(uid) of householdId: a member only.
    test.each<[string, () => h.Db, string]>([
        ["a user in no household", () => frank.verified, FRANK],
        ["a removed member, his householdId still pointing at it", () => gus.verified, GUS],
        ["a member of another household", () => eve.verified, EVE],
    ])("denied: a create for HOME by %s", async (_what, db, uid) => {
        await assertFails(create(db(), code(HOME, "n"), fresh({ createdBy: uid })));
    });

    // LIVE (PLAN 3.1): erin's member doc is still there and the name is the tombstone's (""), so only
    // LIVE can deny.
    test("denied: a create under a tombstone", async () => {
        const data = fresh({ householdId: TOMB, householdName: "", createdBy: ERIN });
        await assertFails(create(erin.verified, code(TOMB, "n"), data));
    });

    test.each<[string, () => h.Db]>([
        ["its creator", () => alice.verified],
        ["the owner", () => bob.verified],
    ])("denied: an update by %s (invites have none)", async (_who, db) => {
        const invite = db().doc(inviteDoc(code(HOME, "a")));
        await assertFails(invite.update({ expiresAt: new Date(Date.now() + 2 * DAY) }));
    });
});

describe("Read one invite (get)", () => {
    const get = (c: string) => (db: h.Db) => db.doc(inviteDoc(c)).get();

    // HH-03: whoever has the code, with a verified email; h.verifiedOnly first shows the same get
    // denied to the caller's unverified token.
    test.each<[string, () => Clients]>([
        ["a user in no household", () => frank],
        ["a member of another household", () => eve],
        ["a member", () => carol],
    ])("verified only: %s reads it, householdName included (P2)", async (_who, caller) => {
        await h.verifiedOnly(caller(), get(code(HOME, "a")));
        const invite = await get(code(HOME, "a"))(caller().verified);
        expect(invite.data()).toMatchObject({ householdName: "Home" });
    });

    // LIVE: under a tombstone the invite keeps the name the soft delete cleared (#281). A code that
    // does not exist (used, revoked, never made) has no household to check: denied as well.
    test.each<[string, () => h.Db, string]>([
        ["signed out", () => frank.anonymous, code(HOME, "a")],
        ["under a tombstone, by a user in no household", () => frank.verified, code(TOMB, "t")],
        ["under a tombstone, by its creator", () => erin.verified, code(TOMB, "t")],
        ["of a code that does not exist", () => frank.verified, code(HOME, "r")],
    ])("denied: a get %s", async (_what, db, c) => {
        await assertFails(get(c)(db()));
    });
});

describe("Query invites (list), as the owner decided on #280", () => {
    const invites = (db: h.Db): Query => db.collection("invites");
    const of = (hid: string) => (db: h.Db) => invites(db).where("householdId", "==", hid);
    const by = (hid: string, uid: string) => (db: h.Db) =>
        of(hid)(db).where("createdBy", "==", uid);
    const HOMES = ["a", "b", "c", "g", "x", "y"].map((c) => code(HOME, c));

    test.each<[string, () => Clients, (db: h.Db) => Query, string[]]>([
        [
            "a plain member, the invites she created",
            () => alice,
            by(HOME, ALICE),
            [code(HOME, "a"), code(HOME, "y")],
        ],
        ["the owner, all of the household's", () => bob, of(HOME), HOMES],
        [
            "the owner, the invites he created",
            () => bob,
            by(HOME, BOB),
            [code(HOME, "b"), code(HOME, "x")],
        ],
    ])("verified only: %s", async (_who, caller, query, want) => {
        expect(await listed(caller(), query)).toEqual(want);
    });

    // #280: a plain member cannot list another member's open codes, which a removed member could
    // still use to rejoin; nobody enumerates codes without the householdId filter (M1.md section 5).
    test.each<[string, () => h.Db, (db: h.Db) => Query]>([
        ["a plain member, all of the household's", () => alice.verified, of(HOME)],
        ["a plain member, another member's", () => alice.verified, by(HOME, CAROL)],
        [
            "a plain member, no householdId filter",
            () => alice.verified,
            (db) => invites(db).where("createdBy", "==", ALICE),
        ],
        ["a plain member, no filter", () => alice.verified, invites],
        [
            "a plain member, householdId in HOME and AWAY",
            () => alice.verified,
            (db) =>
                invites(db)
                    .where("householdId", "in", [HOME, AWAY])
                    .where("createdBy", "==", ALICE),
        ],
        ["a removed member, the invites he created", () => gus.verified, by(HOME, GUS)],
        ["a user in no household, the household's", () => frank.verified, of(HOME)],
        ["the owner of another household, the household's", () => eve.verified, of(HOME)],
        ["a plain member of a tombstone, her own", () => erin.verified, by(TOMB, ERIN)],
        [
            "the owner, as a collection-group query",
            () => bob.verified,
            (db) => db.collectionGroup("invites").where("householdId", "==", HOME),
        ],
        ["signed out, the household's", () => bob.anonymous, of(HOME)],
    ])("denied: %s", async (_what, db, query) => {
        await assertFails(query(db()).get());
    });
});

describe("Delete invite: revoke, and the cleanup of expired invites", () => {
    const remove = (c: string) => (db: h.Db) => db.doc(inviteDoc(c)).delete();

    // Each path on its own: the creator (neither the owner nor expired), the owner (neither the
    // creator nor expired), any member's cleanup (neither, expired). The creator path needs no
    // M(uid): gus, removed, deletes his leftover invite.
    test.each<[string, () => Clients, string]>([
        ["its creator, a plain member, revokes it", () => alice, code(HOME, "a")],
        ["the owner revokes a plain member's", () => bob, code(HOME, "c")],
        ["a plain member deletes the owner's expired one", () => carol, code(HOME, "x")],
        ["its creator, removed since, deletes it", () => gus, code(HOME, "g")],
    ])("verified only: %s", async (_what, caller, c) => {
        await h.verifiedOnly(caller(), remove(c));
    });

    // #280: the expired-invite cleanup runs per creator and by the owner, each over the invites it
    // may list (above): the expired ones, deleted in one batch.
    test.each<[string, () => Clients, string[]]>([
        ["a plain member, her own", () => alice, [code(HOME, "y")]],
        ["the owner, the household's", () => bob, [code(HOME, "x"), code(HOME, "y")]],
    ])("verified only: the expired-invite cleanup by %s", async (_who, caller, expired) => {
        await h.verifiedOnly(caller(), (db) => {
            const batch = db.batch();
            for (const c of expired) batch.delete(db.doc(inviteDoc(c)));
            return batch.commit();
        });
    });

    test.each<[string, () => h.Db, string]>([
        ["a plain member, another member's open invite", () => carol.verified, code(HOME, "a")],
        ["a plain member, the owner's open invite", () => alice.verified, code(HOME, "b")],
        ["a removed member, an expired invite", () => gus.verified, code(HOME, "x")],
        ["a user in no household, an expired invite", () => frank.verified, code(HOME, "x")],
        ["a user in no household, an open invite", () => frank.verified, code(HOME, "a")],
        ["the owner of another household, an open invite", () => eve.verified, code(HOME, "a")],
        ["its creator, a plain member of a tombstone", () => erin.verified, code(TOMB, "t")],
        ["a plain member of a tombstone, an expired invite", () => erin.verified, code(TOMB, "x")],
        ["signed out, an expired invite", () => alice.anonymous, code(HOME, "x")],
    ])("denied: %s", async (_what, db, c) => {
        await assertFails(remove(c)(db()));
    });
});
