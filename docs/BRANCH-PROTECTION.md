# Branch protection for `main` (owner guide)

For the repo owner (`bondo`). Do this once after the foundation PR merges (PLAN section 5, item 6).
Agents cannot do it: it needs repo admin in GitHub Settings.

> **Verification status.** The check names, CODEOWNERS paths and workflow triggers below were read from
> `.github/workflows/ci.yml` and `.github/CODEOWNERS` on `main`. The GitHub UI labels are written from
> memory of the current Rulesets UI and were **not verified against a live Settings page**; GitHub renames
> things. If a label differs, match by meaning. Items marked **[unverified]** need your eyes.

## 0. The decision this guide implements (owner decision, logged on issue #15)
- **Agents act on GitHub as your identity.** Every agent PR is authored by `bondo`, and GitHub does not let
  an author approve their own PR. So "1 required approval" or "Code Owners review required" could never be
  met by a normal merge.
- Therefore: **0 required approvals, Code Owners review OFF. Your merge is the review.** CODEOWNERS still
  marks owner-owned files and requests your review; it does not block.
- **Empty bypass list.** Because agents share your identity, a standing bypass for you is a standing bypass
  for every agent (the session's GitHub tools include merge). No ruleset can tell you and an agent apart
  while the identity is shared, so the only server-side gate that works is one nobody bypasses day to day.
  You add yourself to the bypass list only for an emergency merge, then remove yourself (section 4).
- Required: a pull request, the CI checks, squash merge only, no force-push, no deletion, branch up to date.
- Possible later improvement: a separate machine account for agent PRs. Then agent PRs have a different
  author, so you could require 1 approval plus Code Owners review, and keep a standing bypass for your
  own account only. Not needed now.

## 1. Before you start
1. Run CI once on a PR so GitHub knows the check names (the status-check picker only lists names seen
   in the last week). Names must match `ci.yml` job `name:` exactly, lowercase, no workflow prefix.
   The `tasks` check (added by PR #35) is only selectable after #35 has merged and the job has run once.
2. Settings > General > Pull Requests: tick **Allow squash merging**, untick **Allow merge commits** and
   **Allow rebase merging**. Tick **Automatically delete head branches**. Optional: default commit message
   "Pull request title and description".

## 2. Create the ruleset
Settings > Rules > Rulesets > **New ruleset** > **New branch ruleset**. Use rulesets, not classic "Branch
protection rules": the classic page has inverted labels ("Allow force pushes", "Allow deletions"), no
per-rule merge-method setting and a different bypass model, so these steps do not carry over.

| Field | Value |
|---|---|
| Ruleset name | `main` |
| Enforcement status | **Active** |
| Bypass list | **Empty** (see sections 0 and 4) |
| Target branches | Add target > **Include default branch** |

Tick these rules:

| UI label | Setting |
|---|---|
| Restrict deletions | on |
| Block force pushes | on |
| Require a pull request before merging | on (this also blocks direct pushes to `main`; section 5 step 3 proves it) |
| - Required approvals | **0** |
| - Dismiss stale pull request approvals when new commits are pushed | on (harmless with 0 approvals) |
| - Require review from Code Owners | **off** (agents share your identity; see section 0) |
| - Require conversation resolution before merging | on |
| - Allowed merge methods | **Squash** only |
| Require status checks to pass | on |
| - Require branches to be up to date before merging | on |
| - Status checks that are required | the 8 checks below, each with its source set to **GitHub Actions** |

Required checks (8): `wrapper`, `static`, `unit`, `firebase`, `ui`, `guards`, `secrets`, `tasks`.
`tasks` can only be added after PR #35 merges and has run once; until then require the other seven, and add
`tasks` the same day #35 lands.

For each check, set the source (the "Integration" / app dropdown, **[unverified]** label) to **GitHub
Actions**, not "Any source". With "Any source", anything holding a write token (agents included) can post a
passing commit status with a required name through the statuses API and satisfy the rule without CI running.

Leave off: Require signed commits, Require linear history (squash already gives it), Require deployments,
Restrict creations, Restrict updates, Require code scanning/merge queue (not used).

There is no second ruleset to create. The pull-request rule above is what stops direct pushes to `main`.
The repo hooks also block agent pushes to `main`, but the server-side rule is the real control.

## 3. Admins and bypass
- **Are admins bound?** Yes. The bypass list is empty, so failing or missing checks block you and agents alike.
- Bypass exists only as an emergency path (section 4): add yourself, merge once, remove yourself the same
  day. If the ruleset does not offer individual users on a personal repo **[unverified]**, add the
  **Repository admin** role (the only admin is you), mode **For pull requests only**.
- Do not ask an agent to bypass. No `--no-verify`, no force-push, no push to `main`.

## 4. What NOT to require (and the stuck-run lesson)
Required checks block a merge until they report. If a check never reports, the PR hangs forever.
- Only the eight jobs above. Do **not** require the `CI` workflow name, `Dependabot`, or any check
  that only runs on some PRs.
- `ui` is the riskiest: it boots an Android emulator on a GitHub runner (45 min timeout) and can stall
  or queue when runners are busy. If it is stuck, see the escape hatch below rather than removing it.
- Do not require checks from path-filtered workflows: a skipped workflow never reports and the PR waits.
  `ci.yml` has no path filters today; keep it that way.
- `ci.yml` re-runs on `labeled`/`unlabeled` (for `golden-update` and `big-pr`) and cancels the older run
  per ref (`cancel-in-progress`). A cancelled run leaves the check not green until the new run ends.
- Required-up-to-date means every merge into `main` re-runs everything for the next open PR. Expected.

### Escape hatch when checks hang
Try these in order; stop at the first that works.
1. A failed (not stuck) job: PR page > Checks > **Re-run failed jobs**. Check https://www.githubstatus.com
   for runner incidents.
2. A run stuck **queued** (cancel returns 409, and "Re-run failed jobs" is not offered while it is queued;
   seen in `docs/reviews/m0-process-tooling-review.md`): start a new run instead. Remove and re-add a label
   on the PR, or click **Update branch** (the triggers include `labeled`, `unlabeled` and `synchronize`, and
   `cancel-in-progress` replaces the old run; no commit needed).
3. Still stuck: force-cancel the run, then re-run it:
   `gh api -X POST repos/bondo/listicles2/actions/runs/<run-id>/force-cancel`
4. Still stuck and you have verified the change locally (`scripts/verify.sh`): **temporary owner bypass**.
   Settings > Rules > Rulesets > `main` > Bypass list > add yourself (or the Repository admin role),
   then in the PR's merge box use **Merge without waiting for requirements to be met (bypass rules)** and
   squash-merge. **Immediately remove yourself from the bypass list** again. Say in the PR comment which
   checks were skipped and why. Do this while no agent session is running against this repo.
5. A single check permanently broken: edit the ruleset, remove only that check from the required list,
   merge, then **re-add it the same day**. Never set Enforcement to Disabled.

## 5. After saving: verify it works
1. Open a throwaway PR changing `README.md`; confirm the required checks appear as "Required" with source
   GitHub Actions, and that merge is blocked until they pass; the squash option is the only one shown.
   With 0 approvals and Code Owners review off, green checks alone must make the PR mergeable.
2. Open a throwaway PR touching `.github/` or `scripts/`; confirm it requests your review as Code Owner
   but does **not** block the merge.
3. Prove the server-side rules from a clone. First save the current head so you can undo a wrong success:
   `git fetch origin && git rev-parse origin/main` (write the SHA down: `<saved-sha>`). Then:
   - plain push: `git commit --allow-empty -m "protection test" && git push origin HEAD:main` must be rejected;
   - force push: `git push --force origin origin/main~1:main` must be rejected;
   - deletion: `git push origin :main` must be rejected.
4. **If any of those pushes succeeded**, the ruleset is wrong. Fix the ruleset first, then restore `main`
   (owner only; temporarily satisfy the ruleset as needed): `git push --force-with-lease origin <saved-sha>:main`.
   Confirm with `git rev-parse origin/main` that it equals `<saved-sha>`.
5. Delete the throwaway branches/PRs.

## 6. Keep in sync
When a CI job is added, renamed or removed in `ci.yml`, update the required list here and in the ruleset
in the same sitting. A renamed job silently becomes "expected, never reported" and blocks every PR.
Pending change: after PR #35 merges, add `tasks` to the required list (section 2).
