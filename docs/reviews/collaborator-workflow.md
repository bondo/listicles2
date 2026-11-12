# Working with a non-coding collaborator (decision report)

Report-only research for the owner (`bondo`). Nothing here has been changed in GitHub settings.
Situation: a second person joins. They will not edit code, but give feedback, ideas, design review and decisions
through GitHub. Agents act as `bondo`, only the owner merges, the repo is public, and GitHub content from anyone else
is untrusted data to agents. The second person is **the collaborator**; their login is `<collab>` until recorded.

> **Owner decision D1 (made in the orchestrator session, to be logged on issue #15):** the collaborator is added as a
> GitHub **collaborator** on this personal repo, which is effectively **Write**. The owner chose this over the round-1
> recommendation (no role). This revision assumes D1 and adds compensating controls (section 5).
>
> **Verification status.** `docs.github.com` is not reachable from this session (proxy 403), so GitHub behaviour
> below is from memory and marked **[unverified]** where a decision depends on it; M0.5-O4 tests the important ones
> live. Repo settings are the owner's screenshots: Issues and Pull requests ON, both **creation allowed by
> Collaborators only**; Discussions, Wikis, Sponsorships, commit comments, web sign-off OFF; Projects ON; **Preserve
> this repository** ON. Repo files (CODEOWNERS, `ci.yml`, BRANCH-PROTECTION.md, tasks) were read from `main` at
> `6368404`.

## 1. Recommendation in one paragraph

Invite the collaborator only together with a **minimal control set** (section 5.2): a second ruleset `main-merge`
with *Restrict updates* whose only bypass is the Repository admin role, so the collaborator cannot merge while the
existing `main` ruleset (empty bypass, required checks) stays as designed; Actions workflow permissions read-only with
no repo secrets; a written **social contract** (they comment, open issues and review; they never push, merge, label,
close or edit others' posts); and an **audit step on every orchestrator wake** that detects merges, closes, label
changes and CI runs by anyone but the owner. Trust in their words comes from their **numeric user id**, read from
`.github/collaborators.toml` **on `main`** and cross-checked against the repo collaborator list. Their input may only
produce Tier 0-1 actions (section 4). Machine account and org move stay deferred, with explicit triggers (D6, D7).

## 2. What Write gives them (and what it gives an attacker who phishes them)

Personal-account repos have **one collaborator level, effectively Write** **[unverified: no Read/Triage on user-owned
repos]**. With the owner's design (0 approvals, Code Owners off, empty bypass), Write means they can:

| Capability | Why it matters here |
|---|---|
| **Merge any green PR**, enable auto-merge | Nothing in `main` ruleset gates *who* merges. Includes a PR whose `ci.yml` is replaced by trivial jobs under the 8 required names: `pull_request` runs the PR head's workflow, and the "GitHub Actions" source only proves Actions ran it. |
| Push branches, add commits to agent PR branches | Content the owner later merges may not be agent-written; a new workflow on a branch runs with a `GITHUB_TOKEN` (can request write scopes on same-repo branches **[unverified]**). No escalation beyond Write while no secrets exist. |
| Secrets, Actions settings | Repo secrets need admin on personal repos **[unverified]**. `ci.yml` uses no `secrets.*` and sets `permissions: contents: read` (verified); whether any repo secret exists needs the owner to check. |
| Apply/remove labels incl. `golden-update`, `big-pr` | These steer CI (ORCHESTRATION §1.1: only the owner applies them). `golden-update` lets changed screenshot references pass `guards`. |
| Edit/hide comments and issue bodies (**#15 state issue**, owner-todo issues); delete issues **[unverified: believed admin-only]** | #15 holds the orchestrator lease and next steps; an edited body could steer agents. |
| Close/reopen issues and PRs | Closing an `owner-todo` issue marks an owner task done for `tasks.py`. |
| Delete branches, dispatch/re-run/cancel workflows | Worker branches are recoverable from session clones; `ci.yml` has no `workflow_dispatch` (verified). |
| Approve PRs, resolve review threads | No effect with 0 approvals; resolving threads bypasses *conversation resolution* (deferred, R1-07). |

## 3. How they talk to the agents

**Channels:** (1) **issue forms** (`.github/ISSUE_TEMPLATE/*.yml`: `Feedback`, `Idea / user story`, `Question for
the team`), which they can now use because creation is limited to collaborators and they are one; forms set labels
for Write users **[unverified]**; blank issues stay allowed; (2) **comments** on issues and PRs, English or Danish,
no command syntax; optional line prefixes `Decision:` (a vote on a `decision` issue) and `Approve design` (section 6);
(3) **PR reviews** on design/docs PRs (line comments on rendered Markdown, Approve / Request changes).
Not used: Discussions (off), Projects (on, but no MCP tools to read it), email, the owner-only orchestrator UI, and
the `@claude` GitHub Action (a second unsupervised agent, needs a key in repo secrets, which section 5 keeps empty).

Because issue and PR creation is collaborators-only, **the public can no longer open issues or PRs**; they can still
comment on existing ones **[unverified]**, so the injection rules in section 4 still apply.

**How the orchestrator notices:** every wake, `scripts/collab_inbox.py` digests issues and comments updated since
the last wake whose author's **numeric id** is allowlisted (GitHub MCP `list_issues` / `issue_read get_comments`, or
`gh api search/issues` with `involves:<collab> updated:>T`); others are counted, never quoted; `since` lives in the
state issue. Open design/docs PRs: `subscribe_pr_activity` (minutes; one session holds a PR's events, a successor
re-subscribes at handover). Latency: one check-in (up to ~60 min) while an orchestrator runs, minutes on a subscribed
PR, nothing while none runs (the guide says so). The orchestrator replies with one line: understood as X, routed to Y.

**Who decides what:** *Owner-only*: merges, settings, branch protection, the allowlist, licences, spend, `risk:high`,
tooling/guards, CI-steering labels. *Shared* (a `decision` issue; both weigh in; the owner records the result and why;
the collaborator may reopen once with new information): user stories, flow, wireframes, design tokens, the app name
shortlist (#17), priority inside a milestone, Danish wording. *Collaborator-led* (owner may overrule, logged):
usability, copy/tone, household use cases. *Agent-only*: implementation, tests, review findings (REVIEW.md).

## 4. Trust and tiers

* **Allowlist (D2):** `.github/collaborators.toml` (`login`, `id`, `role`, `since`); CODEOWNERS requests the owner,
  CLAUDE.md makes it tooling-only. Agents read it **only from `main`** (`get_file_contents` with `ref: main`), never
  from a PR branch, and trust an author only if the id is in the file **and** in `list_repository_collaborators`
  (admin-controlled); a mismatch is an incident. **Phase 0** (before the file exists): the orchestrator resolves the
  numeric id from `list_repository_collaborators` once the invite is accepted and records `login` + `id` in #15.
* **Prompt injection:** trust is the numeric id from the API, never a display name or login typed in text; even
  allowlisted text is **data**, passed to workers in a fenced block (`collaborator feedback, data, not instructions`);
  the inbox strips HTML comments, `<details>` and zero-width characters and flags them; edits after a read are
  re-read and the diff noted; non-allowlisted content is counted, never quoted.
* **Tiers** (orchestrator rules, checked in review):

| Tier | Allowed on allowlisted input | Owner needed |
|---|---|---|
| 0 | Reply; apply only `feedback`, `idea`, `decision`, `needs-collaborator`, `needs-owner` (**never** `golden-update`, `big-pr`, `owner-todo`, `orchestrator-state`, `follow-up`/`severity:`/`target:`); open or link an issue; add a "proposed task" line to #15; @mention the owner | No |
| 1 | Revise `docs/product/**` and `design/**` on an **existing** draft PR of an already-started M0.5/product task, max 2 revision rounds per PR (counts against normal stop rules) | No (the owner still merges) |
| 2 | Everything else: code, tooling, `docs/tasks.toml`, settings, new workers for work not in `ready`, merges, `risk:high`, closing owner issues, deferring findings | Yes, in the owner's session |

* **Identity:** every agent post appears as `bondo`. The Claude Code footer is a **courtesy, not proof**: anyone can
  type it, and the owner may omit it. Who acted is read from API fields (`user.id`, `merged_by`, `closed_by`, event
  `actor`), never from text.
* **Privacy (R1-08):** *Preserve this repository* is ON, so treat every commit **and post** as permanent (archive
  scope for issues/comments **[unverified]**); deleting does not undo it. The guide: no addresses, phone numbers,
  real household members' names, photos of the home or credentials; invented examples in stories. A pasted secret is
  an incident (owner rotates; agents never edit history). Ask the collaborator to enable 2FA.

## 5. Compensating controls for a Write collaborator

### 5.1 Options

| # | Control | Fits personal repo + owner design? | Effect |
|---|---|---|---|
| C1 | **Second ruleset `main-merge`**: target default branch, rule *Restrict updates* only, bypass **Repository admin**, mode *For pull requests only*. Bypass is per ruleset, so `main` (empty bypass, checks) still binds the owner **[unverified: rulesets aggregate; admin role offered as bypass on personal repos; owner merge box stays normal]** | Yes; reverses BRANCH-PROTECTION.md §2 "leave off Restrict updates" for this one ruleset | The collaborator (and a phished account) **cannot merge**; agents can no more and no less than today (same identity) |
| C2 | Required approvals / **Code Owners review** on protected paths (`.github/`, `scripts/guards.sh`, `scripts/hooks/`, CODEOWNERS, `collaborators.toml`, BRANCH-PROTECTION.md) | **No.** Agent PRs are authored by `bondo`, who cannot approve their own PR, and `bondo` is the only code owner: every tooling PR would block. 1 approval without Code Owners makes the non-coder the gate for every agent PR. A bypass for `bondo` is a bypass for agents (§0) | Unworkable until a machine account exists (C8) |
| C3 | **Push ruleset / file-path restriction** (*Restrict file paths*) | Believed org-only (Team/Enterprise) or private-only **[unverified]** | Would stop their pushes to `.github/` on any branch; not available, and C1 covers merge |
| C4 | **Tamper-evident checks**: a `pull_request_target` job (runs the **base** workflow, no PR checkout) that fails when a PR touches `.github/workflows/` or the protected paths and the last push or an `owner-ok` label came from a non-owner `actor` | Possible; tooling work. A same-named job in the PR's `ci.yml` could also report **[unverified how duplicate names resolve]**; org-only *required workflows* would fix that | Tamper-evident, not tamper-proof; low value once C1 holds |
| C5 | **Actions settings**: workflow permissions *Read repository contents*; untick *Allow GitHub Actions to create and approve pull requests*; fork PRs *Require approval for all external contributors*; **no repo secrets or environments** (owner confirms the list is empty); later *Allow select actions* | Yes | No secret to steal; a branch workflow gains nothing Write lacks |
| C6 | **Social contract** in COLLABORATING.md, agreed before the invite: web UI only; comment, open issues, review; never push, merge, label, close, resolve threads or edit others' posts | Yes | Sets expectations; detection (C7) checks it |
| C7 | **Audit on every wake** (`scripts/collab_audit.py`): PRs merged since T with `merged_by.id` != owner; `owner-todo` issues closed by a non-owner (`closed_by`); label events on CI-steering labels by a non-owner `actor`; CI runs on open PR heads with `triggering_actor` != owner (a push by someone else; commit author is spoofable, the run actor is not **[unverified]**); #15 body differing from what the orchestrator last wrote; collaborator list != allowlist | Yes | Detects what C1/C6 miss |
| C8 | **Machine account** for agents (D6) | Yes, at a cost (section 5.3) | Makes C2 workable: Code Owners `@bondo` on `*` + 1 approval, standing bypass for `bondo` only |
| C9 | **Org move + Triage** (D7) | Repo transfer | Triage labels/closes but cannot push or merge; bypasses the issue-creation restriction per the 2026-08-03 changelog (**[unverified]**, seen only as a search extract) |

**On a hit from C7** the orchestrator stops spawning (a merged change to `scripts/hooks/` or `install-hooks.sh` would
run in every new session), logs an incident row, reopens a wrongly closed `owner-todo` issue, removes a non-owner
CI-steering label from an open PR, and asks the owner. It never reverts on its own: a revert is a PR the owner
merges; no force-push, no history edits. The owner decides whether to remove the collaborator.

### 5.2 Minimal viable set

* **Now (before or in the same sitting as the invite):** C1, C5, C6, plus C7 done by hand each wake in Phase 0
  (`list_pull_requests` closed + `pull_request_read` for `merged_by`, issue events for owner-todo closes). CODEOWNERS
  gains `/docs/BRANCH-PROTECTION.md` (M0.5-17).
* **Later:** C7 as a tested script (M0.5-20); C8 when a trigger in D6 fires; C4 only if C1 proves unavailable; C9 only
  per D7.

### 5.3 Machine account, honestly

With a separate agent identity, agent PRs have another author, so the owner can approve them: Code Owners `@bondo`
on everything + 1 approval blocks the collaborator from merging anything the owner has not approved, and the owner's
standing bypass stops being an agent bypass. Costs: cloud sessions push and call the GitHub MCP as the claude.ai
account's connected GitHub user, so the machine account needs its own claude.ai/GitHub connection or a custom App
with token plumbing; every environment, both rulesets and CODEOWNERS change; GitHub allows one free machine account
per person, managed by a human **[unverified ToS wording]**. It becomes worth it when C1 fails its live test, when the
owner wants approvals to gate merges, after any C7 incident, or when a third person joins.

## 6. M0.5 design approval for a non-coder

* M0.5-03 produces a **review packet** on its draft PR: `docs/product/wireframes/*.png` (one per screen, light and
  dark, EN and DA where text matters; outside `screenshots/`/`golden/` so the golden guard does not fire, marked as
  design pictures, not test references); `docs/product/flow.md` (Mermaid renders on GitHub); a **tokens sheet** image
  (swatches with names and contrast pass/fail, type scale, spacing, light/dark) from `design/tokens.json`; optionally
  an artifact for the owner, the PR staying canonical **[unverified artifact sharing]**.
* The PR body starts with a **plain-language review sheet**: numbered screens, each image permalinked by commit SHA
  (public repo), 2-3 questions each ("Would you find X here?", "Anything confusing?", "Missing something at home?").
* The collaborator answers per number, or with a PR review; `Approve design` (or a GitHub Approve) records sign-off.
  Their Approve is now a Write approval but still gates nothing (0 required); it is a recorded opinion.
* **Sign-off rule (D5):** M0.5-O1 is done when the owner approves **after** the collaborator approved or had 3 days;
  the orchestrator links both. `assignee = "owner"` stays (no new assignee, no `tasks.py` change).
* **Deferred (R1-07, follow-up note):** with conversation resolution required, the collaborator's open threads block a
  merge, but they and agents can resolve threads. Rule to add later: agents never resolve a collaborator's thread;
  C7 may check who resolved.

## 7. Process changes and tasks

**Docs:** `docs/COLLABORATING.md` (plain language, ~1 page: what you can do, the social contract, how to file
feedback, what happens next and when, what agents may not do on your word, who `bondo` is, privacy and permanence,
how to watch the repo: *Custom: Issues, Pull requests*, email on, GitHub Mobile); ORCHESTRATION §1 (roles row),
§1.1 (tiers, CI-steering labels), §2 (inbox `since`, last #15 body hash), §7 (inbox and audit wake steps), §8 (fenced
collaborator text); orchestrator-state.md (`Collaborator inbox:` line); BRANCH-PROTECTION.md (C1, C5, live test);
PLAN §8 and the M0.5 row. **Labels** `feedback`, `idea`, `decision`, `needs-collaborator`, `needs-owner`: created by
the owner (agents' GitHub tools cannot create labels, ORCHESTRATION §4.5).

**Tasks for `docs/tasks.toml`** (M0.5; each agent task also goes into `M0.5-FU.depends_on`):

| Id | Title | Assignee | Risk | Env | Effort | depends_on |
|---|---|---|---|---|---|---|
| M0.5-O3 | Log D1; decide D2-D7; apply C1 + C5 (section 5.2), confirm no repo secrets | owner | normal | n/a | XS | [] |
| M0.5-16 | COLLABORATING.md (incl. social contract) + ORCHESTRATION/PLAN/state-template/BRANCH-PROTECTION changes | process | normal | normal (docs) | S | ["M0.5-O3"] |
| M0.5-17 | Issue forms, `.github/collaborators.toml`, CODEOWNERS `/docs/BRANCH-PROTECTION.md`; test parsing both (labels in a fixture list, ids numeric; negatives: missing id, duplicate, login-only) in verify.sh and the `tasks` job | implementer | normal | **tooling** | S | ["M0.5-O3"] |
| M0.5-18 | `scripts/collab_inbox.py`: digest since T from saved API JSON; allowlist from `main` only, cross-checked with the collaborator list; strips hidden markup; tests incl. renamed login, non-allowlisted author, id in file but not a collaborator, edited comment, hidden HTML, typed footer | implementer | **high** (trust boundary) | tooling | M | ["M0.5-17"] |
| M0.5-19 | Orchestrator/worker prompts: inbox and audit wake steps, tiers, fenced text, label limits, footer-is-not-proof (`agents/prompts`) | implementer | normal | **tooling** | S | ["M0.5-16", "M0.5-18", "M0.5-20"] |
| M0.5-20 | `scripts/collab_audit.py` (C7) from saved API JSON; tests incl. merge by non-owner, owner-todo closed by non-owner, `golden-update` added by non-owner, CI run by non-owner actor, #15 body changed, allowlist vs collaborator list; negatives: all-owner activity passes | implementer | normal | tooling | S | ["M0.5-17"] |
| M0.5-O4 | Record the collaborator (login + id into the allowlist PR); send COLLABORATING.md; confirm watch + 2FA; **live test** (below) | owner | normal | n/a | XS | ["M0.5-17", "M0.5-O3"] |

**M0.5-O4 live test** (R1-05), on a throwaway issue and a throwaway green draft PR, results noted on #15: the
collaborator comments on the issue and leaves a review (expect: both work, the orchestrator's next wake picks them up
with the right id); opens an issue from a form (expect: label applied); tries **Merge** on the green PR (expect:
blocked by `main-merge`; if it merges, C1 failed: revert by owner PR, trigger D6); the owner then merges a green PR
normally (expect: no bypass prompt, checks still required). The owner records what else the UI offered them
(labels, close, re-run) to correct section 2.

Also: notes on **M0.5-03** (review packet) and **M0.5-O1** (sign-off rule); `"M0.5-16"` into M0.5-03's `depends_on`.
M0.5-18 is `risk:high`: owner OK to start, max-effort review.

## 8. Phased plan

| Phase | When | What | Settings changed |
|---|---|---|---|
| 0 | Now | M0.5-O3 (C1, C5); invite; orchestrator resolves the id via `list_repository_collaborators`, records it in #15, polls their issues/comments and runs C7 by hand each wake; Tier 0 only | C1 ruleset, Actions settings, collaborator invite |
| 1 | Before M0.5-03 | M0.5-16..20, labels, M0.5-O4 incl. live test; review packet on the design PR; Tier 1 on | Labels |
| 2 | On a D6/D7 trigger | Machine account (C8) or org + Triage (C9) | Rulesets, CODEOWNERS, environments or repo transfer |

## 9. Owner decisions

| Id | Decision | Recommendation |
|---|---|---|
| D1 | GitHub role | **Decided: collaborator (Write).** Log on #15 with the minimal set of 5.2 as its condition. |
| D2 | How trust is established | Numeric id in `.github/collaborators.toml` read only from `main`, and present in the repo collaborator list; Phase 0 id resolved by the orchestrator via the API. |
| D3 | Channels | Issue forms (they can create issues; the public cannot), comments, PR reviews; no Discussions, no Projects channel, no `@claude` Action. |
| D4 | What their input may trigger | Tiers 0-1 (section 4); Tier 0 labels exclude CI-steering and process labels. |
| D5 | Design sign-off | Joint: you approve M0.5-O1 after the collaborator approves or has 3 days; you break ties and log why. |
| D6 | Machine account | Still defer, but no longer "small benefit": it is the only clean way to make approvals gate merges. Do it if C1 fails the live test, you want approvals, after a C7 incident, or a third person joins. |
| D7 | Org move | Not now. Revisit only if C1 is unavailable and a machine account is too costly: Triage gives them what they need without merge (changelog claim unverified). |
