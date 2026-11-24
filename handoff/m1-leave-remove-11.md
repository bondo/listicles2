# Handoff: M1-11 Leave and Remove member rules (branch m1/leave-remove-11)

Delete this file in the PR's final commit (squash merge keeps it off `main`).

## Goal
PLAN 3.1 Leave and Remove member in `firebase/firestore.rules` (the member delete, the removed marker's
create or overwrite, the owner's marker get, list and delete in a live household), with allow and deny tests,
model rows, fuzz templates and mutants (docs/tasks.toml M1-11 notes).

## Done
- Red tests first: `65059c5` (leave.test.ts, tombstone.test.ts row, model.ts rows, fuzz.ts templates, fuzz.test.ts mutants).
- Rules and PLAN 3.1's Leave tests line: `8ab16f3`. Draft PR #401. Then fuzz template variants with the
  re-measured mutant finds, and tasks.toml (M1-11 done, pr 401): see `git log`.
- Scratch mutation pass: 20 mutants, 12 killed, the 8 survivors are the header's "no test can isolate" list.
- Verifier self-review on 78113f9: no blocker, major or minor; two nits (fuzz note, join comment) fixed after it.

## Next (in order)
1. Review rounds: fix findings, rerun `scripts/verify.sh`, push, WORKER-RESULT on the PR, send_message to the
   orchestrator (session_013srDQiFtrPbVLdnHo4u9fz).
2. Final commit: delete this file.

## Decisions made
- Leave needs the caller's member doc (`resource != null`, PLAN "a member"): a removed member's Leave batch is
  denied, it self-heals instead; keeps a no-op delete from telling that a household exists.
- Marker create checks keys (hasAll, hasOnly); the overwrite checks affectedKeys (PLAN 3.1 field validation).
- New fuzz templates sit in the ninth-weight group with the former extension points, so #372's draws stay.
  The join's former-member variant takes a second slot (12): with the group shared by five templates, seed 1
  found it only at 8298 of the 9000-case cap. Remove member got a marker-with-another-field variant (7): the
  extra tweak alone did not find that mutant within the cap.

## Open findings
- none yet

## Commands to resume
```
git fetch origin m1/leave-remove-11 && git checkout m1/leave-remove-11
scripts/install-hooks.sh
scripts/verify.sh
```

## Facts that save time
- Run one rules suite: `cd firebase && npx firebase emulators:exec --only firestore --project demo-tally "npx jest --runInBand test/leave.test.ts"`.
- A second emulator needs other ports (firestore, auth, hub, logging) in a scratch copy's firebase.json.

## Waiting on the owner
- M1-O6 (rules deploy after merge)
