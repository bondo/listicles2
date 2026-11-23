# Handoff: M1-67 auth data 2, Firebase session layer in :core:data (branch m1/auth-data-67)

Delete this file in the PR's final commit (squash merge keeps it off `main`).

## Goal
M1-67 (`docs/tasks.toml`; `docs/milestones/M1.md` section 5, M1-14 and its split note), draft PR #348.

## Done
- Failing emulator tests f8e514b (`ui` red there: 5 of 7 failed on their assertions), implementation 986eb27,
  privacy Q5 and task status ae7b54e, self-review fixes 9d6878f.

## Next (in order)
1. CI on the head; a red `ui` job goes to the `ci-triage` subagent (REST: `commits/<sha>/check-runs?check_name=ui`,
   then `actions/jobs/<id>/logs`).
2. Review rounds: fix or dispute each finding (`REVIEW.md`), refresh the PR body's review table.
3. Final commit: delete this file.

## Decisions made
- In the PR body, "Decisions for the reviewer" and "Self-review".

## Facts that save time
- No KVM here: the emulator tests run only in CI's `ui` job. The Auth emulator runs locally (`npm ci` in
  `firebase/`, then `npx firebase emulators:start --only auth`) for REST probes (`accounts:signInWithIdp`,
  `accounts:lookup` with `Bearer owner`).
- Maven Central answers 429 at times: rerun the Gradle command.
- Diff guard: about 450 lines with this file (CI fails above 600).

## Waiting on the owner
- none for this PR (M1-O5 sees the reduced privacy marker)
