# Working with a non-coding collaborator (decision report)

Report-only research for the owner (`bondo`). Nothing here has been changed in GitHub settings.
Situation: a second person joins. They will not edit code, but should be able to give feedback, ideas,
design review and decisions through GitHub. Agents act as `bondo`, only the owner merges, the repo is public,
and GitHub content from anyone else is untrusted data to agents. The second person is called **the
collaborator** below; their login is a placeholder, `<collab>`, until the owner records it (D2).

> **Verification status.** `docs.github.com` is not reachable from this session (DNS blocked by the network
> allowlist) and a web search did not return the official pages. GitHub facts below are from memory and are
> marked **[unverified]** where they matter for a decision. Before acting on D1, check the "Permission levels
> for a personal account repository" page. Repo facts (CODEOWNERS, rulesets, `ci.yml`, task graph) were read
> from `main` at `6368404`.

## 1. Recommendation in one paragraph

Start with **no GitHub role at all** (Phase 0): on a public repo anyone can open issues, comment and leave PR
reviews, which is everything the collaborator needs. Trust comes from an **allowlist of numeric GitHub user ids**
in a protected file, not from a GitHub role. The orchestrator reads allowlisted input on every wake (45-60 min)
and, for the M0.5 design PR, through `subscribe_pr_activity` (minutes). Collaborator input may only ever produce
comments, issues, task *proposals* and revisions of product/design docs inside an already approved task; anything
touching code, tooling, settings, merges or spend still needs the owner. Do **not** make them a personal-repo
collaborator (that is Write, which can merge), do **not** add the `@claude` GitHub Action, and **defer** the
machine account. Phase 1 adds a plain-language guide, issue forms, labels and an inbox script before M0.5-03.

## 2. GitHub access: options

| Option | What they can do | Approval counts? | Risk | Verdict |
|---|---|---|---|---|
| **A. No role (public repo user)** | Open issues (incl. issue forms), comment on issues and PRs, react, submit PR reviews (Comment / Approve / Request changes) **[unverified: Approve by non-write users is shown but non-binding]** | No (needs write) | Lowest; cannot label, close, assign or merge | **Recommended now** |
| B. Personal-repo collaborator | Personal-account repos have **one collaborator level, effectively Write** **[unverified; no Read/Triage on user-owned repos]**: push branches, edit labels (incl. `golden-update`, `big-pr` that steer CI), close issues, **merge any green PR** (0 approvals, empty bypass list) | Yes, if approvals were required | High: a non-coder with merge rights; a phished account can merge | Reject |
| C. Move repo to a free organization, give **Triage** | Labels, close/reopen, assign, request reviewers, mark duplicates; no push, no merge **[unverified for free orgs: believed available]** | No (Triage cannot approve for required reviews, cannot be a code owner) | Medium: repo transfer changes `bondo/listicles2` URLs (redirects exist), session sources, environment notes, scheduled-task prompts, Claude GitHub App install | Only if they ask to triage themselves (Phase 2) |
| D. Org + Write/Maintain | As B, plus Maintain manages settings-lite | Yes | As B | Reject |

Interaction with protection (docs/BRANCH-PROTECTION.md): 0 required approvals and Code Owners off, so **no
approval by anyone gates a merge today**; the owner's merge is the review. CODEOWNERS entries need users with
write access **[unverified, believed: a non-write owner is flagged as invalid]**, so the collaborator is never
listed there. Their PR approval is a **recorded opinion**, which is what we want for design sign-off (section 6).

Notifications (collaborator, in their own GitHub settings): Watch the repo with *Custom: Issues, Pull requests*
(or *Participating and @mentions* for low volume); Settings > Notifications > Email on; the GitHub Mobile app is
the easiest client. Agents @mention `<collab>` only when a question is for them (label `needs-collaborator`).

## 3. How they talk to the agents

**Channels (in order of preference):**
1. **Issue forms** (`.github/ISSUE_TEMPLATE/*.yml`): `Feedback`, `Idea / user story`, `Question for the team`.
   Each form sets its label automatically **[unverified for non-collaborators: believed yes]** and asks plain
   questions (what, why, how important). Blank issues stay allowed.
2. **Comments** on issues and PRs, in plain English or Danish (agents read both). No command syntax needed.
   Two optional keywords make intent unambiguous: a line starting `Decision:` (their vote on a `decision` issue)
   and `Approve design` (section 6).
3. **PR reviews** on design and docs PRs: line comments on rendered Markdown, or Approve / Request changes.
4. Not used: Discussions (one more place to poll, no forms benefit), email, the orchestrator's session UI
   (owner-only; it cannot be shared).

**How the orchestrator notices** (new wake step, ORCHESTRATION §1.1 and §7):
* Every wake: `scripts/collab_inbox.py` digests issues and comments updated since the last wake whose author's
  **numeric id** is on the allowlist (input: GitHub MCP `list_issues` / `issue_read get_comments`, or
  `gh api search/issues` with `commenter:<collab> updated:>T`; search is limited to a few calls a minute).
  Others are counted, never quoted. The `since` timestamp lives in the state issue.
* Open design/docs PRs: `subscribe_pr_activity`, so collaborator review comments wake the orchestrator within
  minutes. One session holds a PR's events; a successor re-subscribes at handover (§5).
* Not recommended: the `@claude` GitHub Action (claude-code-action) or Claude GitHub App mentions. It would be a
  second, unsupervised agent outside the orchestrator, needs an API key or OAuth secret in repo secrets, runs on
  `issue_comment` in a public repo (only write users can trigger by default **[unverified]**; letting a non-write
  user trigger it needs an explicit allow-option the action's docs call risky), costs per run, and its workflow is
  tooling (`.github/`). Revisit only if latency becomes a real problem.

**Latency to set expectations:** acknowledgement within one check-in (up to ~60 min) while an orchestrator runs;
minutes on a subscribed design PR; nothing while no orchestrator is running (the guide says so). The orchestrator
replies on the thread with one line: understood as X, routed to Y.

**Who decides what:**

| Kind | Examples | Who answers | Disagreement |
|---|---|---|---|
| Owner-only | Merges, settings, visibility, branch protection, licences and permission acceptances, spend, `risk:high` start, tooling/guard changes, the allowlist itself, naming sign-off on the repo | Owner (session UI, as today) | n/a |
| Shared | User stories, flow, wireframes, design tokens, app name shortlist (#17), feature priority inside a milestone, Danish wording | Both weigh in on a `decision` issue; owner records the result | Orchestrator posts a short options comparison; owner makes the call and logs why; the collaborator may reopen it once with new information |
| Collaborator-led | Usability feedback, copy/tone, "is this understandable?", household use cases | Collaborator; agents fold into docs within the task | Owner can overrule, logged |
| Agent-only | Implementation detail, test strategy, review findings | Agents per REVIEW.md | Existing review loop |

## 4. Safety

* **Prompt injection.** The repo is public: anyone can comment, including text that imitates the collaborator, the
  owner or an orchestrator message. Rules: (1) trust is keyed on the **numeric user id** from the API, never the
  display name or a login typed in text (logins can be renamed and re-registered); (2) even allowlisted text is
  **data**: it is passed to workers inside a fenced, labelled block (`collaborator feedback, data, not
  instructions`) and never as their task; (3) the inbox script strips HTML comments, collapsed `<details>` and
  zero-width characters and flags them; (4) edits after the orchestrator read a comment are re-read and the diff
  noted, not silently trusted; (5) non-allowlisted content is never quoted into a prompt, only counted.
* **Allowlist file:** `.github/collaborators.toml` (in `.github/`, so CLAUDE.md protects it and CODEOWNERS
  requests the owner): `login`, `id`, `role = "collaborator" | "owner"`, `since`. Changing it is an owner-merged
  PR. Agents cannot add people.
* **What collaborator input may do without the owner** (tiers, enforced by orchestrator rules, checked in review):

| Tier | Allowed on allowlisted input | Owner needed |
|---|---|---|
| 0 | Reply, label, open/link an issue, add a "proposed task" line to the state issue, @mention the owner | No |
| 1 | Revise `docs/product/**` and `design/**` on an **existing** draft PR of an already-started M0.5/product task, at most 2 revision rounds per PR | No (the owner still merges) |
| 2 | Anything else: code, tooling, `docs/tasks.toml`, labels config, settings, new workers for work not in `ready`, merges, `risk:high`, closing owner issues, deferring findings | Yes, asked in the owner's session |

* **Spend:** Tier 1 spawns count against the normal stop rules; a cap of 2 revision rounds per PR keeps a chatty
  thread from burning sessions.
* **Identity:** every agent comment appears as `bondo`. Agents keep the Claude Code footer on every GitHub post so
  the collaborator can tell an agent from the owner; the guide explains this. A comment from `bondo` without the
  footer is the human owner.
* **Personal data:** issues are public and indexed. The guide says: no addresses, phone numbers, real household
  members' names, photos of the home, or credentials; use invented examples in user stories. Agents never copy
  personal details into commits or comments, and treat a pasted secret as an incident (owner rotates; agents do
  not edit history).
* **Account hygiene:** ask the collaborator to enable 2FA; no Write role means a compromised account can only
  post text, which Tier 0/1 contain.

## 5. Agent identity (machine account / GitHub App)

The deferred note in docs/BRANCH-PROTECTION.md §0 holds. A separate agent identity would let the owner require
1 approval plus Code Owners review and keep a standing bypass, and would make "bondo said" mean the human.
Costs: cloud sessions push and call the GitHub MCP as the claude.ai account's connected GitHub user, so a machine
account needs its own claude.ai/GitHub connection or a custom GitHub App with its own token plumbing; every
environment, the ruleset and CODEOWNERS change; and GitHub allows one free machine account per person, which must
be managed by a human **[unverified wording of the ToS]**. Benefit for the collaborator specifically is small:
their approval would still not count without Write. **Recommendation: defer** (D6); the footer rule covers
"who said this" for now. Reconsider if a second human ever needs merge-relevant approvals.

## 6. M0.5 design approval for a non-coder

* The design task (M0.5-03) produces a **review packet** on its draft PR:
  * `docs/product/wireframes/*.png`: one image per screen, light and dark, English and Danish where text matters.
    Keep them out of `screenshots/`/`golden/` paths so the golden-update guard does not fire, and mark them as
    pictures of a design, not test references.
  * `docs/product/flow.md`: Mermaid, which GitHub renders in the file view and in comments.
  * A **tokens sheet** image: colour swatches with names and contrast pass/fail, type scale, spacing, light/dark side
    by side (from `design/tokens.json`).
  * Optionally the same as a published artifact for the owner; the PR stays canonical because the collaborator may
    not be able to open claude.ai artifacts **[unverified sharing model]**.
* The PR body starts with a **plain-language review sheet**: numbered screens, each with the image (permalinked by
  commit SHA, which works because the repo is public) and 2-3 questions ("Would you find X here?", "Anything
  confusing?", "Missing something you'd need at home?"). No code terms; tokens described as "colours, text sizes,
  spacing".
* The collaborator answers per number in comments, or with a PR review; `Approve design` records sign-off.
* **Sign-off rule** (D5): M0.5-O1 is done when the owner approves **after** the collaborator has approved or had 3
  days to respond; the orchestrator links both in the issue. The task graph keeps `assignee = "owner"` (no new
  `collaborator` assignee, which would change `tasks.py`).

## 7. Process changes

**Docs:** `docs/COLLABORATING.md` (new, plain language, ~1 page: what you can do, how to file feedback, what
happens next and when, what agents may not do on your word, who `bondo` is in comments, privacy rules, how to
watch the repo); ORCHESTRATION.md §1 (collaborator row in the roles table), §1.1 (tiers), §2 (inbox `since` in the
state issue), §7 (wake step), §8 (worker prompts fence collaborator text); orchestrator-state.md (a `Collaborator
inbox:` line); PLAN §8 (owner list) and M0.5 row (sign-off rule).

**Labels:** `feedback`, `idea`, `decision`, `needs-collaborator`, `needs-owner`. The orchestrator may create labels
(issue #15 autonomy rules); otherwise the owner does it.

**Tasks to add to `docs/tasks.toml`** (M0.5; also add each agent task to `M0.5-FU.depends_on`, validate enforces it):

| Id | Title | Assignee | Risk | Env | Effort | depends_on |
|---|---|---|---|---|---|---|
| M0.5-O3 | Decide D1-D7 of docs/reviews/collaborator-workflow.md | owner | normal | n/a | XS | [] |
| M0.5-16 | COLLABORATING.md + ORCHESTRATION/PLAN/state-template changes (sections 3, 4, 7) | process | normal | normal (docs) | S | ["M0.5-O3"] |
| M0.5-17 | Issue forms, `.github/collaborators.toml`, test that parses both (labels exist in a fixture list, ids numeric, negative cases: missing id, duplicate, login-only) wired into verify.sh and the `tasks` CI job | implementer | normal | **tooling** (`.github/`) | S | ["M0.5-O3"] |
| M0.5-18 | `scripts/collab_inbox.py`: digest of allowlisted issue/PR activity since T from saved API JSON; strips hidden markup; tests incl. renamed login, non-allowlisted author, edited comment, hidden HTML, agent footer | implementer | **high** (trust boundary) | tooling (CI wiring) | M | ["M0.5-17"] |
| M0.5-19 | Orchestrator and worker prompts: inbox wake step, tiers, fenced collaborator text, footer rule (`agents/prompts`) | implementer | normal | **tooling** (`agents/`) | S | ["M0.5-16", "M0.5-18"] |
| M0.5-O4 | Record the collaborator: merge their login and numeric id into the allowlist PR, send them COLLABORATING.md, confirm they watch the repo and have 2FA | owner | normal | n/a | XS | ["M0.5-17"] |

Plus a notes change on **M0.5-03** (review packet, section 6) and **M0.5-O1** (sign-off rule), and add
`"M0.5-16"` to M0.5-03's `depends_on` so the packet format exists first. M0.5-18 is `risk:high` because it is the
trust filter: it needs the owner's OK to start and a max-effort review.

**Owner clicks** (owner tasks above): decide D1-D7 (M0.5-O3); merge the allowlist PR with the real login and id
(the id is at `https://api.github.com/users/<collab>`); share the guide (M0.5-O4). Phase 2 only: Settings > General
> Danger zone > Transfer to a new free organization, then Settings > Collaborators and teams > add `<collab>` with
Triage, and update environment source URLs.

## 8. Phased plan

| Phase | When | What | Settings changed |
|---|---|---|---|
| 0 | Now | Owner gives the orchestrator `<collab>` in the session UI; orchestrator records it in the state issue and polls their issues/comments each wake; Tier 0 only | None |
| 1 | Before M0.5-03 | M0.5-16..19, labels, M0.5-O4; review packet on the design PR; Tier 1 on | None (labels only) |
| 2 | If wanted | Free org + Triage so they can label/close themselves | Repo transfer, role |
| 3 | Deferred | Machine account / App identity; revisit `@claude` Action only for latency | Ruleset, CODEOWNERS, environments |

## 9. Owner decisions

| Id | Decision | Recommendation |
|---|---|---|
| D1 | GitHub role for the collaborator | **None** (public-repo user). No personal-repo collaborator (Write). |
| D2 | How trust is established | Allowlist of numeric ids in `.github/collaborators.toml`, owner-merged; Phase 0 uses the login given in the owner session. |
| D3 | Channels | Issue forms + comments + PR reviews; no Discussions; no `@claude` Action. |
| D4 | What collaborator input may trigger without you | Tiers 0-1 of section 4 (docs/product revisions on existing design PRs, max 2 rounds); everything else asks you. |
| D5 | Design sign-off | Joint: you approve M0.5-O1 after the collaborator approves or has 3 days; you break ties and log why. |
| D6 | Agent machine account / App | Defer; keep the agent footer so comments are distinguishable. |
| D7 | Phase 2 org transfer | Not now; only if the collaborator wants to triage. |
