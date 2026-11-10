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

describe("default deny", () => {
  test("a signed-in user cannot read an arbitrary document", async () => {
    const db = env.authenticatedContext("alice").firestore();
    await assertFails(getDoc(doc(db, "households/h1")));
  });

  test("a signed-in user cannot write an arbitrary document", async () => {
    const db = env.authenticatedContext("alice").firestore();
    await assertFails(setDoc(doc(db, "households/h1"), { name: "x" }));
  });

  test("an anonymous client cannot read", async () => {
    const db = env.unauthenticatedContext().firestore();
    await assertFails(getDoc(doc(db, "users/alice")));
  });
});
