# Dependency security alerts: triage policy

Canonical for how Dependabot security alerts (the repository's Security tab, "Dependabot alerts") are handled.
Origin: owner decision on issue 187 (also logged on issue 15). Version-update PRs are a separate routine
(`docs/ORCHESTRATION.md`, "Dependabot weekly routine").

## 1. Policy

1. **Critical and high alerts are triaged within one week** of being opened. Triage means each alert is either
   bumped (a PR) or has a proposed dismissal with a recorded reason (section 4). Medium and low alerts are triaged
   at the next milestone review.
2. **All open alerts are reviewed at every milestone** (before its burn-down task closes the milestone). The review
   lists every open alert and its state; nothing stays open without a reason.
3. **Only the owner dismisses an alert**, and the reason is recorded (section 4). Agents never dismiss an alert, not
   even one that is clearly a false positive: they propose, the owner decides.
4. **An alert in a dependency that ships in the app** (anything in the APK runtime classpath) is at least a `major`
   follow-up (`docs/FOLLOW-UPS.md`) and is bumped, not dismissed, unless no fixed version exists.
5. **Bump first.** Prefer the smallest bump that reaches the fixed version. A dismissal is for an alert that cannot or
   should not be bumped (no fixed version, the vulnerable code is not used, bumping breaks the build).

## 2. How to bump

* **npm** (`firebase/`): update `package.json` (`overrides` for a transitive package) and `package-lock.json`, then run
  `cd firebase && npm ci && npm run typecheck && npm run lint && npm test`.
* **Gradle** (build classpath and project configurations): add `group:artifact=fixed version` to
  `gradle/patched-dependencies.properties` (`build.gradle.kts` raises every older request to it), then run the checks with
  `--write-verification-metadata sha256` to add the new checksums to `gradle/verification-metadata.xml`, and remove the
  superseded entries (the PR review checks that only the bumped coordinates changed).
* `scripts/dependency_floors.py` (run by `scripts/verify.sh` and the CI `tasks` job) fails if a version that a triaged alert flagged comes
  back in `firebase/package-lock.json` or `gradle/verification-metadata.xml`. A new bump adds its row there, with every
  vulnerable range of the advisory (one per release line), not only the one the alert shows.

## 3. Alert list and reachability

List the open alerts with `gh api "repos/bondo/listicles2/dependabot/alerts?state=open&per_page=100"`. For each alert
record: package, ecosystem, manifest, severity, advisory, fixed version, and whether the vulnerable code is reachable
(shipped in the app, build-only, test-only, dev-only).

## 4. Proposed dismissals

A proposal goes in the PR description (or the milestone review) as one row per alert: alert number, package, severity,
reason, and a one-line note. The owner dismisses in the Security tab with the matching GitHub reason:

| Reason | Use when |
|---|---|
| Fix has already been started | A PR for the bump is open and waiting to merge. |
| No bandwidth to fix this | Not used for critical or high alerts. |
| Risk is tolerable to this project | Dev-only or build-only, and the note names why the code path is not exercised. |
| Vulnerable code is not actually used | The affected API is not called in our use; the note names the API. |
| Alert is inaccurate | The graph reports a version that is not the one that resolves. |

The dismissal comment copies the one-line note, so the Security tab keeps the reason.
