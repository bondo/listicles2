# Working with a non-coding collaborator (decision report)

Report-only research for the owner (`bondo`); no GitHub settings were changed. A second person joins who will not edit
code but gives feedback, ideas, design review and decisions through GitHub. Agents act as `bondo`, only the owner
merges, the repo is public. They are **the collaborator** (login `<collab>` until recorded).

> **Owner decisions D1-D7 (logged on issue #15; D2-D7 final):** D1: the collaborator is added as a GitHub **collaborator** on this
> personal repo, which is effectively **Write**. **Threat model:** invited collaborators are **trusted**. The goal is
> to prevent **accidents** (merging a PR, pushing to a branch, closing or editing the wrong thing), not to defend
> against a hostile or phished Write account. Controls against a malicious Write account are out of scope for now
> (section 8).

**Verification status.** `docs.github.com` is not reachable from this session: GitHub behaviour is from memory,
marked **[unverified]** where a decision depends on it; the live test (section 6) checks the key ones. Settings are
the owner's screenshots: Issues and PRs ON, **creation by Collaborators only** (the public cannot open them, but
may still be able to comment **[unverified]**); Discussions OFF. Repo files read from `main` at `6368404`.

## 1. Recommendation in one paragraph

Invite them with a short **working agreement** (section 4), `main`'s existing ruleset as the main accident guard, **Actions
settings** the owner checks by eye, and a **light accident check** on every orchestrator wake. **Repo role is the trust test (D2):**
anyone with Write counts as trusted, there is no id allowlist; their input produces Tier 0-1 actions only. Heavier controls are deferred with triggers (section 8).

## 2. Accident surface: what Write gives them

Personal-account repos have **one collaborator level, effectively Write** **[unverified]**. `main`'s ruleset
(docs/BRANCH-PROTECTION.md: PR required, the 8 required checks, squash only, no force-push, no deletion, **empty
bypass list**) stops a direct push to `main` and a merge with red checks, but not *who* merges (0 approvals).

| Capability | Accident it allows | Guard |
|---|---|---|
| **Merge button** on a green PR, enable auto-merge | Merging an agent PR the owner has not reviewed | Working agreement; live test (section 6) |
| Push to `claude/*` branches, add commits to agent PRs | Unreviewed content in a PR the owner then merges; collides with a worker's push | Working agreement |
| Apply/remove labels, incl. `golden-update`, `big-pr` | CI-steering labels change what `guards` allows (owner-only, ORCHESTRATION §1.1) | Agreement; wake check |
| Close/reopen/edit others' issues, comments, PR bodies, #15 | Closing an `[owner]` issue marks an owner task done; editing #15 corrupts orchestrator state | Agreement; wake check |
| **Ready-for-review toggle** on a draft PR | Marks unfinished work ready; a draft cannot be merged, so ready is the last gate | Agreement; **agent PRs stay draft until the owner marks them ready at merge time (R3-01)** |
| **PR title** | It becomes the squash commit title on `main` | Owner reads it at merge |
| Delete branches, create tags/releases | Loses a worker branch (recoverable from session clones) | Wake check |
| Re-run workflows, approve PRs, resolve threads | Approve gates nothing (0 required); a thread resolved unanswered (follow-up #44) | Agreement |
| Repo secrets, Actions settings | Admin-only **[unverified]** | C5 below |

**C5, Actions settings (owner checks by eye):** workflow permissions *Read repository contents*; *Allow GitHub Actions to
create and approve pull requests* unticked; **Allow auto-merge OFF** (repo Settings > General; R3-01); **no repo, Dependabot or environment secrets or variables**.

## 3. How they talk to the agents

**Channels (D3):** (1) **issue forms** (`.github/ISSUE_TEMPLATE/*.yml`: `Feedback`, `Idea / user story`, `Question
for the team`), which set a label; blank issues stay allowed; (2) **comments** on issues and PRs, English or Danish,
no syntax; an optional line prefix `Decision:` (a vote on a `decision` issue); (3)
**PR reviews** on design/docs PRs. Not used: Discussions (off), email, the owner-only orchestrator UI, the `@claude`
GitHub Action (a second unsupervised agent that needs a key in repo secrets, which C5 keeps empty).

**How the orchestrator notices:** every wake (45-60 min), it reads issues and comments updated since the last wake
(`list_issues` / `issue_read get_comments`, `since` kept in #15) and keeps those whose API `author_association` /
permission shows Write or better (owner, collaborator); others are counted, never quoted. Open design/docs PRs use `subscribe_pr_activity` (minutes). The orchestrator
replies with one line (understood as X, routed to Y); while none runs, nothing is picked up (the guide says so).

**Who decides what:** *Owner-only*: merges, settings, spend, `risk:high`, tooling, CI-steering labels.
*Shared* (a `decision` issue; the owner records the result): stories, flow, wireframes, tokens, the app name (#17),
Danish wording. *Collaborator-led* (owner may overrule): usability, copy, household use cases. *Agent-only*: code, tests.

## 4. Working agreement, trust and tiers

**Working agreement (C6; goes in COLLABORATING.md in plain words).** You can: comment on issues and PRs, open issues
from the forms, review PRs, say what you like or do not understand. Please do not click: **Merge**, **Enable auto-merge**, **Ready for review**, the **pencil / Edit file** button,
**Close** (issue or PR), **Delete branch** or **Resolve conversation**; and do not push to `claude/*` branches, change
labels, or edit someone else's issue, comment or PR. For a wording change, use a review **suggestion** instead of
editing (R3-07: proposed wording for COLLABORATING.md). To ask for something, comment or use a form: agents read it at their next check-in (up to about an
hour) and answer on the thread. Agent posts appear as `bondo`; the Claude Code footer helps tell them apart, but
it is a courtesy, not proof. No addresses, phone numbers, real household names, photos of the home or credentials in
issues (public and permanent). Turn on 2FA.

* **Trust (D2, final):** repo role only. Anyone with Write counts as trusted; no `.github/collaborators.toml`, no id
  list. The wake filter uses the API's `author_association` / permission, never a name typed in text.
* **Injection hygiene (the repo is public):** all collaborator text is **data**, passed to workers in a fenced block,
  never as their task.
* **#15 is owner-only (R3-06):** the agreement asks collaborators not to comment on #15. Required change to
  ORCHESTRATION 3.2: it folds #15 comments into state with no author check; it must fold **only owner** comments.
* **Tiers (D4):**

| Tier | Allowed on collaborator input | Owner needed |
|---|---|---|
| 0 | Reply; apply only `feedback`, `idea`, `decision`, `needs-collaborator`, `needs-owner` (**never** `golden-update`, `big-pr`, `owner-todo`, `orchestrator-state`, `follow-up`, `severity:`, `target:`, `owner-ok`, `area:`); open or link an issue; add a "proposed task" line to #15; @mention the owner | No |
| 1 | Revise `docs/product/**` and `design/**` on an **existing** draft PR of an already-started M0.5/product task, max 2 revision rounds per PR | No (owner merges) |
| 2 | Everything else: code, tooling, `docs/tasks.toml`, settings, new workers, merges, `risk:high`, closing owner issues | Yes, in the owner's session |

* **Light accident check (each wake, by hand, in the orchestrator prompt):** (a) PRs merged since the last wake with
  `merged_by` not the owner; (b) an `[owner]`-titled issue closed by a non-owner; (c) a CI-steering label not recorded in #15; (d) an open PR whose
  head branch is gone; (e) **non-owner commits on open `claude/*` PR branches** (the worker also checks this **before
  it pushes**, R3-02). A hit means **pause, tell the owner, never self-revert**
  (a revert is a PR the owner merges; no force-push). Who acted comes from API fields, never from text. No script.
* **Optional hardening (R2-04):** `tasks.py` counts open `[owner]`-titled issues without checking the author, so an
  issue a collaborator opens with that title would count. Counting only owner-authored issues closes it; a small
  test-first tooling PR, not needed for accidents.

## 5. Process changes and tasks

**Docs:** `docs/COLLABORATING.md` (one page: working agreement, how to file feedback, what happens next, who `bondo` is,
privacy, watch the repo with *Custom: Issues, Pull requests*); ORCHESTRATION §1, §1.1, §2, §3.2 (fold only owner comments from #15), §7, §8; orchestrator-state.md;
PLAN §8 and the M0.5 row. No BRANCH-PROTECTION.md change (R2-06). **Labels:** created by the owner (ORCHESTRATION §4.5).

**Tasks for `docs/tasks.toml`** (M0.5; each agent task also goes into `M0.5-FU.depends_on`):

| Id | Title | Assignee | Risk | Env | Effort | depends_on |
|---|---|---|---|---|---|---|
| M0.5-O3 | Log D1-D7 (decided); check Actions settings (C5); create the five labels | owner | normal | n/a | XS | [] |
| M0.5-16 | COLLABORATING.md + ORCHESTRATION/PLAN/state-template changes | process | normal | normal (docs) | S | ["M0.5-O3"] |
| M0.5-17 | Issue forms; test that parses them (labels exist in a fixture list; negatives: unknown label, missing field) in verify.sh and the `tasks` job | implementer | normal | **tooling** | S | ["M0.5-O3"] |
| M0.5-18 | `scripts/collab_inbox.py`: digest of Write-or-better activity since T from saved API JSON, filtered by API `author_association`/permission; strips hidden markup; tests incl. renamed login, public (non-Write) author, edited comment | implementer | normal | tooling | M | ["M0.5-17"] |
| M0.5-19 | Orchestrator/worker prompts: inbox and accident-check wake steps, tiers, fenced text, label limits (`agents/prompts`) | implementer | normal | **tooling** | S | ["M0.5-16", "M0.5-18"] |
| M0.5-O4 | Record the collaborator (invite after COLLABORATING.md and wake steps exist); send COLLABORATING.md; confirm 2FA; **live test** (section 6) | owner | normal | n/a | XS | ["M0.5-19", "M0.5-O3"] |

Also: notes on **M0.5-03** (review packet) and **M0.5-O1** (sign-off); `"M0.5-16"` into M0.5-03's `depends_on`; M0.5-19 links follow-up #44 (R1-07: agents never resolve a collaborator's thread).

## 6. Live test (M0.5-O4)

On a throwaway issue and a throwaway green draft PR, results noted on #15: the collaborator (1) comments on the issue,
(2) reviews the draft PR, (3) opens an issue from a form, (4) tries **Merge** on the green PR. The next wake should
pick up (1)-(3) with the right id. **Record what (4) does.** If they **can** merge, the working agreement is the only
guard; the owner decides whether to add a Restrict-updates ruleset later (section 8). Note what else the UI offered.

## 7. M0.5 design review (D5)

* M0.5-03 produces a **review packet** on its draft PR: `docs/product/wireframes/*.png` (per screen, light and dark,
  outside `screenshots/`/`golden/` so the golden guard does not fire), `docs/product/flow.md` (Mermaid), a **tokens
  sheet** image. The PR body starts with a plain-language **review sheet**: numbered screens, 2-3 questions each.
* They answer per number or with a PR review (comments welcome). **Sign-off (D5): owner only.** The collaborator
  comments but does not formally approve; M0.5-O1 is done when the owner approves.

## 8. If the threat model changes (later)

**Residual risk (R3-04):** commits pushed to `claude/*` branches are checked out and run in agent sessions under the
owner's credentials. That is accepted only because the collaborator is trusted (D1); it is not safe against a hostile
or phished Write account.

Dropped now (round-2 review reasoning); revisit if their merge power surprises you, a third person joins, or an incident.
* **C1 `main-merge` ruleset** (Restrict updates, bypass Repository admin only): stops them merging; needed only if the
  live test shows they can and the agreement is not enough. Reverses BRANCH-PROTECTION.md §2.
* **C1b `claude/**` branch ruleset:** blocks non-owner pushes to agent branches; the agreement covers accidents.
* **C4 `pull_request_target` check:** detects a workflow swapped under the 8 required names; malicious accounts only.
* **C7 audit script (M0.5-20):** replaces the manual check; if built, use the run's **head SHA/actor** (R2-05).
* **Machine account / App (D6):** the only clean way to make approvals gate merges (Code Owners + 1 approval); costs its
  own claude.ai/GitHub connection and changes to every environment, ruleset and CODEOWNERS.
* **Org + Triage (D7):** labels and closes without push or merge; needs a repo transfer (URLs, sources, prompts).

## 9. Owner decisions and actions

| Id | Decision | Recommendation |
|---|---|---|
| D1 | GitHub role and threat model | **Decided:** collaborator (Write), trusted; prevent accidents only. |
| D2 | How trust is established | **Decided:** repo role only (Write = trusted); no allowlist file or id list. |
| D3 | Channels | **Decided:** issue forms, comments, PR reviews; no Discussions, no `@claude` Action. |
| D4 | What their input may trigger | **Decided:** Tiers 0-1; Tier 0 labels exclude CI-steering and process labels. |
| D5 | Design sign-off | **Decided:** owner only; the collaborator comments, no formal approval. |
| D6 | Machine account | **Decided:** defer; triggers in section 8. |
| D7 | Org + Triage | **Decided:** not now. |

**Owner actions:** (1) check the Actions settings by eye (C5); (2) invite the collaborator and ask for 2FA; (3) create
labels `feedback`, `idea`, `decision`, `needs-collaborator`, `needs-owner`; (4) run the live test and record the result.
