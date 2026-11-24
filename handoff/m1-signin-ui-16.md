# Handoff: M1-16 / PR 397 (branch m1/signin-ui-16)

Delete this file in the PR's final commit (squash merge keeps it off `main`).

## Goal
M1-16 sign-in UI (AUTH-01, AUTH-02), docs/milestones/M1.md section "M1-16 / M1-17 Sign-in UI". Split by layer after round 2 (R2-01, 746 > 600 lines): PR 397 is part 1; part 2 is M1-99.

## Done
- Part 1 on PR 397: SignInViewModel, its tests, MainActivity/TallyApp wiring, a plain sign-in screen (no mark or icons), en/da strings, the Hilt test in SignedOutStartTest.

## Next (in order)
1. Merge PR 397 (review of part 1, no goldens in it).
2. M1-99 from main (not stacked): start from the local branch `m1/signin-ui-part2` (the full screen at c78ab97: mark, icons, grouped buttons, SignInScreenInsetsTest, SignInScreenScreenshotTest, 5 goldens), rebased onto main by a merge or re-created by cherry-pick.
3. In M1-99, fix R2-02 (icon beside the first line of a wrapped label at 200 % font) and R2-03 (a real gap between the buttons at 200 %), each test first, record the goldens again, golden-update label.

## Decisions made
- Split by layer, no big-pr label (orchestrator #46). Nits R1-05, R1-06, R2-04, R2-05 accepted as nits.

## Open findings
- R2-02, R2-03 (minor): part 2. R2-01 (major): resolved by the split.

## Commands to resume
```
git fetch origin m1/signin-ui-16 && git checkout m1/signin-ui-16
scripts/install-hooks.sh
scripts/verify.sh
```

## Facts that save time
- The pre-push guard blocks screenshot PNGs without the golden-update label; the label needs the PR first.
- The part 2 branch exists only in the M1-16 container; if lost, rebuild from commits 216684a..90a58d1 on the PR's history plus the goldens (`scripts/screenshots.sh record`).

## Waiting on the owner
- None.
