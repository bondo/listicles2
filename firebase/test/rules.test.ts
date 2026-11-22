import {
    assertFails,
    initializeTestEnvironment,
    type RulesTestEnvironment,
} from "@firebase/rules-unit-testing";
import * as h from "./harness";

let env: RulesTestEnvironment;
let dbs: Record<h.Client, h.Db>;

beforeAll(async () => {
    env = await initializeTestEnvironment({ projectId: h.PROJECT, firestore: { rules: h.RULES } });
    dbs = h.connect(env);
});

afterAll(async () => {
    await env.cleanup();
});

beforeEach(async () => {
    await env.clearFirestore();
});

// The probed paths come from PLAN section 3; a collection added to or dropped from PLAN changes this list.
test("the suite probes every collection of PLAN section 3, and UNPLANNED is none of them", () => {
    expect(h.TEMPLATES).toEqual([
        "users/{uid}",
        "households/{hid}",
        "households/{hid}/members/{uid}",
        "households/{hid}/removed/{uid}",
        "invites/{code}",
        "lists/{lid}",
        "lists/{lid}/items/{iid}",
        "config/app",
    ]);
    expect(h.TEMPLATES.map(h.collectionIdOf)).not.toContain(h.collectionIdOf(h.UNPLANNED));
});

// Until the real rules land, every client is denied every operation on every path. The suite runs
// exactly h.PROBES, the probes of the mutant check, so each mutant that check kills turns it red.
test.each(h.PROBES)("default deny: $client $op $path", async (probe) => {
    await env.withSecurityRulesDisabled(async (admin) => {
        await assertFails(h.attempt(admin.firestore(), dbs[probe.client], probe));
    });
});
