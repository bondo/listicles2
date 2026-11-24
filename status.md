# Tally status detail

Milestones, their tasks, what each open task waits on, and every blocker, generated from `docs/tasks.toml` and the open PRs and issues. The picture on the front page (`status.svg`) shows the same state. Status words: **done**, **ready** (all dependencies met), **in progress** (an open PR names the task), **blocked** (unmet dependencies or a `blocked` label), **owner to-do** (needs the owner).

## Overview

| Milestone | Name | Done | Open |
|---|---|---|---|
| M0 | Foundation and process | 28/28 (100%) | 0 |
| M0.5 | Product design and guardrails | 35/35 (100%) | 0 |
| M1 | Accounts and households | 82/113 (72%) | 31 |
| M2 | Inventory lists | 0/2 (0%) | 2 |
| M3 | Packing rules (domain) | 0/3 (0%) | 3 |
| M4 | Packing templates and trips | not planned yet | 0 |
| M5 | Barcode scanning | not planned yet | 0 |
| M6 | Release | 0/4 (0%) | 4 |

## M0 Foundation and process

Gradle skeleton, CI, hooks, review loop and agent setup, proven green on a hello-world app.

**Progress:** 28/28 done (100%), 0 open.

### Tasks

| Task | Title | Status | Depends on | Who | PR |
|---|---|---|---|---|---|
| M0-01 | Implementation plan (docs/PLAN.md), 4 review rounds | done | none | planner | [#1](https://github.com/bondo/tally/issues/1) |
| M0-02 | Gradle skeleton, version catalog, spotless/detekt/lint/Kover | done | M0-01 | implementer | [#1](https://github.com/bondo/tally/issues/1) |
| M0-03 | Batch 1&#58; verify/guards/hooks, Firebase emulator + deny tests, CI, Dependabot, PR template, CODEO… | done | M0-02 | implementer | [#1](https://github.com/bondo/tally/issues/1) |
| M0-04 | REVIEW.md and CLAUDE.md | done | M0-03 | implementer | [#1](https://github.com/bondo/tally/issues/1) |
| M0-05 | Agent setup&#58; roles.yaml, prompts, .claude settings and hooks, status line, handoff template, me… | done | M0-03 | implementer | [#1](https://github.com/bondo/tally/issues/1) |
| M0-06 | detekt 2.x vs 1.23 ADR, Kover on &#58;app, dark theme | done | M0-03 | implementer | [#1](https://github.com/bondo/tally/issues/1) |
| M0-07 | Prove the gates&#58; CI green on GitHub, a deliberately broken commit fails CI, then revert | done | M0-04, M0-05, M0-06, M0-O1 | implementer | [#1](https://github.com/bondo/tally/issues/1) |
| M0-08 | Branch-protection guide for the owner | done | M0-03 | implementer | [#34](https://github.com/bondo/tally/issues/34) |
| M0-09 | Orchestration process&#58; docs/ORCHESTRATION.md, state template, task graph + scripts/tasks.py | done | none | process | [#16](https://github.com/bondo/tally/issues/16) |
| M0-10 | Tooling session A&#58; run tasks.py and its tests in CI and verify.sh; CODEOWNERS for the process docs | done | none | implementer | [#35](https://github.com/bondo/tally/issues/35) |
| M0-11 | Tooling session B&#58; align REVIEW.md, CLAUDE.md, agents/prompts, handoff template with ORCHESTR… | done | M0-04, M0-05, M0-10, M0-12 | implementer | [#80](https://github.com/bondo/tally/issues/80) |
| M0-12 | Follow-ups process&#58; docs/FOLLOW-UPS.md, tasks.py follow-up counts and burn-down checks | done | none | process | [#16](https://github.com/bondo/tally/issues/16) |
| M0-13 | Process and tooling review (#20)&#58; written review in docs/, prioritised proposals with effort an… | done | none | process | [#33](https://github.com/bondo/tally/issues/33) |
| M0-14 | Turn the proposals the owner adopts (M0-O11) into PR-sized tasks with dependencies; open follow… | done | M0-13, M0-O11 | planner | [#37](https://github.com/bondo/tally/issues/37) |
| M0-15 | Lower the big-pr diff cap in ci.yml from 6000 to 1500 (D2) | done | M0-O11 | implementer | [#36](https://github.com/bondo/tally/issues/36) |
| M0-16 | Close follow-ups #21-#26 as by-design once branch protection is confirmed on (D1) | done | M0-O6 | process |  |
| M0-FU | Follow-up burn-down for M0 (close or re-defer each open follow-up targeting M0) | done | M0-01, M0-02, M0-03, M0-04, M0-05, M0-06, M0-07, M0-08, M0-09, M0-10, M0-11, M0-12, M0-13, M0-14, M0-15, M0-16 | implementer |  |
| M0-O1 | Add the big-pr label to PR #1 | done | none | owner |  |
| M0-O2 | Set the default branch to main | done | none | owner |  |
| M0-O3 | Make the repository public | done | none | owner |  |
| M0-O4 | Confirm the CODEOWNERS handle | done | M0-03 | owner |  |
| M0-O5 | Decide how the orchestration branch lands (merge into the PR #1 branch or a separate PR) | done | none | owner |  |
| M0-O6 | Turn on branch protection for main using the guide | done | M0-08, M0-O2 | owner |  |
| M0-O10 | Create the follow-up labels (follow-up, severity&#58;*, target&#58;*, area&#58;*, owner-ok) | done | none | owner |  |
| M0-O7 | Squash-merge PR #1 (M0) | done | M0-04, M0-05, M0-06, M0-07, M0-08, M0-O1, M0-O4, M0-O5 | owner | [#1](https://github.com/bondo/tally/issues/1) |
| M0-O8 | Retarget PR #16 to main after #1 merges, then squash-merge it | done | M0-O7, M0-09, M0-10, M0-11, M0-12, M0-FU | owner | [#16](https://github.com/bondo/tally/issues/16) |
| M0-O11 | Decide which proposals from the #20 process and tooling review to adopt | done | M0-13 | owner |  |
| M0-O9 | Create the GitHub labels orchestrator-state and owner-todo | done | none | owner |  |

### Open tasks and what blocks them

Nothing open.

## M0.5 Product design and guardrails

User stories, app flow, design tokens and the test, lint and review guardrails, signed off by the owner.

**Progress:** 35/35 done (100%), 0 open.

### Tasks

| Task | Title | Status | Depends on | Who | PR |
|---|---|---|---|---|---|
| M0.5-01 | User stories with acceptance criteria (docs/product/stories.md) | done | all of M0 | planner | [#94](https://github.com/bondo/tally/issues/94) |
| M0.5-02 | App-flow diagram (docs/product/flow.md, Mermaid) | done | M0.5-01 | planner | [#103](https://github.com/bondo/tally/issues/103) |
| M0.5-03 | Screen wireframes and design tokens (colors, type, spacing, dark mode) as an artifact | done | M0.5-01, M0.5-16 | planner | [#113](https://github.com/bondo/tally/issues/113) |
| M0.5-04 | App and repo name shortlist (#17)&#58; 5-8 candidates with Play Store, GitHub and domain availabilit… | done | all of M0 | planner | [#77](https://github.com/bondo/tally/issues/77) |
| M0.5-05 | guards.sh&#58; suppressions of new linters (noqa, type&#58; ignore, eslint-disable, &#64;ts-*, coverage, for… | done | M0-O11 | implementer | [#43](https://github.com/bondo/tally/issues/43) |
| M0.5-06 | CI&#58; shellcheck, actionlint, zizmor; SHA-pin actions; persist-credentials false (P2) | done | M0.5-05 | implementer | [#102](https://github.com/bondo/tally/issues/102) |
| M0.5-07 | ruff check (E,F,W,B,UP,SIM) and mypy (default) for scripts/, in verify.sh and CI (P3) | done | M0.5-05, M0-10 | implementer | [#79](https://github.com/bondo/tally/issues/79) |
| M0.5-08 | Firebase rules tests to strict TypeScript, ESLint strictTypeChecked and Prettier (P4, P5) | done | M0.5-05 | implementer | [#96](https://github.com/bondo/tally/issues/96) |
| M0.5-09 | Kotlin allWarningsAsErrors in all modules (P6) | done | M0-O11 | implementer | [#47](https://github.com/bondo/tally/issues/47) |
| M0.5-10 | licensee with the owner's allowlist (P8, D3)&#58; Apache-2.0, MIT, BSD-2-Clause, BSD-3-Clause; Goog… | done | M0.5-09 | implementer | [#84](https://github.com/bondo/tally/issues/84) |
| M0.5-11 | Konsist&#58; no floating point in core/domain, no raw colors/dp in UI; network-blocking JUnit extens… | done | M0-O11 | implementer | [#59](https://github.com/bondo/tally/issues/59) |
| M0.5-12 | Docs check&#58; relative links and backticked repo paths exist, planned paths allowlisted (P12) | done | M0.5-05, M0-11 | implementer | [#78](https://github.com/bondo/tally/issues/78) |
| M0.5-13 | Metrics&#58; orchestrator CSV comments per ORCHESTRATION 6 and scripts/agent_metrics.py to docs/age… | done | M0-O11 | implementer | [#58](https://github.com/bondo/tally/issues/58) |
| M0.5-14 | ORCHESTRATION.md retro changes&#58; delta review, one batch per PR, env pick, default deferral, early… | done | M0-O11 | process | [#41](https://github.com/bondo/tally/issues/41) |
| M0.5-15 | Prompts&#58; design-reviewer role and checklist, PR-body refresh, delta review, environment pick (P… | done | M0-11, M0.5-14, M0.5-23 | implementer | [#83](https://github.com/bondo/tally/issues/83) |
| M0.5-FU | Follow-up burn-down for M0.5 | done | M0.5-01, M0.5-02, M0.5-03, M0.5-04, M0.5-05, M0.5-06, M0.5-07, M0.5-08, M0.5-09, M0.5-10, M0.5-11, M0.5-12, M0.5-13, M0.5-14, M0.5-15, M0.5-16, M0.5-17, M0.5-18, M0.5-19, M0.5-20, M0.5-21, M0.5-22, M0.5-23, M0.5-24, M0.5-25, M0.5-26, M0.5-27, M0.5-28, M0.5-29 | implementer |  |
| M0.5-27 | Status picture on the README&#58; scripts render docs/tasks.toml plus PR and issue state to an SVG, a… | done | none | implementer | [#71](https://github.com/bondo/tally/issues/71) |
| M0.5-O1 | Approve stories, flow and design | done | M0.5-01, M0.5-02, M0.5-03 | owner |  |
| M0.5-O2 | Pick the app and repo name from the shortlist | done | M0.5-04 | owner | [#77](https://github.com/bondo/tally/issues/77) |
| M0.5-O3 | Log collaborator decisions D1-D7, create the five labels, check Actions settings (C5) | done | none | owner |  |
| M0.5-16 | COLLABORATING.md plus ORCHESTRATION, PLAN and orchestrator-state changes for the collaborator | done | M0.5-O3 | process | [#55](https://github.com/bondo/tally/issues/55) |
| M0.5-17 | Issue forms for feedback, ideas and questions, with a test that parses them | done | M0.5-O3 | implementer | [#56](https://github.com/bondo/tally/issues/56) |
| M0.5-18 | scripts/collab_inbox.py&#58; digest of trusted collaborator activity since a time, from saved API JSON | done | M0.5-17 | implementer | [#64](https://github.com/bondo/tally/issues/64) |
| M0.5-19 | Orchestrator and worker prompts&#58; inbox and accident-check wake steps, tiers, fenced text, label … | done | M0.5-16, M0.5-18 | implementer | [#67](https://github.com/bondo/tally/issues/67) |
| M0.5-20 | docs/ANDROID-BEST-PRACTICES.md&#58; checklist from Google's Android guidance, enforced vs reviewer-c… | done | none | process | [#62](https://github.com/bondo/tally/issues/62) |
| M0.5-21 | Usage-limit handling&#58; ORCHESTRATION pause protocol, early warning, limit failures are not stalls… | done | M0.5-13 | process | [#63](https://github.com/bondo/tally/issues/63) |
| M0.5-22 | CLAUDE.md&#58; allow one reviewer session to review several small docs-only PRs (the pending bulle… | done | M0.5-21 | implementer | [#93](https://github.com/bondo/tally/issues/93) |
| M0.5-23 | docs/reviews/README.md&#58; review catalogue R1-R12, procedures, visual-quality rubric, meta-revie… | done | M0.5-21 | implementer | [#72](https://github.com/bondo/tally/issues/72) |
| M0.5-24 | scripts/agent_metrics.py&#58; &#96;review&#96; row type (ledger of docs/reviews/README.md section 5), fai… | done | M0.5-23 | implementer | [#73](https://github.com/bondo/tally/issues/73) |
| M0.5-25 | Orchestrator prompt&#58; R3 weekly digest step, ledger row after each review, R10 owner-todo per … | done | M0.5-19, M0.5-21, M0.5-23 | implementer | [#74](https://github.com/bondo/tally/issues/74) |
| M0.5-26 | REVIEW.md&#58; R9 visual-rubric item (agent score below 3 is a minor finding) and R7 rules allow/… | done | M0.5-03, M0.5-15, M0.5-23 | implementer | [#133](https://github.com/bondo/tally/issues/133) |
| M0.5-O4 | Collaborator invite sent and accepted | done | M0.5-19, M0.5-O3 | owner |  |
| M0.5-O5 | Confirm the collaborator's 2FA and run the live test | done | M0.5-O4 | owner |  |
| M0.5-28 | R6 retro of M0.5&#58; compare the Agent Usage Redesign pilot with its baseline and propose at most … | done | M0.5-01, M0.5-02, M0.5-03, M0.5-04, M0.5-05, M0.5-06, M0.5-07, M0.5-08, M0.5-09, M0.5-10, M0.5-11, M0.5-12, M0.5-13, M0.5-14, M0.5-15, M0.5-27, M0.5-16, M0.5-17, M0.5-18, M0.5-19, M0.5-20, M0.5-21, M0.5-22, M0.5-23, M0.5-24, M0.5-25, M0.5-26, M0.5-29 | retro | [#137](https://github.com/bondo/tally/issues/137) |
| M0.5-29 | File-size guard in scripts/guards.sh&#58; an added or changed file over 1 MB, or a PNG over 300 KB out… | done | none | implementer | [#141](https://github.com/bondo/tally/issues/141) |

### Open tasks and what blocks them

Nothing open.

## M1 Accounts and households

Google and email sign-in, households, invite links, members and ownership, with rules tests.

**Progress:** 82/113 done (72%), 31 open.

### Tasks

| Task | Title | Status | Depends on | Who | PR |
|---|---|---|---|---|---|
| M1-01 | Plan M1&#58; docs/milestones/M1.md and PR-sized tasks in this file | done | all of M0.5 | planner | [#124](https://github.com/bondo/tally/issues/124) |
| M1-02 | Create &#58;core&#58;data with an emulator smoke test; Auth and Firestore emulators in CI (firebase.jso… | done | M1-29 | implementer | [#294](https://github.com/bondo/tally/issues/294) |
| M1-03 | Roborazzi screenshots (light/dark x en/da), scripts/screenshots.sh, CI diff artifact, ATF and enabl… | done | M1-01 | implementer |  |
| M1-04 | Design tokens&#58; Theme.kt parity test against design/tokens.json and WCAG AA contrast test (P22) | done | M0.5-03, M1-03 | implementer | [#295](https://github.com/bondo/tally/issues/295) |
| M1-05 | PIT plus kotest-pitest on core/domain, mutationThreshold 80 (P16) | done | M1-01 | implementer |  |
| M1-06 | Rules fuzzing&#58; fast-check against a TS reference model of PLAN 3.1 (P17) | done | M1-01, M0.5-08, M1-10 | implementer | [#372](https://github.com/bondo/tally/issues/372) |
| M1-07 | Test-impact summary&#58; uncovered changed lines to the step summary and verify.sh (P19) | done | M1-01 | implementer | [#298](https://github.com/bondo/tally/issues/298) |
| M1-29 | Rename to Tally&#58; applicationId and namespace dk.bjarkebjarke.tally, packages, app label en/da | done | M1-01 | implementer | [#268](https://github.com/bondo/tally/issues/268) |
| M1-08 | Rules base&#58; signedIn() with email_verified, users/{uid} householdId set/clear and name, tombsto… | done | M1-52 | implementer | [#314](https://github.com/bondo/tally/issues/314) |
| M1-09 | Rules spike&#58; PLAN 3.1 items a-e in the emulator, ADR 0002 with the results | done | M1-08 | implementer | [#333](https://github.com/bondo/tally/issues/333) |
| M1-10 | Rules&#58; create household and member display name, allow and deny tests (transfer is M1-53) | done | M1-09 | implementer | [#352](https://github.com/bondo/tally/issues/352) |
| M1-95 | Rules&#58; household soft delete and cleanup (tombstone, P6, owner's cleanup of members, markers a… | done | M1-54, M1-53 | implementer | [#390](https://github.com/bondo/tally/issues/390) |
| M1-11 | Rules&#58; leave and remove member (removed marker), allow and deny tests | ready | M1-54, M1-53, M1-95 | implementer |  |
| M1-12 | Rules&#58; invites (create, get, list, revoke, cleanup), incl. unverified get denied (join is M1-54) | done | M1-10, M1-O12 | implementer | [#371](https://github.com/bondo/tally/issues/371) |
| M1-30 | App skeleton&#58; Hilt with KSP, Google Services plugin + generated stand-in config, Connectivity help… | done | M1-29, M1-02, M1-36, M1-49 | implementer | [#304](https://github.com/bondo/tally/issues/304) |
| M1-60 | Start-up root&#58; Navigation 3, M1 home (#194, Q1 A), signed-in/out routing (P10 steps 2 and 6), sig… | done | M1-30, M1-36, M1-49 | implementer | [#311](https://github.com/bondo/tally/issues/311) |
| M1-62 | Start-up gates (b2 of M1-60)&#58; update (START-01), email verified (#195, Q2 A), name saved (AUTH-1… | done | M1-60 | implementer | [#323](https://github.com/bondo/tally/issues/323) |
| M1-64 | guards check 2c&#58; YAML folded and multi-line values as one line, in addition to the per-line check… | done | M1-42 | implementer | [#325](https://github.com/bondo/tally/issues/325) |
| M1-65 | guards check 2c&#58; npm &#96;--&#96; tail resolved through package.json scripts, fail closed by construction … | done | M1-42 | implementer | [#330](https://github.com/bondo/tally/issues/330) |
| M1-71 | guards check 1&#58; test-runner options that skip or rewrite tests on command lines (jest, vitest, … | done | M1-65 | implementer | [#339](https://github.com/bondo/tally/issues/339) |
| M1-81 | guards check 1&#58; playwright and cypress test-runner options on command lines | done | M1-71 | implementer | [#358](https://github.com/bondo/tally/issues/358) |
| M1-82 | Firestore source for the minimum app version&#58; config/app.minVersionCode bound in GateModule | in progress | M1-27, M1-88 | implementer | [#391](https://github.com/bondo/tally/issues/391) |
| M1-13 | Domain&#58; email, password and name validation (12+ code points, name 1-50), property tests | done | M1-37 | implementer | [#303](https://github.com/bondo/tally/issues/303) |
| M1-14 | Auth data 1&#58; Google sign-in and sign-out steps (OQ-13) in core/domain, with fakes for every step | done | M1-60, M1-13, M1-02, M1-50 | implementer | [#319](https://github.com/bondo/tally/issues/319) |
| M1-67 | Auth data 2&#58; Firebase session state, Google ID-token sign-in, per-session Firestore holder in &#58;core… | done | M1-14 | implementer | [#348](https://github.com/bondo/tally/issues/348) |
| M1-66 | Auth wiring 1&#58; Credential Manager wrapper (Sign in with Google button flow) in &#58;core&#58;data, &#58;ap… | done | M1-67, M1-O14 | implementer | [#368](https://github.com/bondo/tally/issues/368) |
| M1-88 | Auth wiring 2&#58; Hilt bindings for session, sign-in and sign-out (replace the M1-60 stand-in Sessio… | done | M1-66 | implementer | [#381](https://github.com/bondo/tally/issues/381) |
| M1-89 | Clear the local data on every change to signed out, also when Firebase signs the user out itself (… | in progress | M1-88 | implementer | [#398](https://github.com/bondo/tally/issues/398) |
| M1-15 | Auth data&#58; email and password sign-up, sign-in, verification, reset, error mapping, collision m… | in progress | M1-88, M1-62 | implementer | [#396](https://github.com/bondo/tally/issues/396) |
| M1-16 | Sign-in UI&#58; sign-in screen and Google button (AUTH-01, AUTH-02; sign-out UI is M1-25) | in progress | M1-88, M1-03, M1-49 | implementer | [#397](https://github.com/bondo/tally/issues/397) |
| M1-17 | Email UI&#58; create account, check your email, sign in, reset (AUTH-05..08, AUTH-10) | blocked | M1-15, M1-16, M1-62 | implementer |  |
| M1-24 | LocaleConfig&#58; generateLocaleConfig and resources.properties (LANG-02) | done | M1-29 | implementer | [#287](https://github.com/bondo/tally/issues/287) |
| M1-18 | Household data 1&#58; create, invite, revoke, join, start-up self-heal (emulator) | in progress | M1-54, M1-88, M1-60, M1-62, M1-02, M1-83 | implementer | [#395](https://github.com/bondo/tally/issues/395) |
| M1-31 | Household data 2&#58; leave, remove (marker, resumable), transfer, delete with cleanup resume (em… | blocked | M1-11, M1-18 | implementer |  |
| M1-19 | Household UI&#58; create, members, invite share sheet, revoke (HH-01, HH-02, HH-04) | blocked | M1-18 | implementer |  |
| M1-20 | Invite link and join screen (HH-03), incl. signed-out routing through sign-in | blocked | M1-19, M1-17 | implementer |  |
| M1-21 | Leave, remove, transfer and delete household UI, household-deleted dialog (HH-05, HH-06) | blocked | M1-19, M1-31 | implementer |  |
| M1-22 | Account&#58; change password with recent sign-in (AUTH-11) | blocked | M1-17, M1-25 | implementer |  |
| M1-32 | Account&#58; delete account (AUTH-04) with recent sign-in, resumable | blocked | M1-22, M1-21 | implementer |  |
| M1-23 | Optional TOTP two-step verification (AUTH-09) | blocked | M1-32, M1-O3 | implementer |  |
| M1-25 | Account screen (wireframe 18) and navigation&#58; sign-out UI (AUTH-03), Crashlytics opt-in switch, … | ready | M1-60, M1-88 | implementer |  |
| M1-26 | App Check&#58; Play Integrity in release, debug provider in debug builds (not enforced) | done | M1-30 | implementer |  |
| M1-27 | Minimum app version&#58; config/app.minVersionCode, schemaVersion, update screen | done | M1-08, M1-60, M1-62 | implementer | [#343](https://github.com/bondo/tally/issues/343) |
| M1-28 | Privacy text draft in English and Danish (OQ-30) | done | M1-01 | planner | [#286](https://github.com/bondo/tally/issues/286) |
| M1-33 | Release smoke build with R8 in CI (best-practices checklist follow-up 7) | done | M1-30 | implementer |  |
| M1-52 | Rules test harness&#58; default-deny paths from PLAN section 3, list and collection-group queries, unv… | done | M1-35 | implementer | [#301](https://github.com/bondo/tally/issues/301) |
| M1-53 | Rules&#58; transfer ownership, allow and deny tests (partial transfers, plain member, non-member) | done | M1-10 | implementer | [#364](https://github.com/bondo/tally/issues/364) |
| M1-54 | Rules&#58; the join batch with the one-household check, allow and deny tests | done | M1-12 | implementer | [#382](https://github.com/bondo/tally/issues/382) |
| M1-83 | Rules&#58; members read the household doc and its members (PLAN 3.1 Reads), allow and deny tests | done | M1-10 | implementer | [#366](https://github.com/bondo/tally/issues/366) |
| M1-55 | Tooling&#58; move the androidTest ListiclesAppTest into the tally package as TallyAppTest and update t… | done | M1-29 | implementer |  |
| M1-49 | detekt LongParameterList&#58; ignoreAnnotated &#91;Composable&#93; for that rule only (issue 217 item 5) | done | M1-01 | implementer | [#236](https://github.com/bondo/tally/issues/236) |
| M1-56 | Java API level check&#58; also look up classes used only as class literals, annotations, checkcast, ins… | done | M1-37 | implementer | [#305](https://github.com/bondo/tally/issues/305) |
| M1-61 | Java API level check&#58; also look up classes named only in descriptors, Signature attributes, throw… | ready | M1-56 | implementer |  |
| M1-63 | Debug APK as a CI artifact on every push to main | done | M1-30 | implementer |  |
| M1-70 | Status&#58; dependency graph of the open tasks under the README status picture (status-graph.svg) | done | none | implementer | [#326](https://github.com/bondo/tally/issues/326) |
| M1-75 | Status graph layout&#58; fewer crossings, arrows routed between rows and columns | done | M1-70 | implementer | [#338](https://github.com/bondo/tally/issues/338) |
| M1-76 | Status graph styling&#58; a colour-blind-safe colour per source task, thicker critical path | done | M1-75 | implementer |  |
| M1-50 | Konsist&#58; no data source in composables or ViewModels, no GlobalScope (checklist proposed follow… | done | M1-01 | implementer | [#290](https://github.com/bondo/tally/issues/290) |
| M1-57 | Konsist&#58; no Context, Activity or AndroidViewModel in ViewModels, no Dispatchers outside the DI … | done | M1-50 | implementer | [#307](https://github.com/bondo/tally/issues/307) |
| M1-51 | Build guards&#58; scripts/check_build_guards.py with the targetSdk floor (checklist follow-up 4; foll… | done | M1-01 | implementer | [#296](https://github.com/bondo/tally/issues/296) |
| M1-58 | Build guard&#58; manifest cleartext and backup (checklist follow-up 5), in scripts/check_build_guards… | done | M1-51 | implementer | [#308](https://github.com/bondo/tally/issues/308) |
| M1-59 | Build guard&#58; catalog-only coordinates (checklist follow-up 3), in scripts/check_build_guards.py | done | M1-51 | implementer | [#310](https://github.com/bondo/tally/issues/310) |
| M1-35 | PLAN amendments from the follow-up triage (P1-P9 rules and users name, quota risk, PIT 80, ui … | done | M1-01 | planner | [#265](https://github.com/bondo/tally/issues/265) |
| M1-36 | Product docs&#58; start-up gates, M1 home, AUTH-06 wording, design status (owner answers Q1 A, Q2 … | done | M1-O7 | planner |  |
| M1-37 | JVM modules&#58; check Java API use against minSdk 26 with api-versions.xml (issue 228) | done | M1-01 | implementer | [#288](https://github.com/bondo/tally/issues/288) |
| M1-38 | Run the licensee and warnings gate self-tests only when their inputs change; licensee version as … | done | M1-01 | implementer |  |
| M1-39 | Your name (AUTH-12)&#58; users/{uid}.name, name step at first Google sign-in and at start, edit in A… | blocked | M1-08, M1-10, M1-18, M1-17, M1-25, M1-62 | implementer |  |
| M1-40 | Process docs wording&#58; owner-merge exceptions next to the merge-agent rule (issue 147), dispatch… | done | M1-01 | implementer | [#293](https://github.com/bondo/tally/issues/293) |
| M1-41 | check_gradle_repos.py&#58; dotted repositories.google(), raw strings and nested templates (issues 226… | done | M1-01 | implementer |  |
| M1-42 | guards check 2c&#58; actionlint flags and ruff --fix/--target-version, deferred nits (issues 164, 174) | done | M1-01 | implementer | [#321](https://github.com/bondo/tally/issues/321) |
| M1-43 | prompt_rules.py&#58; sentence-level negation for the resolve-thread rule (issue 153) | done | M1-01 | implementer |  |
| M1-44 | CI hardening nits&#58; job timeouts, pinned python and node, gitleaks download, npm install scripts … | done | M1-01 | implementer | [#331](https://github.com/bondo/tally/issues/331) |
| M1-73 | Advanced CodeQL workflow&#58; java-kotlin with a Gradle build, plus actions, javascript-typescript a… | done | M1-01 | implementer |  |
| M1-74 | Hash-locked pip requirements for the lint tools (issue 189 item 5) | done | M1-44 | implementer | [#355](https://github.com/bondo/tally/issues/355) |
| M1-45 | merge_ready.py nits still open after PRs 248 and 245 (issue 148) | done | M1-01 | implementer | [#292](https://github.com/bondo/tally/issues/292) |
| M1-46 | build-logic convention plugins; no allprojects or subprojects configuration (issue 217 items 1-3) | done | M1-02 | implementer |  |
| M1-68 | Root check tasks without cross-project reads&#58; checkWarningsAsErrors, checkJdkRelease, checkJavaAp… | done | M1-46 | implementer | [#359](https://github.com/bondo/tally/issues/359) |
| M1-84 | Isolated projects&#58; module build files read the root through isolated.rootProject, check 4 denies o… | in progress | M1-68 | implementer | [#384](https://github.com/bondo/tally/issues/384) |
| M1-69 | Nested builds&#58; dependency verification for the licensee fixture build (issue 217 item 4), check_gr… | done | M1-46 | implementer | [#328](https://github.com/bondo/tally/issues/328) |
| M1-47 | R12 screens vs wireframes for M1 (issue 65 review catalogue) | blocked | M1-16, M1-17, M1-19, M1-20, M1-21, M1-22, M1-23, M1-25, M1-27, M1-32, M1-39, M1-03, M1-04 | process |  |
| M1-48 | R8 milestone quality review for M1 (issue 65 review catalogue) | blocked | M1-02, M1-03, M1-04, M1-05, M1-06, M1-07, M1-08, M1-09, M1-10, M1-11, M1-12, M1-13, M1-14, M1-15, M1-16, M1-17, M1-18, M1-19, M1-20, M1-21, M1-22, M1-23, M1-24, M1-25, M1-26, M1-27, M1-28, M1-29, M1-30, M1-60, M1-62, M1-31, M1-32, M1-33, M1-35, M1-36, M1-37, M1-38, M1-39, M1-40, M1-41, M1-42, M1-43, M1-44, M1-45, M1-46, M1-47, M1-49, M1-50, M1-51, M1-52, M1-53, M1-54, M1-68, M1-69, M1-82 | process |  |
| M1-34 | guards.sh&#58; compare line length per tool across all style files, with ruff and flake8 defaults (is… | done | none | implementer |  |
| M1-77 | State issue part A&#58; one JSON block in the body, typed schema, scripts/state_body.py validate | done | none | implementer | [#340](https://github.com/bondo/tally/issues/340) |
| M1-80 | State issue part A2&#58; state_body.py render (short summary above the block), tasks.py --state reads… | done | M1-77 | implementer |  |
| M1-78 | State issue part B&#58; rotation (milestone end, ~250 comments or ~15 KB body), merge_ready.py --ap… | done | M1-77 | implementer |  |
| M1-79 | State issue part C&#58; ORCHESTRATION.md 2, 3, 4.3, 5 and orchestrator-state.md for the JSON block, r… | done | M1-77, M1-78, M1-80 | process | [#365](https://github.com/bondo/tally/issues/365) |
| M1-FU | Follow-up burn-down for M1 (planner&#58; add each new M1 task to depends_on) | blocked | M1-88, M1-89, M1-90, M1-01, M1-02, M1-03, M1-04, M1-05, M1-06, M1-07, M1-08, M1-09, M1-10, M1-11, M1-12, M1-91, M1-92, M1-93, M1-94, M1-95, M1-13, M1-14, M1-15, M1-16, M1-17, M1-18, M1-19, M1-20, M1-21, M1-22, M1-23, M1-24, M1-25, M1-26, M1-27, M1-28, M1-29, M1-30, M1-31, M1-32, M1-33, M1-34, M1-35, M1-36, M1-57, M1-37, M1-38, M1-39, M1-40, M1-41, M1-42, M1-43, M1-44, M1-45, M1-46, M1-47, M1-48, M1-49, M1-50, M1-51, M1-52, M1-53, M1-54, M1-55, M1-56, M1-58, M1-59, M1-60, M1-61, M1-62, M1-63, M1-64, M1-65, M1-66, M1-67, M1-68, M1-69, M1-70, M1-71, M1-73, M1-74, M1-75, M1-76, M1-77, M1-78, M1-79, M1-80, M1-81, M1-82, M1-83, M1-84, M1-85, M1-86, M1-87 | implementer |  |
| M1-O1 | Create the Firebase project (Spark), Firestore in eur3, email sign-in, google-services.json secret | done | all of M0, M0.5-O2, M1-29, M1-O10 | owner |  |
| M1-O2 | Register the SHA-1 and SHA-256 fingerprints of the debug key in Firebase (Google sign-in) | dropped | M1-O1, M1-O16 | owner |  |
| M1-O3 | Check the Identity Platform upgrade needs no billing (OQ-25); if so, upgrade and enable TOTP via R… | owner to-do | M1-O1 | owner |  |
| M1-O4 | Enable the Play Integrity API for the Firebase project in the Google Cloud console | owner to-do | M1-O1, M1-26 | owner |  |
| M1-O5 | Approve the privacy text (OQ-30) before anyone but the owner installs the app | owner to-do | M1-28 | owner |  |
| M1-O6 | Deploy firestore.rules to the real project after each merged rules PR and before each tester build | owner to-do | M1-O1, M1-11 | owner |  |
| M1-O7 | Answer the M1 planning questions Q1-Q7 (docs/milestones/M1.md section 6.1) | done | none | owner |  |
| M1-O8 | Turn on secret scanning non-provider patterns and validity checks (repo settings) | dropped | none | owner |  |
| M1-O9 | Turn off CodeQL default setup when the advanced workflow of M1-73 merges | done | M1-73 | owner |  |
| M1-O10 | Ask the owner about the repo rename to Tally (right before M1-O1) | done | M1-29 | owner |  |
| M1-O11 | Add the screenshots check to the main ruleset required list (M1-03 added the job; docs list it as… | done | M1-03 | owner |  |
| M1-O12 | Decide #280 (who may list invites) before M1-12 starts | done | none | owner |  |
| M1-O13 | Add the release-smoke check to the main ruleset required list (M1-33 added the job; docs list it… | done | M1-33 | owner |  |
| M1-O14 | Decide the licences of the 17 artifacts &#58;app needs for Firebase Auth and Credential Manager (list … | done | none | owner |  |
| M1-O15 | Check once with a real Google sign-in which fields the Firebase Auth record keeps (privacy Q5) | dropped | M1-O1, M1-O2, M1-O16, M1-66, M1-16, M1-86 | owner |  |
| M1-O16 | Enable Google sign-in in Firebase (needs a public support email for Tally) | dropped | M1-O1 | owner |  |
| M1-85 | Repo name and checkout path from one place, so the scripts work before and after the repo rename | done | none | implementer |  |
| M1-86 | Google sign-in switch in &#58;app (off in v1)&#58; hide the Google button and the Google hint while off | blocked | M1-66, M1-16 | implementer |  |
| M1-87 | Repo rename follow-up&#58; the old repo name and checkout path in process files, docs, README and a… | done | none | implementer |  |
| M1-90 | Blank names&#58; one definition for the rules (trim strips code points up to U+0020) and the app (Kot… | ready | M1-06 | implementer |  |
| M1-91 | Tooling&#58; hooks and status line read TALLY_* env names; TALLY_TASK=tooling accepted next to LISTICL… | done | none | implementer | [#389](https://github.com/bondo/tally/issues/389) |
| M1-92 | Tooling&#58; process docs, prompts and status output say Tally; new sessions get tally&#58;* tags | done | none | implementer | [#388](https://github.com/bondo/tally/issues/388) |
| M1-93 | Build names&#58; rootProject.name tally, convention plugin ids tally.*, catalog aliases, tallyChecks … | ready | M1-68 | implementer |  |
| M1-94 | Tooling&#58; drop LISTICLES_TASK and the dev/listicles package root; docs name TALLY_TASK=tooling | blocked | M1-O17, M1-91, M1-92 | implementer |  |
| M1-O17 | Owner&#58; add TALLY_TASK=tooling to the Tally tooling environment (keep LISTICLES_TASK for now) | owner to-do | M1-91 | owner |  |
| M1-O18 | Owner&#58; remove LISTICLES_TASK from the Tally tooling environment; drop the listicles2 path in th… | owner to-do | M1-94 | owner |  |

### Open tasks and what blocks them

An arrow points from what a task waits on to the task. Dashed grey boxes are outside this milestone.

```mermaid
flowchart LR
    n0["M1-11 Rules: leave and remove member (rem… (ready)"]:::ready
    n1["M1-82 Firestore source for the minimum app… (in progress)"]:::progress
    n2["M1-89 Clear the local data on every change to… (in progress)"]:::progress
    n3["M1-15 Auth data: email and password sign-up… (in progress)"]:::progress
    n4["M1-16 Sign-in UI: sign-in screen and Google b… (in progress)"]:::progress
    n5["M1-17 Email UI: create account, check your e… (blocked)"]:::blocked
    n6["M1-18 Household data 1: create, invite, revok… (in progress)"]:::progress
    n7["M1-31 Household data 2: leave, remove (mark… (blocked)"]:::blocked
    n8["M1-19 Household UI: create, members, invite… (blocked)"]:::blocked
    n9["M1-20 Invite link and join screen (HH-03), in… (blocked)"]:::blocked
    n10["M1-21 Leave, remove, transfer and delete hou… (blocked)"]:::blocked
    n11["M1-22 Account: change password with recent … (blocked)"]:::blocked
    n12["M1-32 Account: delete account (AUTH-04) with… (blocked)"]:::blocked
    n13["M1-23 Optional TOTP two-step verification (A… (blocked)"]:::blocked
    n14["M1-25 Account screen (wireframe 18) and nav… (ready)"]:::ready
    n15["M1-61 Java API level check: also look up clas… (ready)"]:::ready
    n16["M1-39 Your name (AUTH-12): users/{uid}.name… (blocked)"]:::blocked
    n17["M1-84 Isolated projects: module build files … (in progress)"]:::progress
    n18["M1-47 R12 screens vs wireframes for M1 (is… (blocked)"]:::blocked
    n19["M1-48 R8 milestone quality review for M1 (… (blocked)"]:::blocked
    n20["M1-FU Follow-up burn-down for M1 (planner:… (blocked)"]:::blocked
    n21["M1-O3 Check the Identity Platform upgrade ne… (owner to-do)"]:::owner
    n22["M1-O4 Enable the Play Integrity API for the F… (owner to-do)"]:::owner
    n23["M1-O5 Approve the privacy text (OQ-30) before… (owner to-do)"]:::owner
    n24["M1-O6 Deploy firestore.rules to the real proj… (owner to-do)"]:::owner
    n25["M1-86 Google sign-in switch in :app (off in … (blocked)"]:::blocked
    n26["M1-90 Blank names: one definition for the ru… (ready)"]:::ready
    n27["M1-93 Build names: rootProject.name tally, … (ready)"]:::ready
    n28["M1-94 Tooling: drop LISTICLES_TASK and the de… (blocked)"]:::blocked
    n29["M1-O17 Owner: add TALLY_TASK=tooling to the T… (owner to-do)"]:::owner
    n30["M1-O18 Owner: remove LISTICLES_TASK from th… (owner to-do)"]:::owner
    n3 --> n5
    n4 --> n5
    n0 --> n7
    n6 --> n7
    n6 --> n8
    n8 --> n9
    n5 --> n9
    n8 --> n10
    n7 --> n10
    n5 --> n11
    n14 --> n11
    n11 --> n12
    n10 --> n12
    n12 --> n13
    n21 --> n13
    n6 --> n16
    n5 --> n16
    n14 --> n16
    n4 --> n18
    n5 --> n18
    n8 --> n18
    n9 --> n18
    n10 --> n18
    n11 --> n18
    n13 --> n18
    n14 --> n18
    n12 --> n18
    n16 --> n18
    n0 --> n19
    n3 --> n19
    n4 --> n19
    n5 --> n19
    n6 --> n19
    n8 --> n19
    n9 --> n19
    n10 --> n19
    n11 --> n19
    n13 --> n19
    n14 --> n19
    n7 --> n19
    n12 --> n19
    n16 --> n19
    n18 --> n19
    n1 --> n19
    n2 --> n20
    n26 --> n20
    n0 --> n20
    n27 --> n20
    n28 --> n20
    n3 --> n20
    n4 --> n20
    n5 --> n20
    n6 --> n20
    n8 --> n20
    n9 --> n20
    n10 --> n20
    n11 --> n20
    n13 --> n20
    n14 --> n20
    n7 --> n20
    n12 --> n20
    n16 --> n20
    n18 --> n20
    n19 --> n20
    n15 --> n20
    n1 --> n20
    n17 --> n20
    n25 --> n20
    n0 --> n24
    n4 --> n25
    n29 --> n28
    n28 --> n30
    classDef ready fill:#dafbe1,stroke:#1a7f37,color:#1f2328
    classDef progress fill:#ddf4ff,stroke:#0969da,color:#1f2328
    classDef blocked fill:#fff8c5,stroke:#9a6700,color:#1f2328
    classDef owner fill:#ffebe9,stroke:#cf222e,color:#1f2328,stroke-dasharray:4 3
    classDef ext fill:#eaeef2,stroke:#59636e,color:#1f2328,stroke-dasharray:2 2
```

## M2 Inventory lists

Private and shared lists, plain and collection items, real-time sync and offline use, in English and Danish.

**Progress:** 0/2 done (0%), 2 open.

### Tasks

| Task | Title | Status | Depends on | Who | PR |
|---|---|---|---|---|---|
| M2-01 | Plan M2&#58; docs/milestones/M2.md and PR-sized tasks in this file | blocked | all of M1 | planner |  |
| M2-FU | Follow-up burn-down for M2 (planner&#58; add each new M2 task to depends_on) | blocked | M2-01 | implementer |  |

### Open tasks and what blocks them

An arrow points from what a task waits on to the task. Dashed grey boxes are outside this milestone.

```mermaid
flowchart LR
    n0["M2-01 Plan M2: docs/milestones/M2.md and … (blocked)"]:::blocked
    n1["M2-FU Follow-up burn-down for M2 (planner:… (blocked)"]:::blocked
    n2["all of M1"]:::ext
    n2 --> n0
    n0 --> n1
    classDef ready fill:#dafbe1,stroke:#1a7f37,color:#1f2328
    classDef progress fill:#ddf4ff,stroke:#0969da,color:#1f2328
    classDef blocked fill:#fff8c5,stroke:#9a6700,color:#1f2328
    classDef owner fill:#ffebe9,stroke:#cf222e,color:#1f2328,stroke-dasharray:4 3
    classDef ext fill:#eaeef2,stroke:#59636e,color:#1f2328,stroke-dasharray:2 2
```

## M3 Packing rules (domain)

(After v1.) Scaling, per-person templates and merging as property-tested pure Kotlin.

**Progress:** 0/3 done (0%), 3 open.

### Tasks

| Task | Title | Status | Depends on | Who | PR |
|---|---|---|---|---|---|
| M3-O1 | Enable Google sign-in in Firebase (needs a public support email for Tally) | owner to-do | M1-O1 | owner |  |
| M3-O2 | Register the SHA-1 and SHA-256 fingerprints of the debug key in Firebase (Google sign-in) | owner to-do | M1-O1, M3-O1 | owner |  |
| M3-O3 | Check once with a real Google sign-in which fields the Firebase Auth record keeps (privacy Q5) | owner to-do | M1-O1, M3-O2, M3-O1, M1-66, M1-16, M1-86 | owner |  |

### Open tasks and what blocks them

An arrow points from what a task waits on to the task. Dashed grey boxes are outside this milestone.

```mermaid
flowchart LR
    n0["M3-O1 Enable Google sign-in in Firebase (need… (owner to-do)"]:::owner
    n1["M3-O2 Register the SHA-1 and SHA-256 fingerpr… (owner to-do)"]:::owner
    n2["M3-O3 Check once with a real Google sign-in … (owner to-do)"]:::owner
    n3["M1-16 Sign-in UI: sign-in screen and Google b… (in progress)"]:::ext
    n4["M1-86 Google sign-in switch in :app (off in … (blocked)"]:::ext
    n0 --> n1
    n1 --> n2
    n0 --> n2
    n3 --> n2
    n4 --> n2
    classDef ready fill:#dafbe1,stroke:#1a7f37,color:#1f2328
    classDef progress fill:#ddf4ff,stroke:#0969da,color:#1f2328
    classDef blocked fill:#fff8c5,stroke:#9a6700,color:#1f2328
    classDef owner fill:#ffebe9,stroke:#cf222e,color:#1f2328,stroke-dasharray:4 3
    classDef ext fill:#eaeef2,stroke:#59636e,color:#1f2328,stroke-dasharray:2 2
```

## M4 Packing templates and trips

(After v1.) Template and rule editor, create a trip, trip checklist and one-off items.

Not planned yet.

## M5 Barcode scanning

(After v1.) Camera scanning, product lookup with a fallback to manual entry, duplicate warning.

Not planned yet.

## M6 Release

Signed APK on tag as a GitHub Release, and a disabled Play internal-track workflow.

**Progress:** 0/4 done (0%), 4 open.

### Tasks

| Task | Title | Status | Depends on | Who | PR |
|---|---|---|---|---|---|
| M6-O1 | Create the GitHub release key; register its SHA-1/SHA-256 in Firebase, App Check and assetlinks.json | owner to-do | M1-O1 | owner |  |
| M6-O2 | Register a free limited-distribution Android developer account when available in Denmark | owner to-do | none | owner |  |
| M6-O3 | Register App Check (Play Integrity, device integrity only) with the release key; watch metrics t… | owner to-do | M6-O1, M1-O4 | owner |  |
| M6-O4 | Adopt Git LFS for screenshot goldens (deferred&#58; only when the revisit trigger fires) | owner to-do | M6-O1 | owner |  |

### Open tasks and what blocks them

An arrow points from what a task waits on to the task. Dashed grey boxes are outside this milestone.

```mermaid
flowchart LR
    n0["M6-O1 Create the GitHub release key#59; register… (owner to-do)"]:::owner
    n1["M6-O2 Register a free limited-distribution A… (owner to-do)"]:::owner
    n2["M6-O3 Register App Check (Play Integrity, dev… (owner to-do)"]:::owner
    n3["M6-O4 Adopt Git LFS for screenshot goldens (d… (owner to-do)"]:::owner
    n4["M1-O4 Enable the Play Integrity API for the F… (owner to-do)"]:::ext
    n0 --> n2
    n4 --> n2
    n0 --> n3
    classDef ready fill:#dafbe1,stroke:#1a7f37,color:#1f2328
    classDef progress fill:#ddf4ff,stroke:#0969da,color:#1f2328
    classDef blocked fill:#fff8c5,stroke:#9a6700,color:#1f2328
    classDef owner fill:#ffebe9,stroke:#cf222e,color:#1f2328,stroke-dasharray:4 3
    classDef ext fill:#eaeef2,stroke:#59636e,color:#1f2328,stroke-dasharray:2 2
```

## Blockers

- **owner to-do** [#120](https://github.com/bondo/tally/issues/120): &#91;owner&#93; Register a free limited-distribution Android developer account when available in Denmark
- **owner to-do** [#291](https://github.com/bondo/tally/issues/291): &#91;owner&#93; M1-O5&#58; Approve the privacy text (OQ-30) before anyone but the owner installs the app
- **owner to-do** [#374](https://github.com/bondo/tally/issues/374): &#91;owner&#93; M1-O3&#58; Check the Identity Platform upgrade needs no billing (OQ-25); if so, upgrade and …
- **owner to-do** [#375](https://github.com/bondo/tally/issues/375): &#91;owner&#93; M1-O4&#58; Enable the Play Integrity API for the Firebase project in the Google Cloud console
- **owner to-do** [#376](https://github.com/bondo/tally/issues/376): &#91;owner&#93; M3-O1&#58; Enable Google sign-in in Firebase (needs a public support email for Tally)
- **owner to-do** [#377](https://github.com/bondo/tally/issues/377): &#91;owner&#93; M6-O1&#58; Create the GitHub release key; register its SHA-1/SHA-256 in Firebase, App Check a…
- **owner to-do** [#392](https://github.com/bondo/tally/issues/392): &#91;owner&#93; M1-O17&#58; add TALLY_TASK=tooling to the Tally tooling environment
- **PR to merge** [#384](https://github.com/bondo/tally/issues/384): M1-84&#58; isolated projects, module build files read the root through isolated.rootProject; check 4 …
- **PR to merge** [#393](https://github.com/bondo/tally/issues/393): M1-97&#58; handover messages between orchestrators
- **task** M1-17: waits on M1-15, M1-16
- **task** M1-31: waits on M1-11, M1-18
- **task** M1-19: waits on M1-18
- **task** M1-20: waits on M1-19, M1-17
- **task** M1-21: waits on M1-19, M1-31
- **task** M1-22: waits on M1-17, M1-25
- **task** M1-32: waits on M1-22, M1-21
- **task** M1-23: waits on M1-32, M1-O3
- **task** M1-39: waits on M1-18, M1-17, M1-25
- **task** M1-47: waits on M1-16, M1-17, M1-19 +7
- **task** M1-48: waits on M1-11, M1-15, M1-16 +13
- **task** M1-FU: waits on M1-89, M1-90, M1-11 +21
- **task** M1-O6: waits on M1-11
- **task** M1-86: waits on M1-16
- **task** M1-94: waits on M1-O17
- **task** M1-O18: waits on M1-94
