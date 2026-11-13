# Recurring reviews: catalogue, procedures, rubric, meta-review

Source: issue #65 (Stage 1-4 FINAL, owner-approved 2026-11-13). Task: M0.5-23. Reviews are **ongoing**. Only the
meta-review rule (section 5) can re-scope or drop one, and **never R1 (correctness) or R7 (security/rules)**.

**Goals, in rank order** (the rank settles conflicts; it does not order the reviews): 1 correctness, 2 security and privacy,
3 user experience, 4 pipeline reliability, 5 cost, 6 visual design, 7 owner attention, 8 dev speed, 9 Play readiness,
10 app performance, 11 accessibility (contrast and touch targets are checked inside R5, R9 and the `ui` job).

**Usage rule:** the recurring reviews (R2, R3, R4) stay at about **$3 a week or less** and are skipped when their input has
not changed (for example nothing merged that week). Per-PR and per-milestone reviews are not weekly cost. If the cap is
exceeded, R3 reports it and R4 waits until the next week. Costs below are estimates until `review` and session rows exist.

## 1. Catalogue

`Start`: now (M0.5) / M1 / M2 / M6. Design material (R5, R10, R12) goes to the **owner and the collaborator at the same time**
(one hand-off comment, `collaborator-workflow.md` section 7). The collaborator's input is **advisory; the owner decides (D5)**.

| Id | Review | Goals | Cadence / trigger | Runner | Input | Output | Cost | Start |
|---|---|---|---|---|---|---|---|---|
| R1 | Code review | 1, 2; 3, 6 on UI PRs | per PR, per round (max 4 per batch) | fresh Opus reviewer | diff, `REVIEW.md`, Android checklist, earlier findings | findings JSON on the PR; CSV round row | $2-3 | now |
| R2 | Usage + reliability check | 4, 5 | every orchestrator wake (45 min) | orchestrator | `get_session` usage, `rate_limit_info`, failed or stalled sessions | `usage:` line in #15; pause protocol (ORCH 7.7); incident rows | ~0 | now |
| R3 | Weekly ops digest | 4, 5, 7, 8; 1 | Mondays, first wake after 10:00 UTC; skipped if nothing merged | orchestrator, inside that wake | `docs/agent-metrics.csv`, `owner-todo` ages, `escaped` and `follow-up` counts | one #15 comment (section 3.1) | $0.3-1 | now |
| R4 | Dependency triage | 2, 8 | weekly, only if Dependabot PRs are open | Sonnet worker | open Dependabot PRs | one grouped draft PR; licence and verification flags | $0-2 | now |
| R5 | Design review | 3, 6; 11 | per design PR; max 2 Opus rounds (D-3.2) | Opus design reviewer, then the owner and the collaborator together | review sheet, `design/tokens.json`, wireframes light/dark, rubric | findings on the PR; rubric scores per screen | $2-3 per round | now |
| R6 | Milestone retro + meta-review | 4, 5, 8; the reviews | end of each milestone | Sonnet medium worker | the CSV, `docs/agent-tuning.md` | at most 3 changes as reviewed PRs; expected effect logged | $1-3 | end of M0.5 |
| R7 | Security / rules review | 2 | per PR labelled `area:security-rules`, `area:sync-merge` or `risk:high` | fresh Opus reviewer, max effort | diff, data model, rules allow/deny matrix (D-2.6) | findings JSON; matrix gaps; CSV round row | $3-5 | M1 |
| R8 | Milestone quality review | 1, 2; 10 from M2 | end of each milestone | Opus worker | story to test trace, Kover/PIT trend, `escaped` issues, ADRs vs checklist, read counter (M2) | one comment on the milestone issue + follow-up issues | $2-4 | M1 |
| R9 | Screen + visual check | 3, 6, 11 | per UI PR, inside R1 | the R1 reviewer | screenshot goldens per state (light/dark, en/da), `golden-update` diffs, rubric | R1 findings + rubric scores for changed screens | ~+$0.5 | M1 |
| R10 | Device notes | 3, 6 | once per milestone | owner and/or collaborator (visible to both at once) | the app on a device, rubric | 3-5 `feedback` issues + rubric scores; **the owner's scores decide** | owner time | M2 |
| R11 | Pre-release review | 9, 10, 2 | before each release (first: the M6 tag) | Opus worker + owner go/no-go | Play checks, data inventory, timing logs, manifest | release checklist comment; owner fills Data safety | $4-6 | M6 |
| R12 | Screens vs wireframes | 3, 6 | end of each UI milestone (M1, M2, M4, M5) | Opus worker; result to owner and collaborator together | wireframes (M0.5-03), goldens per state, rubric, design ADRs | one comment on the milestone issue (section 3.4) | $2-3 | M1 |

Weekly total: R2 ~0 + R3 up to $1 + R4 $0-2, about **$3 or less**. Per milestone about **$8-16** (R5 up to 2 rounds, R6, R8, R12).
Not reviews on purpose: CI flake and lead-time numbers (D-2.7, a rollout script), a separate docs-drift review (R1 and the
wake checks catch it; revisit at R6).

## 2. How each review is run

Protected files (`agents/`, `REVIEW.md`, `.github/`, `CLAUDE.md`) change only in the **tooling** environment.

| Review | Runs as | Instructions live in | Status |
|---|---|---|---|
| R1 | worker session, fresh Opus | `agents/prompts/reviewer.md`, `REVIEW.md`, `docs/ANDROID-BEST-PRACTICES.md` | exists |
| R2 | inside every orchestrator wake | ORCHESTRATION 7.7 (pause protocol, usage line); prompt text: M0.5-25 | protocol exists |
| R3 | inside one orchestrator wake (D-3.1), no separate session | section 3.1; prompt step: M0.5-25 | by hand until then (D-4.4) |
| R4 | Sonnet worker, only if Dependabot PRs are open | ORCHESTRATION 7.5 | exists |
| R5 | Opus design reviewer (max 2 rounds), then **one** hand-off comment on the PR to the owner and the collaborator (same review sheet and screenshots) plus one line in #15; `owner-todo` only if sign-off is still pending after 7 days (D-4.5) | design-reviewer role (M0.5-15), `docs/product/rubric.md` drafted in M0.5-03 | to write |
| R6 | Sonnet medium worker | PLAN 9.4 + section 5 | exists, extended here |
| R7 | Opus worker, max effort | reviewer prompt + a `REVIEW.md` allow/deny-matrix item (M0.5-26) | M1 |
| R8 | Opus worker, one-off prompt (ORCHESTRATION 8.4) | section 3.2 | M1 |
| R9 | inside R1, no extra session | `REVIEW.md` item (M0.5-26): goldens per state + rubric scores | M1 |
| R10 | owner and/or collaborator | one issue per milestone, assigned to the owner, mentioning the collaborator, rubric as the template; the orchestrator opens it as an `owner-todo` (M0.5-25) | M2 |
| R11 | Opus worker + owner go/no-go | section 3.3 | M6 |
| R12 | Opus worker, one-off prompt; result to both at once | section 3.4 | M1 |

## 3. Procedures

### 3.1 R3 weekly ops digest (orchestrator, in the wake)
1. **When:** the first wake on a Monday after 10:00 UTC. Skip it (one line in #15) if nothing merged in the last 7 days.
   **The first two digests are written by hand** from the CSV (D-4.4); a script may replace that later.
2. **Read** `docs/agent-metrics.csv` (rows of the last 7 days), open `owner-todo` issues with their age, and the counts of
   `escaped` and `follow-up` issues opened in the week. No new data source, no transcripts.
3. **Post one comment on #15**, headed `Weekly ops digest <date>`, with at most 25 lines: cost per role and per PR (sum the
   session rows; never add the `review` rows' `cost_usd`, which repeat a session row); rounds per PR; incidents by kind;
   owner load (D-2.5: sum of `owner_interventions` and the age of each open `owner-todo`); escaped count; running
   counts per review from the ledger (section 4); the week's cost against the $3 cap; at most **3 proposals**.
4. R3 only shows numbers and proposes. It decides nothing, changes no file, and spawns no worker.
5. **Cost of this review:** it runs inside the wake, so there is no session row of its own. Write one `review` row for it
   (run_ref = ISO week, for example `2026-W47`).

### 3.2 R8 milestone quality review (Opus worker, end of each milestone)
Checklist, one comment on the milestone issue, follow-up issues for gaps (label `follow-up`):
1. Every story of the milestone traces to at least one test (story id in the test name or the task notes); list the gaps.
2. Kover and PIT trend against the previous milestone; a drop is a finding.
3. Every `escaped` issue of the milestone has a link to the causing PR and a test that now fails without the fix.
4. ADRs vs `docs/ANDROID-BEST-PRACTICES.md`: decisions that deviate from the checklist are recorded, not silent.
5. From M2: the debug Firestore read counter (D-2.4) against the budget in the plan.
6. Findings are ranked by the goals order; at most 10 follow-up issues, the rest named in the comment.

### 3.3 R11 pre-release review (Opus worker + owner go/no-go, before each release)
1. Play checks: `targetSdk`, a release (R8-minified) smoke build installs and starts, version code, manifest permissions
   against the privacy page.
2. Data inventory (D-2.8): the worker writes it from the code and Firestore rules; **the owner fills in the Data safety form**.
3. Timing logs and Macrobenchmark results (D-2.4) against the budgets; regressions are findings.
4. One release-checklist comment with pass / fail per item; the owner decides go or no-go.

### 3.4 R12 screens vs wireframes (Opus worker, end of M1, M2, M4, M5)
Input: wireframes from M0.5-03, the current goldens per state (light/dark, en/da), the rubric, design ADRs. One comment on the
milestone issue, mentioning the owner and the collaborator at the same time: per screen **matches / deviates (intended, with
ADR) / deviates (unintended)**, rubric scores with a one-line reason each, and at most 5 fixes as follow-up issues.
Agent scores are advisory (section 4.2); the owner decides.

### 3.5 R10 device notes (owner and/or collaborator, once per milestone from M2)
One issue per milestone, assigned to the owner and mentioning the collaborator, with the rubric as its template. Notes become
3-5 `feedback` issues (D-2.2). Notes from either person are visible to both at once. **The owner's scores decide.**

## 4. Visual-quality rubric

Draft owned by `docs/product/rubric.md` (written in M0.5-03, agreed by the owner at D5; the owner and the collaborator see the
draft together; later changes go through R6). Used by R5, R9, R10 and R12. Score each criterion **1-5 with a one-line reason**,
per screen or per flow.

| Criterion | A 5 looks like |
|---|---|
| Hierarchy | the main action and content stand out at a glance |
| Spacing and alignment | token spacing only, a clear grid, nothing cramped or floating |
| Colour | palette from tokens, used with purpose, works in light and dark |
| Density | fits a real household list (30+ items) without clutter or wasted space |
| Typography | type scale from tokens, readable, en and da both fit without truncation |
| Consistency | same patterns for the same things across screens |
| Polish and delight | empty states, transitions and small details feel cared for |

Optional: 2-3 **reference apps** the owner names at D5 ("feels like X"), used for comparison, never copied.

**Pass bar (D-3.4):** no criterion below 3 in the **owner's** scores (R10, D5). An **agent** score below 3 is a **minor
finding**, never a blocker.

**What an agent can judge from screenshots:** alignment and spacing against the tokens, hierarchy and contrast, truncation and
overflow (Danish is longer), light/dark parity, consistency across screens, differences from the wireframes, unfinished states.
**It cannot judge:** motion, touch feel, real-device size and density, felt speed, or **taste**. So agent scores are advisory
findings, and taste stays with the owner. When an agent score disagrees with the owner's, that is a calibration note for
the rubric, not a finding.

## 5. Meta-review: the usefulness ledger and the rule

### 5.1 Ledger
One **`review` row per review run** in `docs/agent-metrics.csv` (same file and script as the other row types; the row type is
added by M0.5-24). Columns:

`date, review_id, run_ref, findings, acted_on, ignored, disputed, deferred, cost_usd, window_end`

* `review_id` is `R1`..`R12`; `run_ref` is the PR number, the ISO week (`2026-W47`) or the milestone (`M1`).
* The orchestrator posts the row (a `# metrics:review` block in a #15 comment, like the other row types, ORCHESTRATION 6) **at
  `window_end`**, when the counts are final; until then the run is listed in #15 as open with its `window_end`. Unknown cost stays empty, never estimated.
* **Acted on:** the finding led to a merged PR, a closed issue or a recorded decision before `window_end`.
  **Disputed:** withdrawn, or rejected by the owner. **Deferred:** a follow-up issue still open (counted as acted on once closed).
  **Ignored:** everything else at `window_end`. The counts add up: `findings = acted_on + ignored + disputed + deferred`.
* **Window (`window_end`):** per-PR reviews (R1, R7, R9): until the PR merges or closes. Weekly reviews (R3, R4): **2 weeks**
  after the run. Milestone and release reviews (R5, R6, R8, R10-R12): **the end of the next milestone** (D-4.3).
* R2 is not ledgered (it produces no findings; incident rows cover it).

### 5.2 Rule
* A review with **0 acted-on findings in 3 consecutive runs** is **re-scoped** (narrower input, lower cadence or a cheaper
  model) or **dropped**.
* A review whose **disputed share is over half across 3 runs** is re-scoped for precision.
* **R1 and R7 are never dropped**; they can only be re-scoped to become more precise.
* **Who:** the R6 retro runs the meta-review from the ledger and proposes the changes as a small docs PR; the owner merges, and
  the expected effect is checked at the next retro. R3 shows the running counts each week and decides nothing.
* A run still inside its window counts as neither a hit nor a miss. Runs skipped because their input did not change are not runs.
