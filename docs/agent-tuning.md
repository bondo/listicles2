# Agent tuning log

The R6 retro log (PLAN 9.4, `docs/reviews/README.md` R6). Each retro adds a section, and the next retro checks the expected
effect of the changes before it. Changes to `agents/roles.yaml`, thresholds and protected files are owner merges.

Comment ids below are on issue #15 (`https://github.com/bondo/listicles2/issues/15#issuecomment-<id>`) unless a PR is named.

## 2026-11-18: M0.5 retro (task M0.5-28), Agent Usage Redesign pilot against its baseline

### Scope and sources

- **Proposal:** the "Agent Usage Redesign" (owner-approved rev 46, comment 6941907770). The pilot table, pass rule and
  kill switch below are quoted from its Rollout section.
- **Baseline window:** 2026-11-12 to 2026-11-17 07:41 UTC. This covers #15 comments 1 to 201 (the last is 6940749891) and
  the 51 PRs merged in those days. Review-round medians also use the M0 PRs (#1 to #40).
- **Pilot window:** 2026-11-17 12:50 UTC to 2026-11-18 09:00 UTC, about 20 hours. It starts when redesign PR 1a (#126)
  merged and the new `agents/roles.yaml` took effect.
  - PRs merged in the window: #126 (the start), #113, #123, #124, #125, #128, #129, #130, #131, #133, plus the five
    Dependabot PRs #107, #108, #110, #111 and #112. That is 15, of which 10 are agent PRs.
  - Still open: #135.
- **Data:**
  - GitHub data for PRs #1 to #135 (findings comments, PR-body round tables, commits, merge SHAs).
  - All 277 comments on #15.
  - `get_session` usage and context for 11 pilot sessions: the three orchestrators, the planner, five implementers,
    the redesign PR 4 implementer and merge agent #3.
  - `rate_limit_event`s of orchestrators #10 to #12.
  - `docs/agent-metrics.csv` holds only the M0 backfill. No `# metrics` block was posted in either window (see P2).
- **Sampling:** transcripts were sampled with event filters, not read in full. Compaction was checked on sampled event
  pages only, not on a full scan.

### The pilot ran on a partial rollout

Before reading the rows, note three things about what the pilot actually tested:

1. **Redesign PR 4 (orchestration) never merged.** It was never opened. It waits on #135, a guard change; PR 4 is blocked
   by a guard false positive on the word "threshold" (owner call 6969709604).
   - Not in effect during the pilot: delta review always, the parallelism and throttle text, and the risk:high merge
     scope.
   - Also not in effect: the `docs/ORCHESTRATION.md` role table.
2. **Implementers ran on the wrong model.** `agents/roles.yaml` says implementer opus/high. Every sampled pilot
   implementer ran Sonnet at high effort (#128, #129, #131, #133, #135 and PR 4), and merge agent #3 ran Sonnet/medium.
   - Cause: `agents/prompts/orchestrator.md:3` says ORCHESTRATION.md wins where the two differ.
   - `docs/ORCHESTRATION.md:15` still says "Implementer: Sonnet / medium" (PR 4 would have changed it).
   - Reviewers and the planner ran on Opus as specified.
3. **The verifier arrived mid-window.** The prompts came with #128 (14:59 UTC) and the `verified` field with #129
   (21:44 UTC), so most blocker and major findings in the window have no verification record.

### Pilot rows

| Row | Baseline | Pilot | Target | Result |
|---|---|---|---|---|
| Commits merged without review (hard) | M0: #1 merged 3 commits after the last round, #16 merged 2. Baseline window: about 10 of 51 PRs merged commits after the last review (e.g. #34 a3517d5, #42 round-3 fixes, #63 4db4f8e, #94 cc6b04b) | **0** non-merge commits reached main unreviewed. Every squash tree equals its reviewed head plus clean merges of main (checked with `git merge-tree`). There were no direct pushes to main | 0 | **Holds, under two readings (below)** |
| Escaped defects in security-rules, sync-merge, release or risk:high work (hard) | not tracked | **0**. No issue has a `Caused by: #N` line, and the `escaped` label has 0 issues | 0 | **Holds** (weak evidence: tracking started with #128, and no protected-area code merged in the window) |
| Usage: no limit-reached pause caused by agent work (hard) | 2 limits reached (6831844631, 6903099936), 2 early pauses (6835199036, 6898397238) | **0** pauses or warnings in #15. Every sampled `rate_limit_event` was `allowed`; five_hour peaked at 0.37 and seven_day at 0.23 | none | **Holds** |
| Owner process interventions per merged PR | 15 process comments (of 68 owner-input comments; the split is below) + owner merges (up to 51), over 51 PRs = **0.29 to 1.29** | 14 process comments + 6 owner merges (#126, #113, #128, #129, #131, #133), over 15 PRs = **1.33**; over the 10 agent PRs = **2.0** | half the baseline or less | **Not met**, under every reading of the baseline merges |
| Review rounds per PR, per class (median) | Tooling: 12 on PR #1 (the proposal's figure); like for like, M0 median 2 and baseline-window median 2 (30 PRs). Docs/design: M0 median 2, baseline-window median 2 (15 PRs) | Tooling: **3** (#128 3, #129 3, #133 4). Docs/design: **4** (#113 4, #123 4, #124 4, #131 2) | at or below the class baseline | **Docs not met.** Tooling meets the written 12 only because PR #1 is an outlier; it is worse than like for like (2) |
| Confirmed share of blocker and major findings | not tracked | **3 of 3** confirmed since the verifier existed (#135 R1-01, R2-01, R3-01). Over the whole window, 3 of 10 have a record; none was withdrawn | reported; under half sends the reviewer prompt to the retro | Reported. Not under half, so no reviewer-prompt change |
| Usage per PR class | no per-class data (no session rows in the baseline window; CSV: M0-1 $4.28, M0-2 $5.02) | Tooling implementer about $5.1 a PR (5 sessions); design implementer #131 $5.38; planner for #123 to #125 $23.21; merge agent $7.71 for 8 merges; orchestrators $82.75 for 3 sessions. Reviewer rounds sampled at $0.78 and $1.66 (2 of about 25) | reported | Reported. **No baseline to compare against** (P2) |

**Readings behind the first hard row:**
- **Narrow checks:** #123, #124 and #125 each merged one fix made after the round cap. Each fix was covered by an
  owner-allowed narrow fresh check of just those lines, not a full round (PR comments 6953155934, 6954551652 and
  6954552779, allowed in 6951347730 and 6953708672). This retro counts a fresh reviewer's check as review.
- **Dependabot:** the five Dependabot PRs had no per-PR review, only one batch triage by a report-only worker
  (6970069776, which notes the SHA-to-tag mapping was not independently verified). Agent work never merged without
  review. If the owner rules that batch triage is not review, the row reads 5 and the pilot fails on a hard row.

#### How the 68 owner-input comments split (criteria for comment 6951347730, Q-B)

- **Rule:** a comment records owner input when its heading starts with "Owner" (any case) or "STANDING OWNER RULE".
  Orchestrator-headed status lines such as "owner merged #N" are not counted; merges are counted from the PRs instead.
  - This reproduces the proposal exactly: 68 comments, 47 of them headed "Owner decision (".
- **Product:** product scope, UX and design, wording, palette, stories, OQ answers (including their deferrals), naming,
  legal, Play and privacy, and collaborator information.
  - 53 in the baseline, e.g. 6896823756, 6900594233, 6901641673, 6926251686, 6929152480.
- **Process:** approvals to merge or mark ready; acceptance of permissions, allowlists, environments or licences;
  review-cap exceptions and tie-breaks; unblock choices; pause and resume; standing process rules; tooling requests;
  deferrals of process or owner-ops tasks; milestone gating.
  - 15 in the baseline: 6846985546, 6847460463, 6848357888, 6897271566, 6897334373, 6897930601, 6898005378,
    6901740774, 6902319806, 6908199967, 6908217198, 6909579309, 6918199738, 6926418662 and 6927323948.
- **Mixed comments** are classed by the decision their heading names.
- **Undercount:** the heading rule misses owner process input that 11-12 and 11-13 logged under "Decision log" or
  orchestrator headings. A wider rule gives 99 comments (43 process). Under that rule the pilot is still not at half the
  baseline: pilot 1.4 against a baseline of at least 1.0 once owner merges are added.
- **Pilot window:** 17 owner-input comments, 14 of them process:
  - round-cap exceptions: 6951347730, 6953708672;
  - M1 gating: 6957230934, 6969901178;
  - the guard false positive: 6969709604;
  - a REVIEW.md severity rule and question language: 6969890077;
  - Dependabot handling: 6969936623, 6970228007;
  - owner-ops confirmations and deferrals: 6969955406, 6969965136, 6969987326, 6969995643;
  - a merge-script task: 6970525540;
  - reviews before M1: 6971244583.
  - Nine of them came in one sitting (05:09 to 06:01 UTC on 11-18) that cleared a queue of owner-ops questions.
  - The product ones are 6951461657, 6956773225 and 6969924163.

### Verdict: FAIL

The pass rule is "every hard row holds and at least one of the other targets is met". The three hard rows hold (the
first under the two readings above), but neither other target is met:
- Owner process interventions per PR went up instead of halving.
- The docs review-round median doubled (2 to 4).
- The tooling median beats only the single-PR figure of 12, not the like-for-like median of 2.

Two things limit the weight of this verdict. The pilot ran for about 20 hours on 10 agent PRs, and it ran without
redesign PR 4 and with implementers on Sonnet instead of the roles.yaml Opus. So it measured a partial rollout, not the
proposal. Quality did not get worse: there were no unreviewed agent commits, no escaped defects, no usage pause, and
every verified finding was confirmed. Proposal P3 asks the owner how to act on the fail.

### Kill switch

- **Owner trigger:** PILOT-STOP was never written; it appears in none of the 277 #15 comments.
- **Automatic triggers:** none fired. There was no unreviewed commit in main, no escaped defect in a protected area and
  no limit-reached pause.
- **Fallback set:** present at `agents/roles.yaml:78` (the `fallback:` key), never used.
- **Gap:** neither `agents/prompts/orchestrator.md` nor `docs/ORCHESTRATION.md` mentions PILOT-STOP or the fallback set.
  An orchestrator following its prompt has no step that checks for the stop word or spawns with the fallback. The
  switch exists on paper only (P1).

### Compaction before handoff

- **Result:** no compaction found, and no handoff note was needed.
  - All 11 sampled pilot sessions ended at or below 52% context. Autocompact sits at 78.4%, and the step boundary in
    `agents/roles.yaml` is 60% of a 1M window.
  - The orchestrator handovers happened at about 47% (6947005038 and 6971287839) and 48% (#10 to #11, 6962900678).
  - No pilot branch committed a handoff note; the only one, handoff/merge-agent-handoff.md, predates the pilot.
- **Coverage:** sampled event pages showed no compact boundary, but a full event scan was not done.
- **Caveat:** no session came near the threshold, so this pilot did not test the handoff path.

### Proposed changes (at most 3; the owner merges them, none is implemented here)

**P1: Make the orchestrator run what `agents/roles.yaml` says, and wire up the kill switch.** This is a tooling PR on
protected files; the owner merges it.
- Land redesign PR 4 after #135, so that the `docs/ORCHESTRATION.md` role table (line 15) matches `agents/roles.yaml`.
  Alternatively, replace the table's model column with "see roles.yaml".
- Add a `scripts/prompt_rules.py` rule, tested first, that fails when a role's model or effort in ORCHESTRATION.md or a
  prompt differs from `agents/roles.yaml`.
- Add two steps to every orchestrator wake: check #15 for PILOT-STOP, and spawn with the fallback set if it is found.
- The roles.yaml values themselves do not change.
- **Expected effect, checked at the next retro:**
  - 100% of sampled worker sessions have `configured_model` and effort equal to roles.yaml (pilot: 0 of 6
    implementers).
  - The kill switch has a step that a test checks.

**P2: Feed the metrics pipeline that the retro depends on.** This changes the orchestrator prompt and
`docs/ORCHESTRATION.md` §6 (protected; owner merge).
- Make the §6.1 session row and the §6.2 round row a required part of collecting each WORKER-RESULT. Today they are
  specified but were not posted once in either window.
- At each milestone end, save the rows to `docs/metrics/` as §6 already says.
- **Expected effect:** the next retro compares usage and rounds per PR class from `docs/agent-metrics.csv`, with a
  session row for at least 90% of worker sessions, instead of scraping PR threads. The usage-per-class row gets a real
  baseline.

**P3: Owner decision on the fail, and a cheaper path for round-cap minors.** This needs an owner decision plus a
REVIEW.md and ORCHESTRATION.md change (owner merge).
- **Decision (recommended):** keep the redesign roles rather than spawn with the fallback set, because no hard row
  broke. Re-run this comparison on the first M1 batch after P1 lands, on at least 10 agent PRs. With the fallback set,
  implementers go to Sonnet/medium and the reviewer token budgets come back.
- **Change:** let the orchestrator grant, without the owner, the one narrow fresh-reviewer check of a fix made after
  round 4 when only minors and nits remain. That is the pattern of 6951347730 and 6953708672, used on #123, #124 and
  #125.
- **Change:** put open owner-ops questions into one `owner-todo` list, answered together, instead of one comment per
  answer.
- **Expected effect:**
  - Owner process interventions per merged PR fall to half the baseline or less: at most 0.65 if all 51 baseline merges were owner merges (the exact
    baseline count needs the P2 rows or a merged-by audit).
  - The docs/design review-round median falls back to about 2 or 3 with no new unreviewed commits.
  - If either stays above its baseline at the next retro, revert the cap change.
