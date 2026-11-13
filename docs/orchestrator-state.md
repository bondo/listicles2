# Orchestrator state: issue body template

Copy everything below the line into the state issue body (label `orchestrator-state`, created by
owner task M0-O9; until then the issue has no label). Rules: [`ORCHESTRATION.md`](ORCHESTRATION.md) §3.
Only the active orchestrator edits it. **Every field is mandatory**, including `Tasks ref:`: the ready query
(§4.3) reads its ref from that line. Issue #15 predates this template: the orchestrator rewrites its body
into this shape on its first wake and logs a `correction` comment.
History goes into comments (`metrics:*`, `incident`, `PAUSED`/`RESUMED` (§7.7), `decision`, `handover`, `handover-ack`,
`todo-done`, `correction`, `takeover`, `lock-lost`, `handover-released`; deferrals are `decision` comments), not into this body.

---

Living state for the Listicles orchestrator. Process: docs/ORCHESTRATION.md. Do not edit
unless you are the orchestrator named below; comment instead.

**Orchestrator:** `{session_id}` since {UTC} · predecessor `{session_id}` · lineage depth {n}
**Updated:** {UTC}, after {event}
**Inbox since:** {UTC} (collaborator comments and issues are read from here, ORCHESTRATION.md §7.6; only owner comments on #15 become state, §3.2)
**Tasks ref:** `{branch}` (the one ref that carries `docs/tasks.toml`: `claude/orchestration-review` until M0-O8, then `main`)
**Usage:** {ok | near limit (5-hour) | near limit (7-day) | near limit (overage) | paused until HH:MM UTC} (read {UTC} from `rate_limit_info`, ORCHESTRATION.md §7.7.1; the owner reads this line first. Issue #15's older "Current" section carries the same line until the body is rewritten into this shape)

## Now
- Milestone: {Mx}, PR #{n} ({draft/ready}), batch {id}: {one line}
- Waiting on: {worker / owner #issue / CI}

## Next
(From `scripts/tasks.py … ready` for implementer work and `… review` for review rounds, ORCHESTRATION.md §4.3.
Don't pick work any other way. Re-schedule the 45-minute check-in on every wake, §1.1.)
1. {concrete action a cold successor can take}
2. …

## Sessions
| Session | Role | Tags | Branch | Task ids (claims) | Spawned | Expects | Last checked | Status |
|---|---|---|---|---|---|---|---|---|
| `session_…` | implementer | `batch:M0-2 pr:1` | `claude/…` | M0-04,M0-05 | {UTC} | WORKER-RESULT + push | {UTC} | running |

## Branches
| Branch | Holder | Tasks awaiting review/merge (`--in-review`) | reviewed_through | Unreviewed since | Disposition |
|---|---|---|---|---|---|
| `claude/…` | `session_…` / none | M0-04,M0-05 | `abc1234` | `def5678` (handoff only) | owner-accepted ({link}) / next round |

## Owner to-dos (ready owner tasks, `owner-todo` issues)
- {task id} #{n} {title}: then the orchestrator {follow-up}

## Follow-ups
(From `scripts/tasks.py --followups … followups`; rules in FOLLOW-UPS.md.)
- {paste the `open follow-ups: N (blocker …, major …, minor …, nit …)` line}

## Pending task additions (for the next PR that touches docs/tasks.toml)
- {new task, deps, why} / drift: {from `tasks.py drift`}

## Batches
| Batch | Rounds (B/M/m/n per round) | Cost | Incidents |
|---|---|---|---|
| {id} | R5 0/7/6/2 → … | ${x} (source: get_session usage) | {kind} |

## Scheduled tasks and subscriptions
| Trigger / PR | Fires into / held by | Purpose | Next run |
|---|---|---|---|
| `trig_…` | `session_…` | remind: {to-do #n} | {UTC} |
| PR #{n} | `session_…` | review/CI events | n/a |

## Collaborator
- Accident check at the last wake: {clean / hit: what, who, link}; CI-steering labels recorded: {none / list}

## Open questions for the owner
- {question}: options {a} / {b}; recommendation {a}
