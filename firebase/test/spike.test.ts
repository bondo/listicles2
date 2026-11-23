import {
    assertFails,
    initializeTestEnvironment,
    type RulesTestEnvironment,
} from "@firebase/rules-unit-testing";
import firebase from "firebase/compat/app";
import * as fs from "node:fs";
import * as path from "node:path";
import * as h from "./harness";

// M1-09, the rules spike (PLAN 3.1 items a-e; docs/adr/0002-rules-spike.md) on the blocks of
// spike.rules, inserted under the documents match of firestore.rules and never deployed. M1-12, M1-54,
// M1-53 and M2 move each block into firestore.rules with its full tests; these stay as regression
// tests, so every payload has its PLAN section 3 shape. Item (e) adds blocks that only make n calls.
type Clients = Record<h.Client, h.Db>;
type Query = firebase.firestore.Query;
let env: RulesTestEnvironment;
let alice: Clients;
let bob: Clients;
let carol: Clients;
let dan: Clients;

const ALICE = h.UID;
const BOB = "bob";
const CAROL = "carol";
const DAN = "dan"; // joins HOME in (b)
const EVE = "eve";
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
const list = (createdBy: string, sharedWith: string | null): object => ({
    ...{ kind: "PLAIN", name: "List", createdBy, sharedWith, schemaVersion: 1 },
    ...{ createdAt: T0, updatedAt: T0, updatedBy: createdBy },
});

// (e): n exists() calls on n distinct documents, limits/<block>-<i>.
const LIMITS: Record<string, [string, number]> = {
    get10: ["get", 10],
    get11: ["get", 11],
    writeA: ["create", 10],
    writeB: ["create", 10],
    write11: ["create", 11],
    write1: ["create", 1],
    query20: ["list", 20],
    query21: ["list", 21],
};
const limitDocs = (block: string, n: number): string[] =>
    Array.from({ length: n }, (_, i) => `limits/${block}-${String(i)}`);
const calls = (block: string, n: number): string =>
    limitDocs(block, n)
        .map((p) => `exists(/databases/$(database)/documents/${p})`)
        .join(" && ");
const BLOCKS: [string, string, string][] = [
    ...Object.entries(LIMITS).map(([b, [method, n]]): [string, string, string] => [
        b,
        method,
        calls(b, n),
    ]),
    // An || operand that fails after 10 calls, then one that makes 10 calls on other documents.
    ["orFails", "get", `(${calls("get10", 10)} && false) || (${calls("writeA", 10)})`],
    ["letCharged", "get", `unusedLet() || (${calls("writeB", 10)})`],
    ["argCharged", "get", `unusedArg(${calls("writeA", 10)}) || (${calls("writeB", 10)})`],
    ["andStops", "get", `(false && ${calls("writeA", 10)}) || (${calls("writeB", 10)})`],
];
const LIMIT_RULES = BLOCKS.map(
    ([block, method, condition]) =>
        `\n    match /${block}/{id} {\n      allow ${method}: if signedIn() && (${condition});\n    }`,
);
// (e): a function whose unused let makes 10 calls, and one that never uses its argument.
const EVALUATION = `
    function unusedLet() { let x = ${calls("writeA", 10)}; return false; }
    function unusedArg(x) { return false; }`;
const SPIKE = fs.readFileSync(path.join(__dirname, "spike.rules"), "utf8");
const RULES = h.underDocuments(h.RULES, `\n${SPIKE}${EVALUATION}${LIMIT_RULES.join("")}`);

async function seed(docs: Record<string, object>): Promise<void> {
    await env.withSecurityRulesDisabled(async (admin) => {
        for (const [p, data] of Object.entries(docs)) await admin.firestore().doc(p).set(data);
    });
}

// A query through h.verifiedOnly, then the ids the verified client gets.
async function listed(clients: Clients, query: (db: h.Db) => Query): Promise<string[]> {
    await h.verifiedOnly(clients, (db) => query(db).get());
    return (await query(clients.verified).get()).docs.map((d) => d.id);
}

beforeAll(async () => {
    env = await initializeTestEnvironment({ projectId: h.PROJECT, firestore: { rules: RULES } });
    alice = h.connect(env);
    bob = h.connect(env, BOB);
    carol = h.connect(env, CAROL);
    dan = h.connect(env, DAN);
});

afterAll(async () => {
    await env.cleanup();
});

// HOME: bob owns it, alice and carol are plain members; carol once joined with JOIN's code, which a
// member then created again (P3's residual). AWAY: eve's. TOMB: bob's tombstone, alice still in it.
beforeEach(async () => {
    await env.clearFirestore();
    await seed({
        [`households/${HOME}`]: household(BOB),
        [`households/${AWAY}`]: household(EVE),
        [`households/${TOMB}`]: household(BOB, true),
        [member(HOME, BOB)]: membership("owner"),
        [member(HOME, ALICE)]: membership("member"),
        [member(HOME, CAROL)]: { ...membership("member"), viaInvite: JOIN },
        [member(AWAY, EVE)]: membership("owner"),
        [member(TOMB, BOB)]: membership("owner"),
        [member(TOMB, ALICE)]: membership("member"),
        [`users/${DAN}`]: { householdId: null },
        [`invites/${JOIN}`]: invite(HOME, BOB),
        [`invites/${code(HOME, "a")}`]: invite(HOME, ALICE),
        [`invites/${code(HOME, "x")}`]: invite(HOME, BOB, -DAY),
        [`invites/${code(HOME, "l")}`]: invite(HOME, "lee"), // lee left HOME
        [`invites/${code(AWAY, "f")}`]: invite(AWAY, EVE),
        [`invites/${code(TOMB, "t")}`]: invite(TOMB, ALICE),
        "lists/home": list(BOB, HOME),
        "lists/mine": list(ALICE, null),
        "lists/away": list(EVE, AWAY),
        "lists/tomb": list(BOB, TOMB),
    });
});

test("every allow statement of the spike requires signedIn()", () => {
    expect(h.withoutSignedIn(RULES)).toEqual([]);
});

// (a) PLAN 3.1 Query invites, as the owner decided on #280 (M1-O12, #15 comment 7081223083): a plain
// member lists the invites they created, the owner all of the household's.
describe("(a) the invite list query on householdId, with M(uid) and LIVE", () => {
    const invites = (db: h.Db): Query => db.collection("invites");
    const all = (db: h.Db, hid = HOME): Query => invites(db).where("householdId", "==", hid);
    const mine = (db: h.Db, hid = HOME): Query => all(db, hid).where("createdBy", "==", ALICE);

    test("verified only: a plain member lists the invites she created", async () => {
        expect(await listed(alice, mine)).toEqual([code(HOME, "a")]);
    });

    test("verified only: the owner lists all of the household's", async () => {
        const want = [code(HOME, "a"), JOIN, code(HOME, "l"), code(HOME, "x")];
        expect(await listed(bob, all)).toEqual(want);
    });

    test.each<[string, (db: h.Db) => Query]>([
        ["a plain member, all of the household's", all],
        ["a plain member, another's", (db) => all(db).where("createdBy", "==", BOB)],
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

// (b) PLAN 3.1 Join: one batch creates dan's member doc, deletes the invite and sets his users doc,
// and each rule sees the others' writes through existsAfter and getAfter. Item (e): M1's largest fixed
// batch.
describe("(b) the join batch, with existsAfter and getAfter", () => {
    interface Join {
        hid?: string;
        via?: string;
        doc?: object; // replaces fields of dan's member doc
        other?: boolean; // adds a member doc for another uid (#206)
        invite?: boolean;
        user?: boolean;
        stale?: string; // dan's householdId before the batch, not yet self-healed
        burn?: string; // deletes this other invite too
    }
    const JOINER = { role: "member", displayName: "Dan", joinedAt: NOW };
    function join(db: h.Db, j: Join = {}): Promise<void> {
        const hid = j.hid ?? HOME;
        const via = j.via ?? JOIN;
        const doc = { ...JOINER, viaInvite: via, ...j.doc };
        const batch = db.batch();
        batch.set(db.doc(member(hid, DAN)), doc);
        if (j.other === true) batch.set(db.doc(member(hid, "zoe")), doc);
        if (j.invite !== false) batch.delete(db.doc(`invites/${via}`));
        if (j.burn !== undefined) batch.delete(db.doc(`invites/${j.burn}`));
        if (j.user !== false) batch.update(db.doc(`users/${DAN}`), { householdId: hid });
        return batch.commit();
    }

    test("verified only: the whole batch", async () => {
        await h.verifiedOnly(dan, (db) => join(db));
    });

    test.each<[string, Join]>([
        ["without the invite delete (single use)", { invite: false }],
        ["without the users-doc set (one household)", { user: false }],
        ["with householdId still HOME, from before a removal", { stale: HOME, user: false }],
        ["with a member doc for another uid too (P1, #206)", { other: true }],
        ["deleting another invite of the household too", { burn: code(HOME, "a") }],
        ["as owner", { doc: { role: "owner" } }],
        ["with a joinedAt that is not the request time", { doc: { joinedAt: T0 } }],
        ["with an expired invite", { via: code(HOME, "x") }],
        ["with an invite whose creator left", { via: code(HOME, "l") }],
        ["with another household's invite", { via: code(AWAY, "f") }],
        ["into a tombstone", { hid: TOMB, via: code(TOMB, "t") }],
    ])("denied: %s", async (_what, j) => {
        if (j.stale !== undefined) await seed({ [`users/${DAN}`]: { householdId: j.stale } });
        await assertFails(join(dan.verified, j));
    });

    test.each<[string, () => h.Db]>([
        ["a member whose member doc names its code (burning it)", () => carol.verified],
        ["a non-member, outside a join batch", () => dan.verified],
    ])("denied: the invite's delete by %s", async (_what, db) => {
        await assertFails(db().doc(`invites/${JOIN}`).delete());
    });
});

// (c) PLAN 3.1 Transfer ownership: one batch updates ownerUid and both roles, and each rule checks the
// others' result through getAfter, so a partial transfer is denied.
describe("(c) the transfer batch", () => {
    // In `hid`: ownerUid to `to`, and the roles of `roles`, owner for `to` and member for anyone else;
    // `extra` adds fields to the household update or to each role update.
    interface Extra {
        household?: object;
        member?: object;
    }
    function transfer(
        db: h.Db,
        hid: string,
        to: string,
        roles: string[],
        extra: Extra = {},
    ): Promise<void> {
        const batch = db.batch();
        batch.update(db.doc(`households/${hid}`), { ownerUid: to, ...extra.household });
        for (const uid of roles) {
            const role = uid === to ? "owner" : "member";
            batch.update(db.doc(member(hid, uid)), { role, ...extra.member });
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
        await assertFails(transfer((caller === BOB ? bob : alice).verified, hid, to, roles));
    });

    test.each<[string, Extra]>([
        ["another household field", { household: { name: "Away" } }],
        ["another member field", { member: { displayName: "Owner" } }],
    ])("denied: the owner's whole batch, changing %s too", async (_what, extra) => {
        await assertFails(transfer(bob.verified, HOME, ALICE, [BOB, ALICE], extra));
    });

    test("denied: the owner's role update alone, a plain member to owner", async () => {
        await assertFails(bob.verified.doc(member(HOME, CAROL)).update({ role: "owner" }));
    });
});

// (d) PLAN 3.1 list read (M2), LIST-01's two queries: createdBy == uid, and sharedWith == hid for a
// member of that live household.
describe("(d) the list query on sharedWith, with M(hid) and LIVE", () => {
    const lists = (db: h.Db): Query => db.collection("lists");
    const shared = (hid: string) => (db: h.Db) => lists(db).where("sharedWith", "==", hid);

    test.each<[string, (db: h.Db) => Query, string]>([
        ["a member's query on sharedWith", shared(HOME), "home"],
        [
            "the creator's query on createdBy",
            (db) => lists(db).where("createdBy", "==", ALICE),
            "mine",
        ],
    ])("verified only: %s", async (_what, query, id) => {
        expect(await listed(alice, query)).toEqual([id]);
    });

    test.each<[string, (db: h.Db) => Query]>([
        ["sharedWith a household she is no member of", shared(AWAY)],
        ["sharedWith a tombstone, her member doc still there", shared(TOMB)],
        ["createdBy another user", (db) => lists(db).where("createdBy", "==", BOB)],
        ["no filter", lists],
    ])("denied: %s", async (_what, query) => {
        await assertFails(query(alice.verified).get());
    });
});

// (e) What the emulator enforces of the access-call limits (10 per single-document request, query and
// write in a batch, 20 per batch): the allow tests of (b) and (c) prove only what it enforces.
describe("(e) the access-call limits in the emulator", () => {
    beforeEach(async () => {
        const docs = Object.entries(LIMITS).flatMap(([block, [, n]]) => limitDocs(block, n));
        const targets = ["get10/x", "get11/x", "orFails/x"];
        await seed(Object.fromEntries([...docs, ...targets].map((p) => [p, {}])));
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

    test("a batch: 10 calls a write and 20 in all allowed, 11 in a write or 21 in all denied", async () => {
        await h.verifiedOnly(alice, (db) => batch(db, ["writeA", "writeB"]));
        await overLimit(batch(alice.verified, ["write11", "write1"]));
        await overLimit(batch(alice.verified, ["writeA", "writeB", "write1"]));
    });

    // So the emulator cannot show the worst case, every call counted: ADR 0002 counts that by hand.
    test("calls on one document count once, also across the writes of a batch", async () => {
        await h.verifiedOnly(alice, (db) => batch(db, Array<string>(21).fill("write1")));
    });

    // So a rule's calls depend on its layout: ADR 0002 orders the paths so that those tried before a
    // batch's own fail without a call.
    test("the calls of an || operand that fails count: 10 there and 10 after it, denied", async () => {
        await overLimit(alice.verified.doc("orFails/x").get());
    });

    // ADR 0002's layout rests on these, so a path's calls come after its call-free conditions.
    test("charged: an unused let's calls and an unused argument's; not: those after false &&", async () => {
        await overLimit(alice.verified.doc("letCharged/x").get());
        await overLimit(alice.verified.doc("argCharged/x").get());
        await h.verifiedOnly(alice, (db) => db.doc("andStops/x").get());
    });

    // Not the documented 10: an emulator test of a query proves nothing between 11 and 20 calls.
    test("a query: 20 calls allowed, 21 denied", async () => {
        await h.verifiedOnly(alice, (db) => db.collection("query20").get());
        await overLimit(alice.verified.collection("query21").get());
    });
});
