import { initializeTestEnvironment } from "@firebase/rules-unit-testing";
import {
    attempt,
    collectionIdOf,
    connect,
    expected,
    matchOf,
    methodMutants,
    mutantsOf,
    mutate,
    outcome,
    PLAN,
    planTemplates,
    PROBES,
    PROJECT,
    RULES,
    UNPLANNED,
} from "./harness";

// The mutant check (see #202): the real rules plus one block that opens a collection of PLAN section 3, or the
// unplanned one, to one audience. The deny suite's own probes on that collection must then be allowed exactly
// for the clients let in, so at least one assertFails of rules.test.ts fails, and denied for everyone else.
// The method mutants use the unplanned collection, which no rule will ever open.
const MUTANTS = [
    ...mutantsOf([...planTemplates(PLAN), UNPLANNED]),
    ...methodMutants(UNPLANNED),
].map((m) => ({
    ...m,
    name: `allow ${m.methods.join(", ")} on ${matchOf(m)} to ${m.audience.name}`,
}));

test.each(MUTANTS)("$name turns the deny suite red", async (mutant) => {
    const rules = mutate(RULES, mutant);
    const env = await initializeTestEnvironment({ projectId: PROJECT, firestore: { rules } });
    try {
        await env.clearFirestore();
        const dbs = connect(env);
        const id = collectionIdOf(mutant.template);
        const probes = PROBES.filter((p) => collectionIdOf(p.path) === id);
        const want = probes.map((p) => `${p.client} ${p.op} ${p.path}: ${expected(mutant, p)}`);
        // Killed: some probe of the deny suite is allowed. A failure here lists the probes, none allowed.
        expect(want).toContainEqual(expect.stringMatching(/: allowed$/));
        const got: string[] = [];
        await env.withSecurityRulesDisabled(async (admin) => {
            for (const p of probes) {
                const result = await outcome(attempt(admin.firestore(), dbs[p.client], p));
                got.push(`${p.client} ${p.op} ${p.path}: ${result}`);
            }
        });
        expect(got).toEqual(want);
    } finally {
        await env.cleanup();
    }
});
