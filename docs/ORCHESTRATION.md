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
| **Orchestrator** | Sonnet / low | Long-lived; hands over (§5) | The state issue (body and comments), owner-todo issues, scheduled tasks, session tags | Commits, pushes, edits files, reviews code, reads full transcripts |
| **Implementer** | Sonnet / medium (high on escalation or `risk:high`) | One batch or PR | Its branch only; `handoff/<branch>.md`; one result comment on its PR | Pushes to `main` or to any branch it was not assigned |
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
| Owner to-dos | One **issue per to-do**, label `owner-todo` (§4) | Orchestrator opens; owner closes | Everyone |
| Review findings per round | One **findings comment on the PR** with a JSON block (§7.2) | Reviewer | Implementer, next reviewer, metrics |
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
* **Sessions**: one row per live worker: id, role, tags, branch, task, spawned-at,
  expected output, last checked, status (`running | idle-with-result | idle-no-result | failed | archived`).
* **Branches**: one row per active branch: holder (session id or `none`),
  `reviewed_through` SHA, unreviewed commits since then and their disposition.
* **Owner to-dos**: issue numbers only, each with the orchestrator's follow-up action.
* **Scheduled tasks**: trigger id, the session it fires into, purpose, next run.
* **PR subscriptions** held by the orchestrator.
* **Next**: the next 1-3 actions, concrete enough for a cold successor.

### 3.2 Who may edit

Only the active orchestrator edits the body or posts log comments. Workers report through
their PRs (§7.3). The owner comments on the state issue or replies in the orchestrator
session; the orchestrator folds the comment into the body on its next wake.

## 4. Owner to-dos

Each to-do is its own issue so it can be closed, linked and searched:

* Title `[owner] <imperative>`, label `owner-todo`.
* Body, in this order:
  * **What**: one sentence.
  * **Where**: the exact click path or command.
  * **Why**: what is blocked until it's done.
  * **Done when**: something the orchestrator can check (a label exists, the default branch is `main`,
    the repository is public, a secret is set).
  * **Then**: what the orchestrator does next.
* The owner closes the issue when done. They don't need to tell the orchestrator: on each wake
  the orchestrator lists open and recently closed `owner-todo` issues, checks the
  *Done when* condition itself, and logs `todo-done #N` in the state issue. If the check fails, it reopens the issue with
  a one-line comment.
* Reminders are scheduled tasks bound to the **current** orchestrator, recorded in the
  state body. Don't bind them to a worker or to a session that is about to hand over.
* When you report to the owner, give the open to-dos as one short list in priority order. Don't dribble them out one per message.

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
   `git ls-remote` HEAD against the recorded SHA. Re-check each `owner-todo`. Note what you corrected.
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
date,batch,pr,role,session_id,model,effort,result,cost_usd,input_tokens,output_tokens,cache_read_tokens,cache_write_tokens,handoffs,verify_fails_before_push,ci_red_runs
{date},{batch},{pr},reviewer,{session_id},{last_served_model},high,done,{cost},{in},{out},{cache_r},{cache_w},0,,
```

`cost_usd` and the token fields come from `get_session` → `external_metadata.usage`.
`model` is `last_served_model`. If it differs from `configured_model`, say so in an incident row.

### 6.2 Round row (one per review round)

```csv
# metrics:round
date,batch,pr,round,reviewer_session,base_sha,head_sha,blocker,major,minor,nit,disputed,withdrawn,verdict
2026-11-10,M0-1,1,R8,session_...,809080c,c1b54ff,0,0,1,1,0,0,findings
```

Rounds are numbered **per PR**, globally and monotonically: R1, R2, … and never reset per batch.
The 4-round cap counts rounds **within a batch**. A finding ID is `<round>-<nn>` (e.g. `R8-01`).
`verdict` is `findings | ready-nits-only | cap-reached`.

### 6.3 Incident row

```csv
# metrics:incident
date,batch,session_id,kind,impact,recovery,prevention
2026-11-10,M0-1,session_...,destructive-git,uncommitted work lost,reflog,PreToolUse deny hook (M0 step 5)
```

Suggested values for `kind`: `destructive-git`, `wrong-branch-push`, `concurrent-push`, `dead-session`,
`stale-state`, `model-fallback`, `unreviewed-merge`, `budget-over`, `guard-bypass`.

### 6.4 Batch summary

When a batch closes, update the batch table in the state body: rounds, findings per round,
total cost, incidents. Then refresh the PR description's review table from the round rows.

## 7. Spawning and collecting work

### 7.1 Spawning

* `create_session` with the prompt template (§8), the tags from §2.1, the model and effort
  from PLAN §9.1, and for writers `outcome_branch` = the branch they hold.
* **Branch lock**: before spawning a writer, set the branch's holder in the state body.
  Only one writer per branch at a time. Reviewers hold no lock and never push.
* At spawn time, schedule a check-in (`send_later`, about 45-60 min for implementers and
  about 30 min for reviewers) and record it in the body.

### 7.2 Review rounds

* The orchestrator gives the reviewer the PR number, `base_sha` (= the branch's
  `reviewed_through`), `head_sha`, the round ID, and the IDs of findings that are still open.
* The reviewer reviews `base_sha..head_sha` only, plus re-checks of open findings, and posts **one**
  PR comment:

  ````
  ## Review R9 (base abc1234 → head def5678)
  ```json
  {"round":"R9","base":"abc1234","head":"def5678","verdict":"findings",
   "findings":[{"id":"R9-01","severity":"major","file":"scripts/guards.sh","line":42,
                "status":"open","summary":"..."}],
   "rechecked":[{"id":"R8-01","status":"fixed"}]}
  ```
  WORKER-RESULT …
  ````
* After the round, the orchestrator sets `reviewed_through = head_sha`.
* Any commit after `reviewed_through` is **unreviewed** until the next round covers it, or until the
  owner explicitly accepts it. That acceptance goes in a `decision` log comment and in the branch row.
  Handoff-only and docs-only commits still count. They are listed, not silently skipped.

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

## 8. Prompt templates

These are the bodies the orchestrator sends. When M0 step 5 creates `agents/prompts/*.md`,
those files become canonical, and this section is replaced with links to them. Placeholders are `{…}`.

### 8.1 Orchestrator bootstrap (successor, or owner-started)

```
You are the Listicles orchestrator for bondo/listicles2. You coordinate only: never edit
files, commit or push. Read docs/ORCHESTRATION.md first, then state issue #{state_issue}
(body, then comments since the last "handover"). Follow §5.2 (incoming checklist) before
doing anything else, then continue from "Next:". Predecessor: {session_id}.
```

### 8.2 Implementer

```
You are an implementer for Listicles (bondo/listicles2), batch {batch}, PR #{pr}.
Branch: {branch}. You are the only writer on this branch; push only to it.
Task: {steps, or the Mx.md section}. Read CLAUDE.md, then handoff/{branch_slug}.md if it exists.
Rules: tests first; run scripts/verify.sh before every push; small commits; never use
git reset --hard, stash, --force or --no-verify; don't touch main or other branches.
At about 50% context: finish the current step, update handoff/{branch_slug}.md (goal, done,
next, decisions, open findings, resume commands), commit, push, and stop.
Refer to owner to-dos by issue number only. Finish with a WORKER-RESULT block
(docs/ORCHESTRATION.md §7.3), as your last message and as a comment on PR #{pr}.
```

### 8.3 Reviewer

```
You are a fresh-context reviewer for Listicles PR #{pr}, round {round}.
Review only {base_sha}..{head_sha} against REVIEW.md, and re-check these open findings:
{open_ids_with_one_line_each}. Don't review unchanged code, don't push, and don't edit files.
Rely on the CI result; run targeted tests only when a finding needs proof.
Post ONE PR comment in the format of docs/ORCHESTRATION.md §7.2 (finding IDs {round}-01…),
ending with a WORKER-RESULT block, and repeat that block as your last message.
```

### 8.4 One-off task (planner, retro, process review)

```
You are a fresh-context {role} for Listicles (bondo/listicles2). Task: {task}.
Inputs: {files/issues}. Push only to {branch}; don't open a PR unless told to.
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
