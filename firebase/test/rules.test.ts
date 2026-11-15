import * as fs from "node:fs";
import * as path from "node:path";
import {
    assertFails,
    initializeTestEnvironment,
    type RulesTestContext,
    type RulesTestEnvironment,
} from "@firebase/rules-unit-testing";

// The rules-unit-testing contexts hand out the compat Firestore type, so the tests use the compat
// calls (doc().get(), set(), update(), delete(), collection().get(), add()): the same operations
// as the modular getDoc, setDoc, updateDoc, deleteDoc, getDocs and addDoc, with no type casts.
type Db = ReturnType<RulesTestContext["firestore"]>;

let env: RulesTestEnvironment;

beforeAll(async () => {
    env = await initializeTestEnvironment({
        projectId: "demo-listicles",
        firestore: {
            rules: fs.readFileSync(path.join(__dirname, "..", "firestore.rules"), "utf8"),
        },
    });
});

afterAll(async () => {
    await env.cleanup();
});

beforeEach(async () => {
    await env.clearFirestore();
});

// Every planned top-level and nested path. Each must deny all operations for
// anonymous and signed-in clients until the real rules land.
const PATHS = [
    "users/alice",
    "households/h1",
    "households/h1/members/alice",
    "households/h1/lists/l1",
    "households/h1/lists/l1/items/i1",
    "households/h1/invites/inv1",
    "anything/else",
];

const CLIENTS = {
    anonymous: (): Db => env.unauthenticatedContext().firestore(),
    "signed-in": (): Db => env.authenticatedContext("alice").firestore(),
};

describe.each(Object.keys(CLIENTS) as (keyof typeof CLIENTS)[])("default deny (%s)", (who) => {
    test.each(PATHS)("%s: get", async (p) => {
        await assertFails(CLIENTS[who]().doc(p).get());
    });

    test.each(PATHS)("%s: create/overwrite", async (p) => {
        await assertFails(
            CLIENTS[who]().doc(p).set({ name: "y", ownerUid: "alice", deleted: false }),
        );
    });

    test.each(PATHS)("%s: update and delete an existing doc", async (p) => {
        await env.withSecurityRulesDisabled(async (ctx) => {
            await ctx.firestore().doc(p).set({ name: "seed" });
        });
        await assertFails(CLIENTS[who]().doc(p).update({ name: "z" }));
        await assertFails(CLIENTS[who]().doc(p).delete());
    });

    test("list and add on a collection", async () => {
        const db = CLIENTS[who]();
        await assertFails(db.collection("households").get());
        await assertFails(db.collection("households/h1/lists").add({ name: "n" }));
    });
});
