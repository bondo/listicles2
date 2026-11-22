import {
    assertFails,
    initializeTestEnvironment,
    type RulesTestEnvironment,
} from "@firebase/rules-unit-testing";
import {
    attempt,
    CLIENT_NAMES,
    connect,
    type Client,
    type Db,
    PLAN,
    PLANNED,
    pathProblems,
    planTemplates,
    PROBES,
    PROJECT,
    RULES,
    UNPLANNED,
} from "./harness";

let env: RulesTestEnvironment;
let dbs: Record<Client, Db>;

beforeAll(async () => {
    env = await initializeTestEnvironment({ projectId: PROJECT, firestore: { rules: RULES } });
    dbs = connect(env);
});

afterAll(async () => {
    await env.cleanup();
});

beforeEach(async () => {
    await env.clearFirestore();
});

test("PLANNED holds one document of every collection in PLAN section 3, UNPLANNED none", () => {
    expect(pathProblems(planTemplates(PLAN), PLANNED, UNPLANNED)).toEqual([]);
});

// Until the real rules land, every client is denied every operation on every path.
describe.each(CLIENT_NAMES)("default deny (%s)", (client) => {
    test.each(PROBES.filter((p) => p.client === client))("$op $path", async (probe) => {
        await env.withSecurityRulesDisabled(async (admin) => {
            await assertFails(attempt(admin.firestore(), dbs[client], probe));
        });
    });
});
