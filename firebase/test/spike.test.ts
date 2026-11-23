import {
    assertFails,
    initializeTestEnvironment,
    type RulesTestEnvironment,
} from "@firebase/rules-unit-testing";
import firebase from "firebase/compat/app";
import * as fs from "node:fs";
import * as path from "node:path";
import * as h from "./harness";

// M1-09, the rules spike (PLAN 3.1 items a-e; docs/adr/0002-rules-spike.md): the invite list query,
// the join and transfer batches and the list query, as the blocks of spike.rules, inserted under the
// documents match of firestore.rules and never deployed. M1-12, M1-54, M1-53 and M2 move each block
// into firestore.rules with its full allow and deny tests; these tests stay as regression tests, so
// every payload has the full shape of PLAN section 3. Item (e) adds blocks that only make n calls.
let env: RulesTestEnvironment;
let alice: Record<h.Client, h.Db>;
let bob: Record<h.Client, h.Db>;
let carol: Record<h.Client, h.Db>;

const ALICE = h.UID;
const BOB = "bob"; // owns HOME and TOMB
const CAROL = "carol"; // a plain member of HOME
const EVE = "eve"; // owns AWAY
const HOME = "household00000000001";
const AWAY = "household00000000002";
const TOMB = "household00000000003";
const code = (hid: string, c: string): string => `${hid}_${c.repeat(22)}`;
const JOIN = code(HOME, "j");
const member = (hid: string, uid: string): string => `households/${hid}/members/${uid}`;
const T0 = new Date(0);
const DAY = 86_400_000;
const NOW = firebase.firestore.FieldValue.serverTimestamp();
const household = (ownerUid: string, deleted = false): object => ({
    ...{ name: deleted ? "" : "Home", createdBy: ownerUid, createdAt: T0, ownerUid, deleted },
});
const membership = (role: string): object => ({ role, displayName: "Name", joinedAt: T0 });
const invite = (hid: string, createdBy: string, expiresIn = DAY): object => ({
    ...{ householdId: hid, householdName: "Home", createdBy, createdAt: T0 },
    expiresAt: new Date(Date.now() + expiresIn),
});
const ids = async (query: Promise<firebase.firestore.QuerySnapshot>): Promise<string[]> =>
    (await query).docs.map((d) => d.id);

// (e) blocks: n exists() calls on n distinct documents, limits/<block>-<i>.
const LIMITS: Record<string, [string, number]> = {
    get10: ["get", 10],
    get11: ["get", 11],
    writeA: ["create", 10],
    writeB: ["create", 10],
    write1: ["create", 1],
    query20: ["list", 20],
    query21: ["list", 21],
};
const limitDocs = (block: string, n: number): string[] =>
    Array.from({ length: n }, (_, i) => `limits/${block}-${String(i)}`);
const BLOCKS = Object.entries(LIMITS).map(([block, [method, n]]) => {
    const calls = limitDocs(block, n).map((p) => `exists(/databases/$(database)/documents/${p})`);
    return `\n    match /${block}/{id} {\n      allow ${method}: if signedIn() && ${calls.join(" && ")};\n    }`;
});
const SPIKE = fs.readFileSync(path.join(__dirname, "spike.rules"), "utf8");
const RULES = h.underDocuments(h.RULES, `\n${SPIKE}${BLOCKS.join("")}`);

async function seed(docs: Record<string, object>): Promise<void> {
    await env.withSecurityRulesDisabled(async (admin) => {
        for (const [p, data] of Object.entries(docs)) await admin.firestore().doc(p).set(data);
    });
}

beforeAll(async () => {
    env = await initializeTestEnvironment({ projectId: h.PROJECT, firestore: { rules: RULES } });
    alice = h.connect(env);
    bob = h.connect(env, BOB);
    carol = h.connect(env, CAROL);
});

afterAll(async () => {
    await env.cleanup();
});

// HOME (bob's, carol a member) and AWAY (eve's) are live; TOMB is bob's tombstone. Each item adds alice.
beforeEach(async () => {
    await env.clearFirestore();
    await seed({
        [`households/${HOME}`]: household(BOB),
        [`households/${AWAY}`]: household(EVE),
        [`households/${TOMB}`]: household(BOB, true),
        [member(HOME, BOB)]: membership("owner"),
        [member(HOME, CAROL)]: membership("member"),
        [member(AWAY, EVE)]: membership("owner"),
        [member(TOMB, BOB)]: membership("owner"),
    });
});

test("every allow statement of the spike requires signedIn()", () => {
    expect(h.withoutSignedIn(RULES)).toEqual([]);
});

// (a) PLAN 3.1 Query invites, as the owner decided on #280 (M1-O12, #15 comment 7081223083): a plain
// member lists the invites they created, the owner all of the household's.
describe("(a) the invite list query on householdId, with M(uid) and LIVE", () => {
    beforeEach(async () => {
        await seed({
            [member(HOME, ALICE)]: membership("member"),
            [member(TOMB, ALICE)]: membership("member"),
            [`invites/${code(HOME, "a")}`]: invite(HOME, ALICE),
            [`invites/${code(HOME, "b")}`]: invite(HOME, BOB),
            [`invites/${code(AWAY, "e")}`]: invite(AWAY, EVE),
            [`invites/${code(TOMB, "t")}`]: invite(TOMB, ALICE),
        });
    });
    const invites = (db: h.Db): firebase.firestore.Query => db.collection("invites");
    const mine = (db: h.Db, hid: string): firebase.firestore.Query =>
        invites(db).where("householdId", "==", hid).where("createdBy", "==", ALICE);

    test("verified only: a plain member lists the invites she created", async () => {
        await h.verifiedOnly(alice, (db) => mine(db, HOME).get());
        expect(await ids(mine(alice.verified, HOME).get())).toEqual([code(HOME, "a")]);
    });

    test("verified only: the owner lists all of the household's", async () => {
        const all = (db: h.Db): firebase.firestore.Query =>
            invites(db).where("householdId", "==", HOME);
        await h.verifiedOnly(bob, (db) => all(db).get());
        expect(await ids(all(bob.verified).get())).toEqual([code(HOME, "a"), code(HOME, "b")]);
    });

    test.each<[string, (db: h.Db) => firebase.firestore.Query]>([
        [
            "a plain member, all of the household's",
            (db) => invites(db).where("householdId", "==", HOME),
        ],
        ["no householdId filter", (db) => invites(db).where("createdBy", "==", ALICE)],
        ["no filter", invites],
        ["a household she is no member of", (db) => mine(db, AWAY)],
        ["a tombstone, her member doc still there", (db) => mine(db, TOMB)],
        [
            "householdId in two households, one not hers",
            (db) =>
                invites(db)
                    .where("householdId", "in", [HOME, AWAY])
                    .where("createdBy", "==", ALICE),
        ],
    ])("denied: %s", async (_what, query) => {
        await assertFails(query(alice.verified).get());
    });
});

// (b) PLAN 3.1 Join: one batch creates alice's member doc, deletes the invite and sets her users doc,
// and each rule sees the others' writes through existsAfter and getAfter. Item (e): with 12 calls in
// the worst case, M1's largest batch.
describe("(b) the join batch, with existsAfter and getAfter", () => {
    beforeEach(async () => {
        await seed({
            [`users/${ALICE}`]: { householdId: null },
            [`invites/${JOIN}`]: invite(HOME, BOB),
            [`invites/${code(HOME, "x")}`]: invite(HOME, BOB, -DAY),
            [`invites/${code(HOME, "l")}`]: invite(HOME, "dave"), // dave left HOME
            [`invites/${code(AWAY, "f")}`]: invite(AWAY, EVE),
            [`invites/${code(TOMB, "t")}`]: invite(TOMB, BOB),
        });
    });

    interface Join {
        hid?: string;
        via?: string;
        doc?: object; // replaces fields of alice's member doc
        other?: boolean; // adds a member doc for another uid (#206)
        invite?: boolean;
        user?: boolean;
    }
    function join(db: h.Db, j: Join = {}): Promise<void> {
        const hid = j.hid ?? HOME;
        const via = j.via ?? JOIN;
        const doc = {
            role: "member",
            displayName: "Alice",
            joinedAt: NOW,
            viaInvite: via,
            ...j.doc,
        };
        const batch = db.batch();
        batch.set(db.doc(member(hid, ALICE)), doc);
        if (j.other === true) batch.set(db.doc(member(hid, "zoe")), doc);
        if (j.invite !== false) batch.delete(db.doc(`invites/${via}`));
        if (j.user !== false) batch.update(db.doc(`users/${ALICE}`), { householdId: hid });
        return batch.commit();
    }

    test("verified only: the whole batch", async () => {
        await h.verifiedOnly(alice, (db) => join(db));
    });

    test.each<[string, Join]>([
        ["without the invite delete (single use)", { invite: false }],
        ["without the users-doc set (one household)", { user: false }],
        ["with a member doc for another uid too (P1, #206)", { other: true }],
        ["as owner", { doc: { role: "owner" } }],
        ["with a joinedAt that is not the request time", { doc: { joinedAt: T0 } }],
        ["with an expired invite", { via: code(HOME, "x") }],
        ["with an invite whose creator left", { via: code(HOME, "l") }],
        ["with another household's invite", { via: code(AWAY, "f") }],
        ["into a tombstone", { hid: TOMB, via: code(TOMB, "t") }],
    ])("denied: %s", async (_what, j) => {
        await assertFails(join(alice.verified, j));
    });

    test("denied: a member deletes another's invite (burns it)", async () => {
        await assertFails(carol.verified.doc(`invites/${JOIN}`).delete());
    });
});

// (c) PLAN 3.1 Transfer ownership: one batch updates ownerUid and both roles, and each rule checks the
// others' result through getAfter, so a partial transfer is denied.
describe("(c) the transfer batch", () => {
    beforeEach(async () => {
        await seed({
            [member(HOME, ALICE)]: membership("member"),
            [member(TOMB, ALICE)]: membership("member"),
        });
    });

    // In `hid`: ownerUid to `to`, and the roles of `roles`, owner for `to` and member for anyone else.
    function transfer(db: h.Db, hid: string, to: string, roles: string[]): Promise<void> {
        const batch = db.batch();
        batch.update(db.doc(`households/${hid}`), { ownerUid: to });
        for (const uid of roles) {
            batch.update(db.doc(member(hid, uid)), { role: uid === to ? "owner" : "member" });
        }
        return batch.commit();
    }

    test("verified only: the owner's whole batch", async () => {
        await h.verifiedOnly(bob, (db) => transfer(db, HOME, ALICE, [BOB, ALICE]));
    });

    test.each<[string, string, string, string, string[]]>([
        ["the household update alone", BOB, HOME, ALICE, []],
        ["only the old owner's role (no owner)", BOB, HOME, ALICE, [BOB]],
        ["only the new owner's role (two owners)", BOB, HOME, ALICE, [ALICE]],
        ["a plain member's whole batch, to herself", ALICE, HOME, ALICE, [BOB, ALICE]],
        ["to a non-member", BOB, HOME, "zoe", [BOB]],
        ["under a tombstone", BOB, TOMB, ALICE, [BOB, ALICE]],
    ])("denied: %s", async (_what, caller, hid, to, roles) => {
        const db = (caller === BOB ? bob : alice).verified;
        await assertFails(transfer(db, hid, to, roles));
    });
});

// (d) PLAN 3.1 list read (M2), LIST-01's two queries: createdBy == uid, and sharedWith == hid for a
// member of that live household.
describe("(d) the list query on sharedWith, with M(hid) and LIVE", () => {
    const list = (createdBy: string, sharedWith: string | null): object => ({
        ...{ kind: "PLAIN", name: "List", createdBy, sharedWith, schemaVersion: 1 },
        ...{ createdAt: T0, updatedAt: T0, updatedBy: createdBy },
    });
    beforeEach(async () => {
        await seed({
            [member(HOME, ALICE)]: membership("member"),
            [member(TOMB, ALICE)]: membership("member"),
            "lists/home": list(BOB, HOME),
            "lists/mine": list(ALICE, null),
            "lists/away": list(EVE, AWAY),
            "lists/tomb": list(BOB, TOMB),
        });
    });
    const lists = (db: h.Db): firebase.firestore.Query => db.collection("lists");
    const shared = (db: h.Db, hid: string): firebase.firestore.Query =>
        lists(db).where("sharedWith", "==", hid);
    const created = (db: h.Db): firebase.firestore.Query =>
        lists(db).where("createdBy", "==", ALICE);

    test("verified only: a member's query on sharedWith", async () => {
        await h.verifiedOnly(alice, (db) => shared(db, HOME).get());
        expect(await ids(shared(alice.verified, HOME).get())).toEqual(["home"]);
    });

    test("verified only: the creator's query on createdBy", async () => {
        await h.verifiedOnly(alice, (db) => created(db).get());
        expect(await ids(created(alice.verified).get())).toEqual(["mine"]);
    });

    test.each([
        ["a household she is no member of", AWAY],
        ["a tombstone, her member doc still there", TOMB],
    ])("denied: sharedWith, %s", async (_what, hid) => {
        await assertFails(shared(alice.verified, hid).get());
    });

    test("denied: no filter", async () => {
        await assertFails(lists(alice.verified).get());
    });
});

// (e) What the emulator enforces of the access-call limits (10 per single-document request, query and
// write in a batch, 20 per batch): the allow tests of (b) and (c) prove only what it enforces.
describe("(e) the access-call limits in the emulator", () => {
    beforeEach(async () => {
        const docs = Object.entries(LIMITS).flatMap(([block, [, n]]) => limitDocs(block, n));
        await seed(Object.fromEntries([...docs, "get10/x", "get11/x"].map((p) => [p, {}])));
    });
    let created = 0; // a new document id for every create
    const batch = (db: h.Db, blocks: string[]): Promise<void> => {
        const b = db.batch();
        for (const block of blocks) b.set(db.doc(`${block}/w${String((created += 1))}`), {});
        return b.commit();
    };
    // Denied for the limit: the emulator's error for a call past it, not a false exists().
    const overLimit = async (request: Promise<unknown>): Promise<void> => {
        await expect(request).rejects.toMatchObject({ code: "permission-denied" });
        await expect(request).rejects.toThrow("Service call error");
    };

    test("a single-document request: 10 calls allowed, 11 denied", async () => {
        await h.verifiedOnly(alice, (db) => db.doc("get10/x").get());
        await overLimit(alice.verified.doc("get11/x").get());
    });

    test("a batch: 10 calls a write and 20 in all allowed, 21 denied", async () => {
        await h.verifiedOnly(alice, (db) => batch(db, ["writeA", "writeB"]));
        await overLimit(batch(alice.verified, ["writeA", "writeB", "write1"]));
    });

    // So the emulator cannot show the worst case, every call counted: ADR 0002 counts that by hand.
    test("calls on one document count once, also across the writes of a batch", async () => {
        await h.verifiedOnly(alice, (db) => batch(db, Array<string>(21).fill("write1")));
    });

    // Not the documented 10: an emulator test of a query proves nothing between 11 and 20 calls.
    test("a query: 20 calls allowed, 21 denied", async () => {
        await h.verifiedOnly(alice, (db) => db.collection("query20").get());
        await overLimit(alice.verified.collection("query21").get());
    });
});
