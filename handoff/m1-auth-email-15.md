# Handoff: M1-15 part 1 (branch m1/auth-email-15)

Delete this file in the PR's final commit (squash merge keeps it off `main`).

## Goal
M1-15 (docs/milestones/M1.md section 5): the email and password steps in `core/domain` with fakes; M1-95 (split off here) is the Firebase part.

## Done
- PR #396 (draft): 75255dc red tests, eb50337 `PasswordAccount`, ec7505d split (M1-95, M1-15 done), 2804fc7 trimmed,
  then the self-review (verifier) fixes: pointers name M1-95, row 11, a padded password in the property, KDoc.

## Next (in order)
1. Review rounds: fix or dispute each finding; keep the PR near 450 counted lines (this file included until deleted).
2. Final commit: delete this file.

## Decisions made
- Split as for M1-14 / M1-67 (about 700 lines with the data layer); `GoogleSignInResult.EmailHasPasswordAccount` moved to M1-95 with its mapping.

## Open findings
- none (self-review: 4 minor, 3 nit, all fixed or recorded in the PR body)

## Commands to resume
```
git fetch origin m1/auth-email-15 && git checkout m1/auth-email-15
scripts/install-hooks.sh
scripts/verify.sh
```

## Facts that save time
- The pre-push hook runs the unit tests: a red-only commit cannot be pushed; push it together with its green commit.
- ktlint `when-entry-bracing` braces every branch once one is multi-line; detekt `TooManyFunctions` is 11 per class, so the answer mappings are top-level.

## Waiting on the owner
- none
