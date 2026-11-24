# Handoff: M1-66 auth wiring 1, Credential Manager wrapper (branch m1/auth-wiring-66)

Delete this file in the PR's final commit (squash merge keeps it off `main`).
Write it when the context hook reminds you (60% of a 1M window, 40% of a 200k one; hard stage 80% / 60%), commit it, and end the session. The next session starts from this file.

## Goal
M1-66 of `docs/tasks.toml` (row 10c of `docs/milestones/M1.md`), narrowed by the split in commit 140481c: the Credential
Manager wrapper (Google ID option) in `:core:data` with its licences, `:app` on `:core:data`. Draft PR, batch M1-66.

## Done
- Failing tests first (8a51097), then the wrapper and the web client id (d3d431a), then the split record (140481c).
- Split: M1-88 (Hilt bindings, MainActivity for the picker; draft patch to post on the PR), M1-89 (#357 cleanup).

## Next (in order)
1. `scripts/verify.sh` green, push, open the draft PR from the template (body through the API).
2. Post the M1-88 draft patch as a PR comment; add `pr = N` to M1-66 in `docs/tasks.toml`.
3. Verifier subagent (agents/prompts/verifier.md), fix above nit, WORKER-RESULT comment, send_message to the orchestrator.

## Decisions made
- Wrapper in `:core:data` with credentials 1.6.0 and googleid 1.2.1: without them `firebase-auth` pulls versions no licence
  line lists, and licensee runs on `:core:data` now (implementer).
- Wrapper tests in `:app`: only `:app` has the offline Robolectric setup (issue 213) (implementer).
- Web client id: `:core:data` has an empty `default_web_client_id`; the Google Services plugin's value overrides it when
  google-services.json has a web client (the stand-in has one now) (implementer).
- Split at about 620 lines (guard 600) (implementer, recorded for the orchestrator).

## Open findings
- none yet

## Commands to resume
```
git fetch origin m1/auth-wiring-66 && git checkout m1/auth-wiring-66
scripts/install-hooks.sh
scripts/verify.sh
```

## Facts that save time
- Maven Central answers 429 from this container now and then: retry the Gradle command.
- googleid 1.2.1 rejects an ID token that is not JWT-shaped (tests build one).
- `CredentialManager by CredentialManager.create(...)` lets a fake override only the two suspend calls.
- App-wide activity callbacks also see the picker's translucent HiddenActivity: observe MainActivity only (M1-88).

## Waiting on the owner
- none
