import { initializeTestEnvironment } from "@firebase/rules-unit-testing";
import * as h from "./harness";

// The mutant check (see #202): the real rules plus one block that opens a collection of PLAN section 3,
// or the unplanned one. The deny suite's own probes on that collection must then be allowed exactly for
// the clients and methods let in (so at least one assertFails of rules.test.ts fails), denied for the
// rest. The method mutants use the unplanned collection, which no rule will open.
const MUTANTS = [
    ...[...h.TEMPLATES, h.UNPLANNED].flatMap((t) => h.mutantsOf(t)),
    ...h.methodMutants(h.UNPLANNED),
].map((m) => ({ ...m, name: `allow ${m.methods.join(", ")} on ${h.matchOf(m)} to ${m.who}` }));

// Each mutant loads its rules and runs 18 probes; the first also opens the connections (about 1.6 s here),
// so the default 5 s per test is too close on a slow runner.
jest.setTimeout(30_000);

test.each(MUTANTS)("$name turns the deny suite red", async (mutant) => {
    const rules = h.mutate(h.RULES, mutant);
    const env = await initializeTestEnvironment({ projectId: h.PROJECT, firestore: { rules } });
    try {
        await env.clearFirestore();
        const dbs = h.connect(env);
        const id = h.collectionIdOf(mutant.template);
        const probes = h.PROBES.filter((p) => h.collectionIdOf(p.path) === id);
        const want = probes.map((p) => `${p.client} ${p.op} ${p.path}: ${h.expected(mutant, p)}`);
        // Killed: some probe of the deny suite is allowed. A failure here lists the probes, none allowed.
        expect(want).toContainEqual(expect.stringMatching(/: allowed$/));
        const got: string[] = [];
        await env.withSecurityRulesDisabled(async (admin) => {
            for (const p of probes) {
                const result = await h.outcome(h.attempt(admin.firestore(), dbs[p.client], p));
                got.push(`${p.client} ${p.op} ${p.path}: ${result}`);
            }
        });
        expect(got).toEqual(want);
    } finally {
        await env.cleanup();
    }
});
