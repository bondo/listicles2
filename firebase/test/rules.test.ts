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
test("the suite probes every collection of PLAN section 3; the UNPLANNED ones are none of them", () => {
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
    expect(h.UNPLANNED).toEqual([
        "anything/{doc}",
        "users/{uid}/unplanned/{doc}",
        "households/{hid}/unplanned/{doc}",
        "households/{hid}/members/{uid}/unplanned/{doc}",
        "households/{hid}/removed/{uid}/unplanned/{doc}",
        "invites/{code}/unplanned/{doc}",
        "lists/{lid}/unplanned/{doc}",
        "lists/{lid}/items/{iid}/unplanned/{doc}",
        "config/app/unplanned/{doc}",
    ]);
    const planned = h.TEMPLATES.map(h.collectionIdOf);
    expect(h.UNPLANNED.filter((u) => planned.includes(h.collectionIdOf(u)))).toEqual([]);
});

// Until the real rules land, every client is denied every operation on every path. The suite runs
// exactly h.PROBES, the probes of the mutant check, so each mutant that check kills turns it red.
test.each(h.PROBES)("default deny: $client $op $path", async (probe) => {
    await env.withSecurityRulesDisabled(async (admin) => {
        await assertFails(h.attempt(admin.firestore(), dbs[probe.client], probe));
    });
});
