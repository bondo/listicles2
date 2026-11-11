# Orchestration process

How Listicles work is coordinated across Claude Code cloud sessions: who does what,
where state lives, how a session hands over, and what the owner does by hand.
This is the canonical process. `docs/PLAN.md` §6 (review loop) and §9 (roles, budgets,
handoff, metrics) say *what* we want; this file says *how* it runs day to day.
If they disagree, fix the disagreement in a PR rather than picking one.

## 1. Roles

| Role | Model / effort | Lifetime | Writes to | Never |
|---|---|---|---|---|
| **Owner** (human) | n/a | n/a | GitHub settings, labels, merges, decisions | n/a |
| **Orchestrator** | Sonnet / low | Long-lived; hands over (§5) | The state issue (body and comments), owner-todo and follow-up issues, scheduled tasks, session tags | Commits, pushes, edits files, reviews code, reads full transcripts |
| **Implementer** | Sonnet / medium (high on escalation or `risk:high`) | One batch or PR | Its branch only; `handoff/<branch>.md`; one result comment on its PR; only when no orchestrator is active: follow-up issues and the deferral decision as a PR comment (FOLLOW-UPS.md §4) | Pushes to `main` or to any branch it was not assigned |
| **Reviewer** | Opus / high (max for `risk:high`) | One review round | One findings comment on the PR | Pushes, edits files, approves or merges |
| **Planner / retro / process reviewer** | See PLAN §9 | One task | Its own branch (`claude/<task>`) | Pushes to a branch another session owns |

The orchestrator is the only session that spawns sessions, and at most **one orchestrator
is active at a time**. The `Orchestrator:` line in the state issue is the lock (§3.1).

## 2. Where state lives (one home per fact)

Each fact has exactly one canonical location. Everything else links to it and doesn't copy it.

| Fact | Canonical location | Written by | Read by |
|---|---|---|---|
| Current milestone, batches, running sessions, branch locks, next steps | **State issue** body (currently #15, label `orchestrator-state`), format in [`orchestrator-state.md`](orchestrator-state.md) | Orchestrator only | Orchestrator, successor, owner |
| History: metrics rows, incidents, owner decisions, handovers | **State issue comments** (append-only, §6) | Orchestrator only | Successor, retro, `scripts/agent-metrics` |
| Tasks, dependencies, done/todo (agent and owner work alike) | **`docs/tasks.toml`** at the tasks ref (§4), queried with `scripts/tasks.py` | Planner (adds), the PR that finishes a task (sets `done`), process PRs | Orchestrator (`ready`), everyone |
| Who is working on a task right now (claims) | **State issue** Sessions table, `Task` column | Orchestrator | `scripts/tasks.py --claimed` |
| Owner to-do details and completion | One **issue per owner task**, label `owner-todo`, title `[owner] <task id>: …` (§4.5) | Orchestrator opens; owner closes | Everyone, `scripts/tasks.py --issues` |
| Review findings per round | One **findings comment on the PR**, in the `REVIEW.md` JSON format (§7.2) | Reviewer | Implementer, next reviewer, metrics |
| Deferred findings (follow-ups) | One **issue per finding**, label `follow-up`, body template and rules in [`FOLLOW-UPS.md`](FOLLOW-UPS.md); the deferral decision is a `decision` comment on the state issue | Orchestrator (implementer if no orchestrator is active); never the reviewer | Burn-down task `Mx-FU`, orchestrator (`tasks.py followups`) |
| Implementation progress inside a batch | `handoff/<branch>.md` on that branch | The implementer holding the branch lock | Next implementer on that branch |
| Worker outcome | `WORKER-RESULT` block (§7.3): last message of the session **and** a PR comment | Worker | Orchestrator |
| Cost and tokens per session | `get_session` → `external_metadata.usage` (read once the session is idle) | The platform | Orchestrator, copied into a metrics row |
| Process rules | This file, `PLAN.md`, `REVIEW.md`, `CLAUDE.md` | Reviewed PRs only | Everyone |

Rules that follow from the table:
* Handoff files hold **task** state only. They refer to owner to-dos by issue number
  (`waiting on #14`) and never restate them, and they don't keep running metrics.
* The PR description review table is a **view** of the findings comments, refreshed when
  a batch closes. Findings comments are the source.
* The orchestrator never commits, so it never writes `docs/status.md` or
  `handoff/orchestrator.md`. Its handover note is a state-issue comment (§5).
* When a fact is found to be wrong (e.g. "CI has never run" while check runs exist),
  correct it at its canonical location in the same wake, and log the correction.

### 2.1 Session tags

Every spawned session gets tags so metrics can be pulled later without reading transcripts:

```
listicles:<milestone or task>   e.g. listicles:M0, listicles:process
role:<role>                     orchestrator | implementer | reviewer | planner | retro
pr:<number>                     when the work belongs to a PR
batch:<id>                      e.g. batch:M0-2
task:<id>                       one per task worked on, e.g. task:M0-04
round:<R-id>                    reviewers only, e.g. round:R9
```

## 3. The state issue

The body is the **current** state and is rewritten in place. The fixed template is
[`orchestrator-state.md`](orchestrator-state.md). Keep it under about 80 lines: history
goes to comments, not the body.

### 3.1 Required fields

* `Orchestrator:` session id, started-at, predecessor session id, **lineage depth** (from
  `get_session` → `lineage.depth`).
* `Updated:` UTC timestamp of the last edit, and what triggered it.
* `Tasks ref:` the git ref whose `docs/tasks.toml` is canonical (§4.2).
* **Sessions**: one row per live worker: id, role, tags, branch, **task ids** (the claims), spawned-at,
  expected output, last checked, status (`running | idle-with-result | idle-no-result | failed | archived`).
* **Branches**: one row per active branch: holder (session id or `none`),
  `reviewed_through` SHA, unreviewed commits since then and their disposition.
* **Owner to-dos**: task id and issue number only, each with the orchestrator's follow-up action.
* **Scheduled tasks**: trigger id, the session it fires into, purpose, next run.
* **PR subscriptions** held by the orchestrator.
* **Follow-ups**: the one-line count by severity from `tasks.py followups` (FOLLOW-UPS.md §8).
* **Next**: the next 1-3 actions, concrete enough for a cold successor.

### 3.2 Who may edit

Only the active orchestrator edits the body or posts log comments (the one exception: deferral decisions by an implementer when no orchestrator is active, as PR comments). Workers report through
their PRs (§7.3). The owner comments on the state issue or replies in the orchestrator
session; the orchestrator folds the comment into the body on its next wake.

## 4. Tasks, dependencies and owner to-dos

### 4.1 Options considered

| Option | Deterministic "what's ready"? | Works with our tools | Reviewed and versioned | Visible to the owner | Verdict |
|---|---|---|---|---|---|
| A. GitHub issues + sub-issues + "blocked by" links + labels | No: an agent has to walk links page by page and interpret labels anyone can set | Partly: the GitHub MCP tools here can't set or read "blocked by" links, and `gh` is limited to search | No diff, no review | Yes | Rejected as the source of truth |
| B. A task file in the repo + a small script | Yes: same file + same inputs → same output, and it's testable | Yes: the file is plain text, and the script needs only Python 3.11+ | Yes: changes go through PRs and review | Through the script output and the state issue | **Chosen** |
| C. Both, kept in sync both ways | Only if sync never fails | Needs a sync job (Actions or the orchestrator) | Partly | Yes | Rejected: two sources of truth |

Chosen: **B, plus read-only facts from GitHub.** The graph (ids, dependencies, risk, who) and
`todo`/`done`/`dropped` live in `docs/tasks.toml`. GitHub facts that the file can't know yet
(a closed owner issue, a merged PR) are fed into the script as inputs, never written back by hand.
Issues stay the place for owner to-dos, because the owner needs a clickable item. They're linked to tasks by id.

### 4.2 Schema (`docs/tasks.toml`)

```toml
milestones = ["M0", "M0.5", "M1", "M2", "M3", "M4", "M5", "M6"]   # order = priority

[[task]]
id = "M1-03"              # <milestone>-NN (agent) or <milestone>-O<n> (owner); stable, never reused
title = "Invite links: create, redeem, revoke + rules tests"
milestone = "M1"
status = "todo"           # todo | done | dropped   (no "in progress": that is a claim, §2)
assignee = "implementer"  # owner | implementer | planner | process | retro
risk = "high"             # normal | high (PLAN 9.1 risk:high → high effort, max-effort review)
depends_on = ["M1-02", "M0.5-O1"]   # task ids, or "milestone:M0" = all of M0 done or dropped
issue = 31                # optional; owner tasks: the to-do issue
pr = 7                    # optional; the PR that delivers it
notes = "…"               # optional, one line
```

`scripts/tasks.py validate` rejects:
* unknown fields, missing fields and bad enum values
* duplicate ids, and ids that don't start with their milestone
* owner ids on non-owner tasks, and the reverse
* unknown dependencies, and dependencies on the task's own milestone
* cycles, including cycles through `milestone:` dependencies
* a milestone with agent work and no burn-down task `<M>-FU`, or a burn-down that is not assigned to `implementer`
  or does not depend on every other non-owner task of its milestone (FOLLOW-UPS.md §8; ids end in `-FU`)

**Tasks ref.** The canonical copy is `docs/tasks.toml` on `main`. Until M0 is merged, `main`
has no task file, so the tasks ref is the PR #1 branch (once this branch has been merged
into it; until then, `claude/orchestration-review`). The state issue's `Tasks ref:` line says
which one applies.

### 4.3 The ready query (the only way to pick work)

The orchestrator runs this on every wake, before it spawns anything. It runs the script from
the tasks ref, without checking it out:

```bash
REF=claude/sleepy-mccarthy-z2paqx      # the "Tasks ref:" line; main once M0 is merged
T="${TMPDIR:-/tmp}/tasks"; mkdir -p "$T"
git fetch -q origin "$REF"
git show "origin/$REF:scripts/tasks.py" > "$T/tasks.py"
gh api -X GET search/issues -f q='repo:bondo/listicles2 is:issue -label:follow-up' -f per_page=100 \
  --jq '{items: [.items[] | {number, title, state}]}' > "$T/issues.json"
gh api -X GET search/issues -f q='repo:bondo/listicles2 is:pr is:merged' -f per_page=100 \
  --jq '{items: [.items[] | {number, merged_at: .pull_request.merged_at}]}' > "$T/prs.json"
gh api -X GET search/issues -f q='repo:bondo/listicles2 is:issue is:open label:follow-up' -f per_page=100 \
  --jq '{items: [.items[] | {number, title, state, labels: [.labels[].name]}]}' > "$T/followups.json"
python3 -I "$T/tasks.py" --ref "origin/$REF" --issues "$T/issues.json" --prs "$T/prs.json" \
  --followups "$T/followups.json" --claimed "<comma-separated task ids from the Sessions table>" ready
```

* The output is one line per ready task, sorted by milestone order and then by position in the file.
  `--json` gives the same list as JSON. `--assignee agent` or `--assignee owner` splits it.
  `status` shows every task with its derived state and what it waits on.
* The last line is the open follow-up count by severity, and a ready `Mx-FU` line shows its own milestone's count.
  Copy the count to the state issue's `Follow-ups:` line. `--json` output of `ready` is unchanged;
  `tasks.py --followups … followups` lists the issues by severity.
* A task is **ready** when it is `todo`, every dependency is satisfied (`done`, `dropped`, or an
  owner task finished on GitHub), and no running session claims it.
* An owner task counts as finished when its `issue` is closed, when a closed issue is titled
  `[owner] <id>: …`, or when its `pr` is merged (merge tasks such as M0-O7). Agent tasks finish
  **only** through `status = "done"` in the file.
* The search API can lag by a minute or so. If a result contradicts something you just did, run the query again.
* The script runs from the tasks ref, not from the working tree, so every session gets the same answer.

### 4.4 How status changes

| Change | Who | How |
|---|---|---|
| Add tasks | Planner (per milestone), process PRs | In the same PR as `docs/milestones/Mx.md`. New work found mid-flight (a deferred finding, say) is added by the PR that finds it, or noted in the state issue under "pending task additions" for the next PR |
| Claim (start) | Orchestrator | Add the task id to the worker's row in the Sessions table, then spawn. Release the claim when the worker ends |
| `todo` → `done` (agent task) | The implementer, in the PR that delivers it | Usually in the final commit, alongside deleting the handoff file. The reviewer checks that the PR marks exactly its own tasks as done. Because merges are squash-only, `done` shows up on `main` exactly when the work merges. For multi-step PRs such as M0, a step is marked done on the PR branch once its batch review has finished |
| Owner task finished | Owner | Close the issue (or merge the PR). This takes effect at once through `--issues`/`--prs`. The next PR that touches the file sets `status = "done"`; `drift` lists what is outstanding |
| `dropped` | Owner decision, recorded by the next PR | Add `notes` with the reason and a link to the decision comment |
| Edits to ids or dependencies | Planner or process PR | Ids are never reused or renumbered |

`scripts/tasks.py drift --issues … --prs … --followups …` reports:
* closed owner issues whose task is still `todo`
* `done` tasks whose issue is open
* merged PRs whose task is still `todo`
* `[owner] <id>` issue titles that name an unknown task
* follow-up issues that break the deferral rules or lack labels (blocker; major or protected `area:` without `owner-ok`;
  no `severity:` or `target:`; targeting a milestone whose burn-down is already done)

The orchestrator logs drift in the state issue and hands it to the next implementer or process session.

### 4.5 Owner to-dos

Owner work is tasks with `assignee = "owner"`, and each one gets an issue once it is **ready**
(not before, so the owner's list holds only actionable items):

* Title `[owner] <task id>: <imperative>`, label `owner-todo`. Older issues (#12-#14) are linked through
  the task's `issue` field instead.
* Body, in this order:
  * **What**: one sentence.
  * **Where**: the exact click path or command.
  * **Why**: what is blocked until it's done (list the tasks that depend on it).
  * **Done when**: something the orchestrator can check (a label exists, the default branch is `main`,
    the repository is public, a secret is set).
  * **Then**: what the orchestrator does next.
* The owner closes the issue when done. They don't need to tell the orchestrator: on each wake the
  orchestrator runs the ready query (closed issues count at once), checks *Done when* itself, and logs
  `todo-done <id>` in the state issue. If the check fails, it reopens the issue with a one-line comment.
* Reminders are scheduled tasks bound to the **current** orchestrator, recorded in the state body.
* When you report to the owner, give the ready owner tasks (`--assignee owner ready`) as one short list in priority order.

## 5. Orchestrator handover

Trigger: about 50% context (`get_session` with no id → `context_usage.used_tokens / max_tokens`,
or the status line once M0 step 5 lands). Prefer handing over at a **batch boundary**
once past about 30%, rather than mid-batch at 50%.

### 5.1 Outgoing orchestrator checklist

1. Finish or abandon the current step. Leave no half-sent message and no spawn without a row in the body.
2. Refresh every running worker's status (`get_session`). Record cost for idle workers.
3. Rewrite the state body from the template. Every field in §3.1 must be filled, and `Next:` must be concrete.
4. Post a `handover` log comment: what changed since the last handover, open questions, and anything
   you suspect is stale.
5. `list_triggers`: for each reminder bound to you, note it in the handover comment so the
   successor recreates it. Delete it only after the successor confirms it has recreated it.
6. Note the PR subscriptions you hold. Unsubscribe right before you stop, so the successor can take them over.
7. Spawn the successor with the bootstrap prompt (§8.1), unless lineage depth is ≥ 6 (§9, F3).
   In that case, ask the owner to start it from the app with the same prompt.
8. Wait for the successor's `handover-ack` comment on the state issue, then unsubscribe and stop. Don't spawn,
   edit the body or message workers after that. The owner archives you.

### 5.2 Incoming orchestrator checklist

1. Read this file, then the state body, then the comments since the last `handover`.
   Don't read predecessor transcripts.
2. Check that the state is true. For each session row, run `get_session`. For each branch row, compare
   `git ls-remote` HEAD against the recorded SHA. Run the ready query (§4.3) and `drift`.
   Note what you corrected.
3. Recreate the reminders listed in the handover comment, bound to yourself. Subscribe to the PRs.
4. Set `Orchestrator:` to yourself (with predecessor and depth), and post `handover-ack`.
5. Child-session failure events go to the session that **spawned** a worker, so a predecessor's
   workers will not wake you. Schedule a check-in (`send_later`) for each one that is still running.

## 6. Metrics and incidents

Source of truth: the state-issue log comments, in fixed CSV blocks that `scripts/agent-metrics`
(PLAN §9.4) can later turn into `docs/agent-metrics.csv` without reading transcripts.
Numbers come from tools, never from memory or estimates. If a value is unknown, write
an empty field, not a guess.

### 6.1 Session row (one per worker, once it is idle)

```csv
# metrics:session
date,batch,pr,tasks,role,session_id,model,effort,result,cost_usd,input_tokens,output_tokens,cache_read_tokens,cache_write_tokens,handoffs,verify_fails_before_push,ci_red_runs
{date},{batch},{pr},{task ids space-separated},reviewer,{session_id},{last_served_model},high,done,{cost},{in},{out},{cache_r},{cache_w},0,,
```

`cost_usd` and the token fields come from `get_session` → `external_metadata.usage`.
`model` is `last_served_model`. If it differs from `configured_model`, say so in an incident row.

### 6.2 Round row (one per review round)

```csv
# metrics:round
date,batch,pr,round,reviewer_session,base_sha,head_sha,blocker,major,minor,nit,disputed,withdrawn,deferred,verdict
2026-11-10,M0-1,1,8,session_...,809080c,c1b54ff,0,0,1,1,0,0,0,changes_requested
```

Rounds are numbered **per PR**, globally and monotonically (1, 2, … giving IDs R1-…, R2-…) and never reset per batch.
The 4-round cap counts rounds **within a batch**. A finding ID is `R<round>-<nn>` (e.g. `R8-01`).
`blocker`..`nit` count the round's findings by severity as reported. `deferred` counts findings of that round the orchestrator later deferred
(it can only be filled once the decision is made; leave it empty until then, never guess). `verdict` is the reviewer's (`changes_requested | ready_nits_only`), or one the orchestrator sets: `cap_reached` after
round 4 of a batch, or `ready_deferred` when every finding above nit was deferred and no commit followed (FOLLOW-UPS.md §4).

### 6.3 Incident row

```csv
# metrics:incident
date,batch,session_id,kind,impact,recovery,prevention
2026-11-10,M0-1,session_...,destructive-git,uncommitted work lost,reflog,PreToolUse deny hook (M0 step 5)
```

Suggested values for `kind`: `destructive-git`, `wrong-branch-push`, `concurrent-push`, `dead-session`,
`stale-state`, `model-fallback`, `unreviewed-merge`, `budget-over`, `guard-bypass`, `task-drift`.

### 6.4 Batch summary

When a batch closes, update the batch table in the state body: rounds, findings per round,
total cost, incidents. Then refresh the PR description's review table from the round rows.

## 7. Spawning and collecting work

### 7.1 Spawning

* Start only tasks that the ready query (§4.3) lists, in the order it lists them. Batching several ready
  tasks of one PR into one session is fine; claim them all.
* `create_session` with the spawn message (§8), the tags from §2.1, the model and effort
  from PLAN §9.1, and for writers `outcome_branch` = the branch they hold.
* **Branch lock**: before spawning a writer, set the branch's holder in the state body.
  Only one writer per branch at a time. Reviewers hold no lock and never push.
* At spawn time, schedule a check-in (`send_later`, about 45-60 min for implementers and
  about 30 min for reviewers) and record it in the body.

### 7.2 Review rounds

* The orchestrator gives the reviewer the PR number, `base_sha` (= the branch's
  `reviewed_through`), `head_sha`, the round ID, the IDs of findings that are still open, and the IDs of deferred findings with their issue
  links (the reviewer re-checks each deferral record against FOLLOW-UPS.md §2).
* The reviewer reviews `base_sha..head_sha` only, plus re-checks of open findings, and posts **one**
  PR comment with the fenced `json` block defined in `REVIEW.md` (`round` as a number,
  `reviewed_range` = `base_sha..head_sha`, finding IDs `R<round>-<nn>`, `verdict`
  `changes_requested | ready_nits_only`), followed by its `WORKER-RESULT` block (§7.3).
  `REVIEW.md` owns the format; this file does not repeat it. **Until M0-10 aligns `REVIEW.md`**, each finding also
  carries `area`, `recommend` (`fix-now | defer`) and `recommend_reason`, and `status` may be `deferred`
  ([`FOLLOW-UPS.md`](FOLLOW-UPS.md) §5). The reviewer recommends only. The orchestrator decides deferral (§7.2.1).
* After the round, the orchestrator sets `reviewed_through = head_sha`.
* Any commit after `reviewed_through` is **unreviewed** until the next round covers it, or until the
  owner explicitly accepts it. That acceptance goes in a `decision` log comment and in the branch row.
  Handoff-only and docs-only commits still count. They are listed, not silently skipped.

### 7.2.1 Deferring findings

Rules, labels and the issue template: [`FOLLOW-UPS.md`](FOLLOW-UPS.md). In short: after each round the orchestrator
sorts the findings. Everything not deferred goes back to the implementer. Nits and minors may be deferred when no
blocker or major is open; majors only with owner OK; blockers never; anything in `security-rules`, `sync-merge`
or `release`, or on a `risk:high` task, never without owner OK. For each deferral it files the follow-up issue, posts a
`decision` comment on the state issue, and lists the finding in the PR's review table (`Deferred` column). The 4-round cap
and the "only nits remain" test count only unresolved, non-deferred findings. If everything above nit was deferred and no
commit followed the reviewed range, the PR needs no further round: the orchestrator posts a `decision` comment
`accepted: all findings above nit deferred (#a, #b)` and sets the round's verdict to `ready_deferred`; that is the owner's
signal to merge. More than 8 open follow-ups for one milestone: stop deferring and report to the owner (count targets
with `tasks.py --followups … --json followups`). The deferral is in the decision comment at once; the PR review table
is refreshed at batch close and no later than when the PR is declared ready.

### 7.3 Results

Every worker ends its last message with this block and also posts it as a PR comment
(the reviewer appends it to its findings comment):

```
WORKER-RESULT
status: done | partial | blocked | failed
role: implementer | reviewer | ...
session: <own session id>
branch: <branch> @ <head sha after last push, or "no push">
pr: <number or none>
summary: <=3 lines
open_items: <finding IDs / steps left / "none">
needs_owner: <decision or action, or "none">
handoff: <path to handoff file, or "none">
```

The orchestrator collects results in this order, from cheapest to most expensive:
1. Read PR comments (durable, and visible to a successor too).
2. `get_session` status bucket.
3. `list_events` with `kinds: ["result"]` and a small `limit`. Never read whole transcripts.

### 7.4 Failure handling

| Symptom | Action |
|---|---|
| Worker idle, no `WORKER-RESULT` | `send_message` once: "post your WORKER-RESULT". If there is still nothing at the next check-in, treat it as dead. |
| `status_bucket` failed, or no progress across two check-ins | Mark the row `failed` and log an incident. Read `handoff/<branch>.md` and `git ls-remote` HEAD. Interrupt the session if it might still push. Only then release the lock and spawn a fresh worker from the handoff file. |
| Branch HEAD moved but no session holds the lock | Stop spawning on that branch. Identify the commit's author (`git log`). Log a `concurrent-push` incident and ask the owner. |
| Model fallback (`last_served_model` ≠ `configured_model`) | Log an incident. For a reviewer, rerun the round on the intended model before trusting a "ready" verdict. |
| Escalation (PLAN §9.1: 3 identical verify failures, 2 rounds with blockers) | Spawn a fresh implementer at high effort from the handoff file. |
| Over budget (PLAN §9.4) | Don't stop the work. Flag it in the session row for the retro. |

Archive finished worker sessions once their metrics row is logged and the owner has
seen the batch report.

## 8. Spawn messages

The role rules live in `agents/prompts/<role>.md` (models and effort in `agents/roles.yaml`).
A spawn message points at the role prompt and adds only the per-task parameters below, so
rules are never copied into prompts. Until task M0-10 aligns `agents/prompts/*`, the bodies
below win where they disagree (the prompts still mention `docs/status.md`,
`handoff/orchestrator.md` and an older summary format). Placeholders are `{…}`.

### 8.1 Orchestrator bootstrap (successor, or owner-started)

```
You are the Listicles orchestrator for bondo/listicles2 (rules: agents/prompts/orchestrator.md,
overridden by docs/ORCHESTRATION.md where they differ). You coordinate only: never edit files,
commit or push. Read docs/ORCHESTRATION.md, then state issue #{state_issue} (body, then comments
since the last "handover"). Do §5.2 (incoming checklist) first, including the ready query (§4.3),
then continue from "Next:". Predecessor: {session_id}.
```

### 8.2 Implementer

```
Role: agents/prompts/implementer.md. Repo bondo/listicles2, PR #{pr}, batch {batch}.
Tasks: {task ids with titles} (docs/tasks.toml). Branch: {branch}. You are its only writer.
Inputs: {Mx.md section / steps}, handoff/{branch_slug}.md if present.
In the PR that finishes a task, set its status = "done" in docs/tasks.toml. Add any new task
you discover there too, with dependencies.
Refer to owner work by task id or issue number only.
Finish with a WORKER-RESULT block (docs/ORCHESTRATION.md §7.3): your last message, and a comment on PR #{pr}.
```

### 8.3 Reviewer

```
Role: agents/prompts/reviewer.md. PR #{pr}, round {round}, range {base_sha}..{head_sha}.
Open findings to re-check: {ids with one line each}. Tasks this PR claims to finish: {task ids}.
Check that docs/tasks.toml marks exactly those as done.
Post ONE PR comment: the REVIEW.md json block, then a WORKER-RESULT block
(docs/ORCHESTRATION.md §7.3), and repeat that block as your last message. Don't push.
```

### 8.4 One-off task (planner, retro, process review)

```
You are a fresh-context {role} for Listicles (bondo/listicles2). Task {task id}: {task}.
Inputs: {files/issues}. Push only to {branch}; don't open a PR unless told to.
Planners: add PR-sized tasks with dependencies and risk to docs/tasks.toml, and run
scripts/tasks.py validate.
Finish with a WORKER-RESULT block (docs/ORCHESTRATION.md §7.3).
```

## 9. Known failure modes and mitigations

| ID | Failure | Mitigation in this process |
|---|---|---|
| F1 | State is duplicated (handoff "Waiting on the owner", the state issue, the to-do issues, the PR body table) and drifts | One home per fact (§2). Others link by number |
| F2 | Facts go stale (e.g. "CI has never run" after CI ran) | The incoming orchestrator verifies (§5.2), and every wake corrects at the source (§2) |
| F3 | Session lineage depth is capped at 8; each orchestrator that spawns its successor adds a level, and workers sit one level deeper | Record depth. At depth ≥ 6, the owner starts the next orchestrator from the app (§5.1 step 7) |
| F4 | Scheduled tasks and PR subscriptions are bound to one session and don't follow a handover | Record them in the body. The successor recreates them and the predecessor deletes or unsubscribes (§5) |
| F5 | Child failure events go only to the spawning session | Check-ins via `send_later` plus `get_session` polling (§7.1, §5.2) |
| F6 | Two writers on one branch (two implementers, or the owner merging a Dependabot PR into a feature branch) | Branch lock (§7.1). Don't merge PRs whose base is a feature branch |
| F7 | Unreviewed commits reach a merge | `reviewed_through` per branch, with explicit owner acceptance logged (§7.2) |
| F8 | Review findings exist only in transcripts and commit messages, so metrics and re-checks lose them | A findings JSON comment on the PR per round (§7.2) |
| F9 | Cost numbers without a source | Read `get_session` usage only. Leave unknown values empty (§6) |
| F10 | The owner has to relay "done" to the orchestrator | The orchestrator checks `owner-todo` issues itself on each wake (§4) |
| F11 | Two orchestrators alive at once overwrite the body | The `Orchestrator:` lock, plus the ack-then-stop handover (§5.1 step 8) |
| F12 | "What's next" is decided from memory, so dependencies get skipped or work gets started twice | `scripts/tasks.py ready` with claims is the only way to pick work (§4.3) |
| F13 | Task status drifts from GitHub (closed owner issue, merged PR) | Status is derived from GitHub on every query. `drift` lists what the next PR must fix in the file (§4.4) |
| F14 | Role prompts and this file disagree (e.g. `agents/prompts/orchestrator.md` still says to write `docs/status.md`) | This file wins until task M0-10 aligns the prompts. Reviewers flag the disagreement |
| F15 | Minor findings block acceptance, or are deferred and forgotten | Follow-up issues with a mandatory burn-down task per milestone that the ready query enforces ([`FOLLOW-UPS.md`](FOLLOW-UPS.md)) |
