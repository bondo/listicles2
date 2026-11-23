# Handoff: M1-85 (branch tooling/repo-name-85)

Delete this file in the PR's final commit (squash merge keeps it off `main`).
Parked on the orchestrator's request (#38 chat, 2026-11-23): the repo is renamed `bondo/listicles2` -> `bondo/tally` right away; a
fresh session on `bondo/tally` finishes this as the post-rename PR. No PR is open yet.

## Goal
M1-85 (docs/tasks.toml, added on this branch): the repo slug and the checkout path come from one place, so no script names the
repository and the scripts work under the old and the new name.

## Done
All committed and pushed; head is the commit that adds this file (its parent 1cf891b holds the code).
- 8c846e7 failing tests: new `scripts/test_repo_slug.py` (wired into `scripts/verify.sh` and `.github/workflows/ci.yml`), wrapper,
  owner-drift and merge_ready tests on fixture checkouts and slugs, fixture constants, M1-85 row (and in M1-FU depends_on).
- 5ad1d0b implementation: `scripts/repo_slug.py` (GITHUB_REPOSITORY when set and valid, else the origin remote of its checkout,
  git run without repository variables and without global/system config, else exit 1); `check_owner_drift.sh` and
  `merge_ready.py` (`main(..., repo=None)`, no `REPO` constant) use it; help text in `state_body.py`/`tasks.py` uses gh's
  `{owner}/{repo}`. `mark-ready.sh`/`update-branch.sh` parse the remote inline (their SHA-256 is pinned in
  `pretooluse_guard.py`, so they must not run an unpinned helper); the parse block is identical in both and a test compares it
  with `repo_slug.slug_from_url` on every fixture URL. Pins updated. `test_prepush_scope.py` ROOT_USES/LISTED_DIRS rows.
- Self-review (verifier subagent): major fixed test-first in 125082a (failing) / 18996bf (fix): the wrappers pin the owner
  (`owner="bondo"`; the guard does not deny `git remote set-url origin`), another owner exits 1 before gh; git's stderr shown;
  scp form user part without a colon. 0d4c1a8 mypy, 1cf891b ruff E501.
- Verify: the last full `scripts/verify.sh --fast` (on 0d4c1a8) failed only `python-lint` (5 x E501); fixed in 1cf891b and
  `scripts/lint_python.sh` exits 0 there. All other steps ok (hook-tests 578s, repo-slug, merge-ready, owner-drift, ...).
  A full verify on 1cf891b did not finish before parking: rerun it first.

## Next (in order)
1. On `bondo/tally`: `git fetch origin tooling/repo-name-85`, check it out, `scripts/install-hooks.sh`, `scripts/verify.sh --fast`.
   The scripts need no change for the rename (the slug comes from the remote; the wrappers pin only the owner `bondo`).
2. Decide with the orchestrator whether this branch also takes the literal renames below (it was out of scope before the
   rename: `.claude/`, agents/prompts/, CLAUDE.md, REVIEW.md, README, docs/, .github/), or a separate PR does.
3. Open the PR as a draft (body draft: scope, test-first commit order, self-review, size; see "Facts" below), WORKER-RESULT.

## Decisions made
- Wrappers ignore GITHUB_REPOSITORY and pin the owner, unlike the other scripts: the environment and `git remote set-url` must not
  redirect the two allow-listed calls (implementer, after the verifier's major). A guard rule denying origin URL changes would be
  the stricter alternative, as its own guard PR.
- `test_status_workflow.py` accepts the README status links of any one repository (not `repo_slug.resolve()`), so it passes
  between the rename and the README update.

## Open findings
- Self-review minor: size 651 changed lines (207 scripts/wiring, 444 tests) vs ~400. Possible split: the fixture-constant edits in
  `test_collab_inbox.py` / `test_status_workflow.py` (~55 lines). Open, for the orchestrator.

## Commands to resume
```
git fetch origin tooling/repo-name-85 && git checkout tooling/repo-name-85
scripts/install-hooks.sh
scripts/verify.sh
```

## Facts that save time
- Remaining literal `listicles2` on main that this branch leaves (old -> new is `bondo/listicles2` -> `bondo/tally`,
  `/home/user/listicles2` -> `/home/user/tally`):
  - README.md:7, 9, 13 (status image, graph, detail page), README.md:23 (CI runs link)
  - agents/prompts/orchestrator.md:1, with scripts/test_prompt_rules.py:1670 that asserts it
  - docs/BRANCH-PROTECTION.md:103, docs/SECURITY.md:35 (`repos/...`; or `repos/{owner}/{repo}/`), docs/FOLLOW-UPS.md:176,
    docs/ORCHESTRATION.md:242, 243, 244 (`repo:` queries), 267, 845, 858, 889 (spawn templates), docs/STATUS.md:111,
    docs/agent-tuning.md:6 and docs/tasks.toml:660 (#15 comment links; GitHub redirects), docs/PLAN.md:1,
    docs/product/naming.md:74, 84, 119 (naming history; owner's call)
  - scripts/hooks/test_settings_permissions.py:96, 99, 100, 102, 103, 116, 117, 132, 133, 134, 142, 204, 214 (rule mutations the
    `.claude/settings.json` checker must reject; rename with the `.claude/` follow-up)
  - test fixtures that pass under either name: scripts/test_collab_inbox.py:17, scripts/test_merge_ready.py:27,
    scripts/hooks/test_mark_ready.py:32, 34, scripts/test_owner_drift_check.py:134, 141, 149, scripts/test_repo_slug.py (23 lines)
  - `.claude/` has none; no workflow hard-codes the slug (`status.yml` uses `github.repository`); CODEOWNERS names no repo.
- The pretooluse guard flags inline code that mentions the git config path; put such Python edits in a scratch file.
- Hook tests take about 8-10 minutes; the gate self-tests run when `scripts/` changed, so a full `--fast` verify is ~30 minutes.

## Waiting on the owner
- none
