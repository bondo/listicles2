# Handoff: M1-46 (branch m1/build-logic-46). Delete in the PR's final commit.

Goal: M1.md row T9, `build-logic` convention plugins, no `allprojects`/`subprojects` configuration (#217 items 1-3). Split for the
600-line guard: #48 is M1-63, #217 item 4 is M1-64 (both in docs/tasks.toml).
Done: failing guard first (1d928ff), then build-logic and the modules on it; an init-script dump of every module's settings equals main.
Next: full verification-metadata regeneration if not done; draft PR; WORKER-RESULT comment; send_message to the orchestrator.
Facts: the root verification metadata covers the included build; guards.sh reads `detekt:` in a coordinate as a suppression (catalog
entry uses group/name form).
