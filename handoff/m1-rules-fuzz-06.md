# Handoff: M1-06 rules fuzzing (branch m1/rules-fuzz-06)

Delete this file in the PR's final commit.

## Next (in order)
1. Push the failing tests (model.ts without rows), then the rows; open the draft PR.
2. tasks.toml: M1-06 done with its pr; M1-90 (name trim gap) added and in M1-FU's depends_on.
3. Verifier self-review, PR body, WORKER-RESULT comment, send_message to the orchestrator.

## Decisions and facts
- Blank names in the model follow Firestore's trim (code points up to U+0020, probed); the app's Kotlin trim differs: M1-90.
- Mutants run on seed 1; the main fuzz on a new seed per run (replay: FUZZ_SEED, FUZZ_PATH). About 25 ms a run locally.
- The tools turn ` ` escapes into the literal character: write `\u{a0}` in sources.
