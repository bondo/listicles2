# Handoff: M1-15 part 1 (branch m1/auth-email-15)

Delete this file in the PR's final commit (squash merge keeps it off `main`).

## Goal
docs/milestones/M1.md section 5, M1-15: the email and password steps in `core/domain` with fakes; M1-99 is the Firebase part.

## Done / next
- PR #396: red tests 75255dc, steps eb50337, split ec7505d (M1-99; M1-15 done), self-review fixes cbf5db3.
- Next: review rounds (fix or dispute; stay near 450 counted lines), then delete this file.

## Facts that save time
- The pre-push hook runs the unit tests, so a red-only commit is pushed together with its green commit.
- ktlint braces every `when` branch once one is multi-line; detekt allows 11 functions per class (mappings are top-level).

## Resume
`git fetch origin m1/auth-email-15 && git checkout m1/auth-email-15 && scripts/install-hooks.sh && scripts/verify.sh`
