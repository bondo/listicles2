# Branch protection for `main` (owner guide)

For the repo owner (`bondo`). Do this once after the foundation PR merges (PLAN section 5, item 6).
Agents cannot do it: it needs repo admin in GitHub Settings.

> **Verification status.** The check names, CODEOWNERS paths and workflow triggers below were read from
> `.github/workflows/ci.yml` and `.github/CODEOWNERS` on `main`. The GitHub UI labels are written from
> memory of the current Rulesets UI and were **not verified against a live Settings page**; GitHub renames
> things. If a label differs, match by meaning. Items marked **[unverified]** need your eyes.

## 1. Before you start
1. Run CI once on a PR so GitHub knows the check names (the status-check picker only lists names seen
   in the last week). Names must match `ci.yml` job `name:` exactly, lowercase, no workflow prefix.
2. Settings > General > Pull Requests: tick **Allow squash merging**, untick **Allow merge commits** and
   **Allow rebase merging**. Tick **Automatically delete head branches**. Optional: default commit message
   "Pull request title and description".

## 2. Create the ruleset
Settings > Rules > Rulesets > **New ruleset** > **New branch ruleset**. (Classic "Branch protection rules"
also works; the ruleset names below map 1:1 and rulesets can be bypassed per actor, which we want.)

| Field | Value |
|---|---|
| Ruleset name | `main` |
| Enforcement status | **Active** |
| Bypass list | Repository admin role **or** just you, mode **For pull requests only** (see section 4) |
| Target branches | Add target > **Include default branch** |

Tick these rules:

| UI label | Setting |
|---|---|
| Restrict deletions | on |
| Block force pushes | on |
| Require a pull request before merging | on |
| - Required approvals | 1 (see section 3 for the solo-owner catch) |
| - Dismiss stale pull request approvals when new commits are pushed | on |
| - Require review from Code Owners | on (uses `.github/CODEOWNERS`: process files, `firestore.rules`, goldens, build files) |
| - Require conversation resolution before merging | on |
| - Allowed merge methods | **Squash** only |
| Require status checks to pass | on |
| - Require branches to be up to date before merging | on |
| - Status checks that are required | `wrapper`, `static`, `unit`, `firebase`, `ui`, `guards`, `secrets` (add each; leave "Integration" as Any source) |

Leave off: Require signed commits, Require linear history (squash already gives it), Require deployments,
Restrict creations, Restrict updates, Require code scanning/merge queue (not used).

Also add a second tiny ruleset, or keep the default, so nothing but PRs reaches `main`. The repo hooks
block agent pushes to `main`, but the server-side rule is the real control.

## 3. Admins and the solo-owner catch
- CODEOWNERS lists only `@bondo`, and GitHub does not let a PR author approve their own PR. Agent PRs
  are opened by the agent's token/account, so you can approve them. **[unverified]** If the PR author is
  your own account (agent acting as you), "Require review from Code Owners" blocks you with no second
  reviewer. Fix: either keep yourself in the bypass list (below) and merge with "Merge without waiting
  for requirements", or run agents under a separate bot/account.
- **Are admins bound?** Recommended: **yes, bound, with you on the bypass list for pull requests only.**
  You get normal enforcement day to day, and an explicit, logged override when you need it. Do not
  tick "Do not allow bypassing" in classic rules unless you accept that nobody can override.

## 4. What NOT to require (and the stuck-run lesson)
Required checks block a merge until they report. If a check never reports, the PR hangs forever.
- Only the seven jobs above. Do **not** require the `CI` workflow name, `Dependabot`, or any check
  that only runs on some PRs.
- `ui` is the riskiest: it boots an Android emulator on a GitHub runner (45 min timeout) and can stall
  or queue when runners are busy. If it is stuck, see the escape hatch below rather than removing it.
- Do not require checks from path-filtered workflows: a skipped workflow never reports and the PR waits.
  `ci.yml` has no path filters today; keep it that way.
- `ci.yml` re-runs on `labeled`/`unlabeled` (for `golden-update` and `big-pr`) and cancels the older run
  per ref (`cancel-in-progress`). A cancelled run leaves the check not green until the new run ends.
- Required-up-to-date means every merge into `main` re-runs everything for the next open PR. Expected.

### Temporary bypass when checks hang
1. First try: PR page > Checks > **Re-run failed jobs** (or Actions > the run > **Cancel**, then
   **Re-run all jobs**). Check https://www.githubstatus.com for runner incidents.
2. If still stuck and you have verified the change locally (`scripts/verify.sh`): as bypass actor, the PR
   merge box shows **Merge without waiting for requirements to be met (bypass rules)**. Squash-merge it.
   Say so in the PR comment (which checks were skipped and why).
3. If a single check is permanently broken: Settings > Rules > Rulesets > `main` > edit > remove only that
   check from the required list, merge, then **re-add it the same day**. Never set Enforcement to Disabled.
4. Do not ask an agent to bypass: no `--no-verify`, no force-push, no push to `main`.

## 5. After saving: verify it works
1. Open a throwaway PR changing `README.md`; confirm all seven checks appear as "Required" and merge is
   blocked until they pass; the squash option is the only one shown.
2. Open a throwaway PR touching `.github/` or `scripts/`; confirm it asks for your Code Owner review.
3. In a clone, try `git push origin HEAD:main` and `git push --force origin <any>:main`; both must be
   rejected server-side.
4. Delete the throwaway branches/PRs.

## 6. Keep in sync
When a CI job is added, renamed or removed in `ci.yml`, update the required list here and in the ruleset
in the same sitting. A renamed job silently becomes "expected, never reported" and blocks every PR.
