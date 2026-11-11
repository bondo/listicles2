# Follow-ups: deferring minor review findings

Purpose: let a PR be accepted while only minor issues remain, without losing them. A finding that is
real but not worth blocking the merge becomes a **follow-up**: a GitHub issue that a milestone
burn-down task must clear before the milestone closes.

Canonical for this process. `docs/ORCHESTRATION.md` links here; `REVIEW.md` and the role prompts are
aligned to it by task M0-10 (section 8). Until then this file wins where they disagree.

## 1. Design, and what changed from the first proposal

A follow-up is an issue labelled `follow-up` (section 7), filed from a fixed body template, tied to
a milestone by a `target:<Mx>` label. The burn-down is a task `Mx-FU` in `docs/tasks.toml`.

Adjustments made while evaluating the first proposal:

| Problem found | Adjustment |
|---|---|
| A hand-written burn-down task goes stale: a planner adds a task and forgets to add it to the burn-down's `depends_on`, so the burn-down could run before the milestone's work is finished. | `scripts/tasks.py validate` enforces it: every milestone with non-owner tasks has exactly one `Mx-FU`, assigned to `implementer`, depending on **every** other non-owner task of that milestone. Later milestones depend on `milestone:Mx`, which includes `Mx-FU`, so the ready query cannot start them early. |
| "Security-rules / sync-merge / release findings are never deferred" needs a machine-readable tag, or it depends on the orchestrator's memory. | Reviewers tag each finding with `area` (section 5). The follow-up issue carries `area:*` and, for anything protected, a mandatory `owner-ok` label. `tasks.py drift` flags violations (blocker; major or protected area without `owner-ok`; missing severity/target). |
| A burn-down inside the last PR of a milestone is the PR being merged, so deferring into it defers nothing. | A finding is deferred to the earliest milestone that still has a **later feature PR** (section 3). Findings from PR #1 (M0's last PR) target `M1`. |
| Deferral with no limit becomes a dumping ground. | Prefer fixing when the fix is small (section 2). More than 8 open follow-ups for one milestone: the orchestrator stops deferring and reports to the owner. |
| The reviewer's verdict (`ready_nits_only`) was computed before the deferral decision. | `deferred` is a finding status set by the decider (not the reviewer). The verdict counts only unresolved, non-deferred findings, and the next round re-checks every deferral (section 4). |

## 2. Eligibility (the rules)

Open means status `open` (not `fixed`, `withdrawn`, `disputed` with the reviewer withdrawing, or `deferred`).

| Finding | Deferral |
|---|---|
| `nit` | Allowed once no `blocker` or `major` finding is open on the PR. Usually just left as a nit (optional); defer only if the owner wants it tracked. |
| `minor` | Allowed once no `blocker` or `major` finding is open on the PR, and the conditions below hold. |
| `major` | Only with explicit owner OK (a comment from the owner on the PR or state issue, linked from the issue, plus the `owner-ok` label). |
| `blocker` | Never. |
| Any severity, `area` is `security-rules`, `sync-merge` or `release`, **or** the PR's task is `risk = "high"` | Never without owner OK (`owner-ok` label). |

A minor may be deferred only if all of these hold:
* The PR's own acceptance criteria and its tests do not depend on the fix (a test that cannot catch the bug
  it claims to catch is a `major`, not a deferrable minor).
* The fix is not small: more than about 15 changed lines, or it touches files outside the PR's scope.
  Small fixes are made now; follow-ups are for work that costs more than it is worth in this PR.
* The finding is not a regression introduced by this PR in code that already worked.

Deferral never changes severity. A deferred finding keeps its ID and severity.

## 3. Target milestone

`target:<Mx>` names the milestone whose burn-down must clear the issue. Pick the earliest milestone that
still has a **feature PR** (not its own `Mx-FU` burn-down PR) to come after the one being reviewed, and prefer the one
whose code the fix touches. Examples: a finding from M1 PR 2 of 3 targets `M1`; one from the last M1 feature PR
targets `M2` (the `M1-FU` PR is too late and too small to take new work); one from PR #1 (M0's last PR) targets `M1`;
one from the process PR #16 (before PR #1) targets `M0`. `M0.5` is design-only, so code follow-ups never target it.

## 4. Who decides, and how a round ends

* **Reviewers recommend, never decide.** Each finding carries `recommend: fix-now | defer` (section 5).
* **The orchestrator decides** by applying section 2 mechanically to the recommendation, the finding's
  severity and `area`, and the open-finding list. It records the decision (section 6) and files the issue.
  If no orchestrator session is active (a manually run loop), the implementer decides by the same rules.
  Reviewers and implementers never decide for their own findings or work alone when the rules need owner OK:
  they put the question in `needs_owner` of their `WORKER-RESULT`.
* `recommend: defer` is advice. The decider may still say fix-now. A fix-now recommendation on a
  `major` can only be turned into a deferral with owner OK, and on a `blocker` never.

Round flow with deferral:
1. Reviewer posts the round with recommendations.
2. Decider fixes, defers, or disputes each finding (disputes as in `REVIEW.md`).
3. If every finding above `nit` was deferred and no commit followed the reviewed range, the PR is accepted
   **without another review round**: nothing unreviewed exists. The orchestrator sets the round's verdict to
   `ready_deferred` (round row, PR table) and posts `accepted: all findings above nit deferred (#a, #b)`; that is the
   owner's signal to merge. An implementer deciding without an orchestrator posts the same `accepted:` comment on the PR
   and updates the round row and PR table itself. If this happens in round 4, `ready_deferred` takes precedence over `cap_reached`. If any fix was committed, `reviewed_through`
   rules apply (`ORCHESTRATION.md` §7.2) and the next round runs as usual. Deferrals are re-checked by the
   owner at merge time (PR review table, `Deferred` column) and by the next round if one happens.
4. The **4-round cap** and the **"only nits remain"** test count only unresolved, non-deferred findings.
   Deferred findings are listed in the report to the owner but do not hold a round open.
5. A deferral that violates section 2, or lacks the issue or decision record, is a finding itself
   (`major`, tagged `area: process`) in the next round, and the finding returns to `open`.

## 5. Reviewer report format change

Each finding in the `REVIEW.md` JSON block gains three fields (existing fields are unchanged):

```json
{
  "id": "R9-03",
  "severity": "minor",
  "file": "scripts/tasks.py",
  "line": 120,
  "title": "…",
  "detail": "Failing scenario: …",
  "status": "open",
  "area": "general",
  "recommend": "defer",
  "recommend_reason": "Cosmetic edge case, not covered by the acceptance criteria; fix is ~40 lines in another module."
}
```

* `area`: `security-rules | sync-merge | release | process | general`. Use the first three whenever the
  finding concerns Firestore rules and their tests, offline/last-write-wins merge, or the release workflow.
* `recommend`: `fix-now | defer`. Blockers and majors are always `fix-now`. `recommend_reason` is one line, required
  for `defer`.
* `status` gains `deferred`. Only the decider sets it, and only together with the issue link in the PR.
* The reviewer's `verdict` keeps its two values (`ready_deferred` and `cap_reached` are set by the decider, section 4). `ready_nits_only` means: nothing above `nit` is **open**, where `deferred`
  findings are not open. A reviewer who sees a deferred finding re-checks only that the record is complete
  and section 2 is respected; if it is, the finding is not counted against the verdict.
* The round row (`ORCHESTRATION.md` §6.2) gets a `deferred` column.

The reviewer's rule of thumb for `defer`: the defect is real, has a clear scope of its own, is not
needed for this PR's behaviour to be correct, and the fix would add noticeable size or risk to this PR.
When in doubt: `fix-now`.

## 6. Where the decision is recorded

1. **Findings comment** stays the reviewer's source (never edited by others). The decider's decision goes in a
   `decision` log comment on the state issue (`defer R9-03 → #52, owner-ok: no`); an implementer deciding
   without an active orchestrator posts it as a PR comment instead (the only case where a non-orchestrator
   writes this record).
2. **PR review table** (a view: refreshed at batch close, and no later than when the PR is declared ready): one row per round, columns
   `Round | Blocker | Major | Minor | Nit | Deferred | Verdict`, plus a **Deferred** list under it:
   `R9-03 minor → #52 (target M1)`.
3. **The follow-up issue** names the finding ID, PR, round and reason (section 7), and the finding's
   status in the PR becomes `deferred` with that issue number.
4. **State issue**: the `Follow-ups` line shows open counts by severity (from `tasks.py followups`).

## 7. The issue

Issue title: `[follow-up] <finding title>`. Labels (the owner creates them once, task M0-O8; the orchestrator
checks they exist before the first filing. If they don't exist yet it files with the labels in the same call, and
it checks that the returned issue carries every label (the API can drop labels silently without push access); if not, it stops
deferring and asks the owner to do M0-O8):

| Label | Meaning |
|---|---|
| `follow-up` | Marks the issue. Always present |
| `severity:nit`, `severity:minor`, `severity:major` | The finding's severity (`severity:blocker` exists only so a mistake is visible in drift) |
| `target:M1` … | Milestone whose burn-down clears it |
| `area:security-rules`, `area:sync-merge`, `area:release` | Only when the finding has that area |
| `owner-ok` | Owner approved the deferral (required for majors and protected areas) |

Body template (copy exactly; `.github/` is a protected path, so the template lives here until M0-10 adds
it as `.github/ISSUE_TEMPLATE/follow-up.md`, section 8):

```markdown
**Finding:** R9-03 (<severity>, area: <general|security-rules|sync-merge|release|process>)
**Where:** `path/File.kt:42`
**Source:** PR #<n>, review round <R>, batch <id>
**Problem:** <the reviewer's title and failing scenario, copied from the findings comment>
**Why deferred:** <which part of docs/FOLLOW-UPS.md section 2 applies; the reviewer's recommend_reason>
**Suggested fix:** <one paragraph; files and the shape of the change>
**Burn down in:** <Mx> (the milestone's `Mx-FU` task must close this or re-defer it with owner OK)
**Owner OK:** <link to the owner comment, or "not required">
**Decided by:** <orchestrator or implementer session id>
```

Closing: fixing PR says `Closes #<n>`. Re-deferral to a later milestone changes the `target:` label and
adds an `owner-ok` comment link; a follow-up older than one milestone is reported to the owner.

## 8. Burn-down, queries, state, and files for M0-10

**Burn-down task `Mx-FU`** (in `docs/tasks.toml`, enforced by `tasks.py validate`): an implementer task that
runs after all of the milestone's work. Done means every issue labelled `target:Mx` is closed or has been
re-targeted with owner OK. It is a normal PR (one concern, small), which may be empty when no follow-up exists:
then it only sets `status = "done"`. The milestone's merge/close task depends on it.

**Ready query** (`ORCHESTRATION.md` §4.3): add a third file and pass it as `--followups`:

```bash
gh api -X GET search/issues -f q='repo:bondo/listicles2 is:issue is:open label:follow-up' -f per_page=100 \
  --jq '{items: [.items[] | {number, title, state, labels: [.labels[].name]}]}' > "$T/followups.json"
python3 -I "$T/tasks.py" … --followups "$T/followups.json" ready
```

`ready` then prints `open follow-ups: N (blocker 0, major 0, minor 2, nit 1)` and annotates the ready `Mx-FU` line
with its milestone's own count. `tasks.py followups` lists them by severity; `drift` adds label violations and
"burn-down already done or dropped but issues still target it", and more than one `severity:`/`target:` label on an issue. `--json` output of `ready` is unchanged.

**State issue**: one line `Follow-ups: <summary from tasks.py followups>` (template updated in `orchestrator-state.md`).

**Protected files for task M0-10** (a `LISTICLES_TASK=tooling` session; this PR does not touch them):

| File | Change |
|---|---|
| `REVIEW.md` | Findings format: add `area`, `recommend`, `recommend_reason` and the `deferred` status (section 5). Severity table: minor/nit "Fix, or defer per `docs/FOLLOW-UPS.md`". Loop and cap: the cap and the "only nits remain" test count unresolved non-deferred findings; the reviewer recommends and never decides; the `ready_deferred` acceptance path (section 4 step 3) as a second signal to merge |
| `agents/prompts/reviewer.md` | Tag every finding with `area` and `recommend`; re-check deferral records; never decide |
| `agents/prompts/orchestrator.md`, `agents/prompts/implementer.md` | Orchestrator applies section 2 and files the issue; implementer proposes in `WORKER-RESULT` and fixes everything not deferred; neither defers majors or protected areas alone |
| `.github/ISSUE_TEMPLATE/follow-up.md` (new) | Section 7 body, with front matter `labels: follow-up` |
| `.github/pull_request_template.md` | Review table gets the `Deferred` column and a "Deferred follow-ups" list |
| `.github/workflows/*` (CI) | Run `scripts/tasks.py validate` and `scripts/test_tasks.py` (already in M0-10); burn-down checks run inside `validate` |
| `.github/CODEOWNERS` | `docs/FOLLOW-UPS.md` is a process doc: owner reviews it |
| `scripts/guards.sh` / `scripts/hooks/pretooluse_guard.py` | Nothing required. Note: the PreToolUse guard also blocks read-only commands that merely **mention** a protected path (`ls .github`, `wc -l REVIEW.md`); consider matching only writing commands |

## 9. Failure modes

| Failure | Mitigation |
|---|---|
| Deferral used to dodge a fix | Section 2 size and acceptance-criteria tests; reviewers re-check deferrals; more than 8 open per milestone goes to the owner |
| A follow-up is forgotten | `Mx-FU` is a dependency of everything later; `drift` flags open issues targeting a done or dropped burn-down |
| Protected area slips through | Reviewer `area` tag, `owner-ok` label, `drift` check, PR task `risk = "high"` check by the orchestrator |
| Labels missing, so issues are unqueryable | Owner task M0-O8; `drift` reports follow-ups lacking `severity:`/`target:` (only works for issues that carry the `follow-up` label, so the orchestrator creates them with all labels in one call) |
| Search API lag hides a just-filed issue | Re-run the query; the orchestrator also holds the number in its decision comment |
