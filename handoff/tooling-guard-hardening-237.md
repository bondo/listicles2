# Handoff: guard hardening after #237 (branch tooling/guard-hardening-237, PR #252)

Delete this file in the PR's final commit (squash merge keeps it off `main`).
Written because the context hook fired (61%) when the round 4 fix round arrived. A FRESH implementer session continues from here.

## Goal
PR #252 (draft): harden `scripts/hooks/pretooluse_guard.py` after #237 (see #229, owner ruling on #15 comment 7021901747 item 1). Session runs with `LISTICLES_TASK=tooling` (process files). Orchestrator is session_013srDQhZuYQs2ZjmM8JSVFd (#22; handover verified on #15 comment 7060408900). Send the compact one-line WORKER-RESULT to it with `send_message`. GitHub: the built-in GitHub MCP is gone, use `gh api` REST only (no `gh pr`).

## Done (pushed, head 5e56935, CI 14/15, only `guards` red on diff size 807 > 600: `big-pr` is the orchestrator's call)
- Rounds 1, 2, 3 fixed test-first. Red commits: 01d7307, c69cd4f, 6e2819c, 0a48b5f, affe2fb. Green: 6053b93, f20e46b, 15204c0, b538270, a04b41f, d28b205, 5e56935.
- Mapping comments on #252: round 1 = 7058278840, round 2 = 7059536207, round 3 = 7062778271. WORKER-RESULT comments: 7032666508 (earlier), 7059538730, 7062780450.
- Tests: `scripts/hooks/test_guard_hardening.py`, `test_guard_round1.py` (class `Base` + `Round1`), `test_guard_hardening2.py`, `test_guard_hardening3.py` (all inherit `Base` from round1; they take `deny(list, both=True, d=None)` / `allow(list, d=None)`).
- DO NOT touch `scripts/hooks/test_guard_round2.py`: it is #237's file (29 tests). I once overwrote it by mistake (caught and restored); my new tests live in the `*_hardening*.py` files.

## Next (in order): the escalation decision, comment 7064667698 on #252 (read it first, it holds the reviewer's prototype and the 23 mutants)
Decision: FIX, ONE fix round, then a fresh round 5 (last). Required design: **make main's verdict a floor**: judge each command with main's (85fdd75-before-this-PR, i.e. `origin/main`'s at PR base) semantics AND with the new model, and deny if either denies. The reviewer's ~24-line throwaway prototype in the comment closes the 29 forms main denies that pass at head, plus R4-12 and R4-07, with 47 everyday commands unchanged.
Fix test-first (each red test must fail for the right reason), then:
1. R4-07, R4-08 (kill all 23 listed mutants; RE-RUN THEM before pushing and list the results in the mapping comment), R3-02, R4-09..R4-16. R4-15: the false positive `unset IFS; git status` must be ALLOWED. R4-16: `false && IFS=-; P=--force; git push $P origin work` must DENY.
2. Do NOT touch R1-09, R1-10, R2-11, R3-10 (owner decision pending).
3. Merge `origin/main` first (plain merge commit; main has moved, b26e024 at the time of writing). A push re-triggers the size check, the `big-pr` label is applied by the orchestrator.
4. `scripts/verify.sh`, push (plain, no force, no `--no-verify`), mapping comment on #252, refresh the PR body (numbers: changed lines, tests, rounds table, sweep, mutants), then the one-line WORKER-RESULT (new head, changed-line count) to the orchestrator, then a WORKER-RESULT comment on #252.

## Decisions made
- Orchestrator (escalation reviewer) ruled FIX with the floor design above; no split, no owner escalation.
- Field splitting follows bash (`split_value`, `expand_fields` in the guard; `Word.qd` = offsets of quoted `$`). IFS is tracked per statement (`track_ifs`, `sets_ifs`), NOT by scanning raw text (a raw-text check blocked my own `git commit -m "... IFS ..."`).
- Deferrals (R1-09, R1-10, R2-11, R3-10) are the orchestrator's decision (FOLLOW-UPS §4); I never filed issues.

## Open findings
- R4-07, R4-08, R3-02, R4-09..R4-16 (round 4, see the round 4 findings comment and the escalation comment 7064667698). Find the round 4 review comment on #252 (`gh api repos/bondo/listicles2/issues/252/comments --paginate`).
- R1-09, R1-10, R2-11, R3-10: open, deferred by the orchestrator/owner, do not touch.

## Commands to resume
```
git fetch origin tooling/guard-hardening-237 && git checkout tooling/guard-hardening-237   # head 5e56935 (+ this handoff commit)
scripts/install-hooks.sh
git merge origin/main        # plain merge commit first
scripts/verify.sh            # ~15 min; run it in the background and poll its output file
```

## Facts that save time
- Run tests from the repo root: `python3 -I -m unittest discover -s scripts/hooks -p 'test_guard_hardening3.py'` (about 10 s per file). The full hook suite is `python3 -I scripts/hooks/run_hook_tests.py --jobs 4` (about 4 min, 609 tests at 5e56935). `scripts/lint_python.sh scripts/hooks` runs ruff (160 columns) and mypy (class attributes need annotations, e.g. `Word.qd: frozenset[int]`).
- The pre-push hook runs the whole hook suite serially (about 7 min): push in the background (`run_in_background`) and wait on its output file. Do not use `pgrep -f "git push"` as a wait condition (it matches the waiting shell itself).
- Tests that write `.git/...` need `CLAUDE_PROJECT_DIR` set to the test repo (as in a real session); `run()` strips it by default. Process-file cases are denied only in default sessions; `.git/config` and `.git/hooks/` in both.
- Mutation testing: copy `scripts/` to a scratch dir and mutate there (the tests find the guard relative to their own file), never mutate the working tree while verify or the pre-push hook runs. My scripts were in the scratchpad (`mut6.py` etc.); rebuild from the mutant lists in the review comments.
- Differential sweep: run 85fdd75's guard (`git show 85fdd75:scripts/hooks/pretooluse_guard.py`) against head over all string constants of `test_guard*.py`; the only accepted deny->allow is `F=--force-with-lease; (F=--force); git push $F origin work`.
- Foreign-commit check before every push (§7.6 item 2(e)): `gh api "repos/bondo/listicles2/pulls/252/commits?per_page=100"`; non-Claude commits so far are the owner's (merged from main). Commit trailers: `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>` and `Claude-Session: https://claude.ai/code/<your own session id>`.
- The guard blocks `git`/`gh` commands if the CURRENT guard misreads your command line (it did once with IFS); if a command is blocked, split it, do not work around the guard.
- No closing keywords before issue numbers in commits or PR body ("see #229").

## Waiting on the owner
- The owner's decision on R1-09, R1-10, R2-11, R3-10 (details in #252 and the orchestrator state), not mine to restate.
