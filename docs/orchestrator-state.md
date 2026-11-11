# Orchestrator state: issue body template

Copy everything below the line into the state issue body (label `orchestrator-state`).
Rules: [`ORCHESTRATION.md`](ORCHESTRATION.md) §3. Only the active orchestrator edits it.
History goes into comments (`metrics:*`, `incident`, `decision`, `handover`, `handover-ack`,
`todo-done`, `correction`; deferrals are `decision` comments), not into this body.

---

Living state for the Listicles orchestrator. Process: docs/ORCHESTRATION.md. Do not edit
unless you are the orchestrator named below; comment instead.

**Orchestrator:** `{session_id}` since {UTC} · predecessor `{session_id}` · lineage depth {n}
**Updated:** {UTC}, after {event}
**Tasks ref:** `{branch}` (`docs/tasks.toml`; `main` once M0 is merged)

## Now
- Milestone: {Mx}, PR #{n} ({draft/ready}), batch {id}: {one line}
- Waiting on: {worker / owner #issue / CI}

## Next
(From `scripts/tasks.py … ready`, ORCHESTRATION.md §4.3. Don't pick work any other way.)
1. {concrete action a cold successor can take}
2. …

## Sessions
| Session | Role | Tags | Branch | Task ids (claims) | Spawned | Expects | Last checked | Status |
|---|---|---|---|---|---|---|---|---|
| `session_…` | implementer | `batch:M0-2 pr:1` | `claude/…` | M0-04,M0-05 | {UTC} | WORKER-RESULT + push | {UTC} | running |

## Branches
| Branch | Holder | reviewed_through | Unreviewed since | Disposition |
|---|---|---|---|---|
| `claude/…` | `session_…` / none | `abc1234` | `def5678` (handoff only) | owner-accepted ({link}) / next round |

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

## Open questions for the owner
- {question}: options {a} / {b}; recommendation {a}
