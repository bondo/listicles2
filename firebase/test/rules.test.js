const fs = require("fs");
const path = require("path");
const {
  initializeTestEnvironment,
  assertFails,
} = require("@firebase/rules-unit-testing");
const { doc, getDoc, setDoc } = require("firebase/firestore");

let env;

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

const {
  addDoc,
  collection,
  deleteDoc,
  getDocs,
  updateDoc,
} = require("firebase/firestore");

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
  anonymous: () => env.unauthenticatedContext().firestore(),
  "signed-in": () => env.authenticatedContext("alice").firestore(),
};

describe.each(Object.keys(CLIENTS))("default deny (%s)", (who) => {
  test.each(PATHS)("%s: get", async (p) => {
    await assertFails(getDoc(doc(CLIENTS[who](), p)));
  });

  test.each(PATHS)("%s: create/overwrite", async (p) => {
    await assertFails(
      setDoc(doc(CLIENTS[who](), p), { name: "y", ownerUid: "alice", deleted: false }),
    );
  });

  test.each(PATHS)("%s: update and delete an existing doc", async (p) => {
    await env.withSecurityRulesDisabled(async (ctx) => {
      await setDoc(doc(ctx.firestore(), p), { name: "seed" });
    });
    await assertFails(updateDoc(doc(CLIENTS[who](), p), { name: "z" }));
    await assertFails(deleteDoc(doc(CLIENTS[who](), p)));
  });

  test("list and add on a collection", async () => {
    const db = CLIENTS[who]();
    await assertFails(getDocs(collection(db, "households")));
    await assertFails(addDoc(collection(db, "households/h1/lists"), { name: "n" }));
  });
});
