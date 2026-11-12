# M0 process and tooling review (issue #20)

Status: proposal for the owner, 2026-11-12. Report only: nothing here is adopted until the owner decides (§9).
Inputs: issues #20, #15 (state and metrics), #21–#29, PRs #1 and #16, `docs/ORCHESTRATION.md`, `docs/FOLLOW-UPS.md`,
`docs/PLAN.md`, `CLAUDE.md`, `REVIEW.md`, `scripts/`, `.github/`, `.githooks/`, `firebase/`, Gradle config, all on `main` at 5240577.
Probe runs (scratch dirs only, nothing committed): ruff 0.16.9, mypy 2.3.1, shellcheck 0.11.0, actionlint 1.7.12, zizmor
(offline), tsc 6.0.3, ESLint 10.14 with typescript-eslint `strictTypeChecked`. Gradle was not run (no build change here).

Legend. **Effort**: S ≤ 150 changed lines / 1 implementer session; M ≤ 400 lines; L = more than one PR.
**Agent cost** comes from #15 metrics: a small tooling PR with 1–2 review rounds costs about $5–8 (S) or $10–15 (M);
a stall roughly doubles that. **CI time** is the estimated wall-clock added to the slowest affected job (repo is public, so minutes
are free; wall-clock is what matters). **[P]** = touches hook-protected files (`CLAUDE.md`, `REVIEW.md`, `agents/`,
`.claude/`, `.github/`, `.githooks/`, `scripts/guards.sh`, `scripts/hooks/`), so it must run in the tooling environment
(`LISTICLES_TASK=tooling`). Every item is test-first (CLAUDE.md "How to work").

## 0. Top recommendations

1. **Teach `guards.sh` the new tools' suppression syntax before adopting any new linter** (P1). Today `# noqa`,
   `# type: ignore`, `eslint-disable`, `@ts-expect-error`, `# pragma: no cover`, `c8 ignore` and `# ruff: noqa` all pass
   the suppression pattern (`scripts/guards.sh:49`); only `# shellcheck disable=` is caught. Every linter we add is an
   unguarded escape hatch until this lands.
2. **Treat the PreToolUse guard as a tripwire, not a boundary, and turn on branch protection now** (D1, D5). 6 of the 8 M0
   follow-ups (#21–#26) are bypass forms of a 969-line shell model (`scripts/hooks/pretooluse_guard.py`). The real controls
   are server side, and they are missing: PR #1 landed as a merge commit (2f9ee1c), not a squash.
3. **Cheap CI linters for the code that gates everything else** (P2, P3): shellcheck, actionlint and zizmor for scripts and
   the workflow, plus SHA-pinned actions; ruff and mypy for the Python hooks. Today's numbers: shellcheck 1 warning,
   actionlint 0, zizmor 24 (17 unpinned actions), ruff 40, mypy 0 in default mode.
4. **Move the Firebase rules tests to strict TypeScript with typescript-eslint while the suite is 79 lines** (P4, P5). It
   is the only security gate (PLAN §3.1). The current file has 12 strict `tsc` errors and 35 ESLint errors, nearly all
   `any` leaking from `let env;`.
5. **Make visual review real: Roborazzi JVM screenshots that agents render and read locally, design tokens in one JSON file
   with parity and contrast tests, and a design-review prompt** (P14, P22, P23). PLAN §5.4 promises Roborazzi,
   accessibility checks, PIT and a network-blocking test extension; none of them exists yet.

## 1. More static checking (Q1)

What runs today: spotless/ktlint 1.8.0, detekt 1.23.8 (type-resolved only on `:core:domain`, ADR 0001), Android Lint
(`warningsAsErrors`, `app/build.gradle.kts:42`), Kover (80% overall and on `:app`, 95% line and 90% branch on
`:core:domain`), `guards.sh`, gitleaks, Gradle wrapper validation, and Dependabot (gradle, npm, actions).

| Finding | Evidence |
|---|---|
| Kotlin compiler warnings are not errors | `compilerOptions` sets only `jvmTarget` (`app/build.gradle.kts:58`, `core/domain/build.gradle.kts:19`) |
| "No floating point in `core/domain`" (CLAUDE.md) is enforced only by review | no detekt rule, guard or test mentions `Double`/`Float` |
| No licence check on shipped dependencies | none in the catalog or the build. It matters from M1 (Firebase) and M5 (ML Kit, Google terms) |
| Workflow and shell code are not linted | actionlint: 0 findings. shellcheck (warning level): 1 finding, `.githooks/pre-push:6` SC2046, which is intended word splitting and needs a justified disable. Plus 8 notes: 7 SC2001 in `guards.sh`, and one false positive SC2329 at `verify.sh:29` (`gradle` is called through `step "$@"`) |
| Actions pinned to major tags, credentials persisted | zizmor: 17 `unpinned-uses`, 7 `artipacked` (`actions/checkout` without `persist-credentials: false`) in `ci.yml`. PR #1 already listed this as a known gap |
| `scripts/test_tasks.py` (479 lines) runs nowhere | `verify.sh:32` and `ci.yml:101` discover only `scripts/hooks`. Already task M0-10; do it first |
| Docs cite paths that do not exist | 0 broken Markdown links, but 4 stale backticked references: `docs/status.md`, `handoff/orchestrator.md` (`agents/prompts/orchestrator.md:3,5,7`, F14), `docs/agent-tuning.md` (PLAN §9.4), `.github/ISSUE_TEMPLATE/follow-up.md` (FOLLOW-UPS) |
| PLAN §5.4 describes gates that do not exist | PIT, Roborazzi, `enableAccessibilityChecks`, the network-blocking JUnit extension, `scripts/agent-metrics`: none of them is in the repo |

Not recommended: Gradle dependency verification (`verification-metadata.xml`), because Dependabot cannot update it and every
bump would fail. Also not recommended: `explicitApi()`, because `:core:domain` has one consumer, so it adds noise without value.
More detekt rule sets (Compose rules, non-default rules) should wait until there is real UI code to evaluate them on (M2).

## 2. TypeScript instead of JavaScript (Q2)

The only JS is `firebase/test/rules.test.js` (79 lines, CommonJS, Jest 30). A `tsc --strict --checkJs
--noUncheckedIndexedAccess` probe gives **12 errors**: an implicit `any` from `let env;` (line 8, used 7×) and a string
index into `CLIENTS` (lines 57, 62). These are exactly the untyped seams that would hide a wrong rules-test helper in M1.

Recommendation: adopt (P4). Rename to `.ts`; `tsconfig.json` with `strict`, `noUncheckedIndexedAccess` and
`exactOptionalPropertyTypes`; `tsc --noEmit` as its own step; ES modules. For the runner, keep Jest via ts-jest if ts-jest
supports the installed TypeScript major (TS is at 6.0), otherwise switch to Vitest (native TS, same `describe/test.each` API).
The implementer checks this in the PR, so the owner does not need to decide it. `guards.sh` already covers `*.ts` tests
(`TESTSRC`, line 31). Add `tsconfig*.json` and `vitest.config.*` to `CFGSRC` (line 32) so `"strict": false` or test
filters get caught (part of P1).

What stays as it is:
* **Python** for hooks and `tasks.py`. They are stdlib-only and run with `python3 -I`, so no install step sits on the
  hook path. Rewriting about 1,260 lines of hooks plus about 1,640 lines of tests in TS would add Node start-up to every
  tool call and throw away proven tests.
* **Bash** for `verify.sh`, `guards.sh` and `.githooks/*`. They are thin orchestration and become safe enough with shellcheck.
* **Rules test helpers in TS**, the M1 rules oracle (P17) included.

## 3. More linting (Q3)

| Tool | Scope | Probe result | Recommendation |
|---|---|---|---|
| ruff check (`E,F,W,B,UP,SIM`, line length 140) | `scripts/**/*.py` | 40 findings: 25 E501, 7 SIM115 (`open` without `with`), 2 SIM102, 2 UP031, 1 SIM114, 1 SIM105, 1 E402, and 1 B023 that is a false positive (`scripts/tasks.py:386`, a closure called inside its own iteration). The `S`/`PL` sets add more than 600 findings, mostly noise (S603/S607 subprocess, E501) | Adopt with this rule set; fix the findings in the same PR |
| ruff format | same | 17 of 23 files would be reformatted: a big diff in protected files | Defer (D6). Do it, if at all, as one mechanical `big-pr` with no logic change |
| mypy | hooks and `tasks.py` | default mode: **0** errors. `--strict`: 219 errors (missing type arguments and annotations) | Adopt default mode now; strict per module later (defer) |
| shellcheck (`-S warning`) | `scripts/*.sh`, `.githooks/*` | 1 warning (see §1) | Adopt (P2) |
| ESLint flat config + typescript-eslint `strictTypeChecked` | `firebase/**/*.ts` | on today's JS: **35 errors** (13 `no-unsafe-call`, 8 `no-unsafe-member-access`, 7 `no-unsafe-argument`, 4 `no-require-imports`, 2 `no-unsafe-return`, 1 `no-unsafe-assignment`), all from untyped `any` and CommonJS, so expect about 0 after P4 | Adopt with P4 (P5) |
| Prettier | `firebase/` only (TS, JSON) | not run | Adopt with P5 as `npm run lint`. Do not route it through Spotless: that would couple Gradle to npm |
| markdownlint | docs | not run | Reject: style churn with no defect value. Use the link and path check (P12) instead |

Versions: pin ruff and mypy in CI (`pip install ruff==… mypy==…`) and pin the npm tools in `firebase/package.json`, so
Dependabot covers the npm side. Ruff and mypy config goes into a root `ruff.toml` / `mypy.ini`, which must be added to
CODEOWNERS (the root is not covered today) **[P]**.

## 4. More ways to automate testing (Q4)

| Idea | Value now | When | Notes |
|---|---|---|---|
| Network-blocking JUnit extension (PLAN §5.4) | M | before M1 | Fails the test when a socket opens. Small, and already promised |
| PIT on `:core:domain` (+ kotest-pitest) | M now, H at M3 | M1 start | Wire it while the domain is tiny (`CatalogKey`). The guards already know `mutationThreshold`. Start at 80%. CI +1–2 min |
| Roborazzi JVM screenshots, light/dark × en/da | H from M1 UI | M1 | See §5. The golden guard and the `golden-update` label already exist (`guards.sh` "Screenshot references"). CI +1–3 min |
| Accessibility: `enableAccessibilityChecks()` in Compose UI tests and Roborazzi ATF checks | H | with Roborazzi | Covers touch targets, contrast and labels mechanically, which today is REVIEW.md item 6, by hand |
| Compose UI tests on more screens | H | per milestone | A definition-of-done item in each milestone plan, not tooling |
| Rules fuzzing: fast-check property tests that compare the emulator's verdict with a small TS reference model of PLAN §3.1 | H | M1, with the real rules | Cap at about 200 runs per PR. CI +1–2 min |
| Sync/merge simulation: N replicas with offline queues and LWW, random interleavings as property tests in `:core:domain` | H | M2/M3 planner input | Pure Kotlin, integers only, so it fits the domain rules |
| Test-impact view: changed lines not covered (Kover XML + `git diff`) written to `$GITHUB_STEP_SUMMARY`, and the same output from `verify.sh` for reviewers | M | M1 | Small stdlib Python script, test-first |
| Mutation testing of the Python hooks (mutmut) | L | reject | Expensive on a regex shell model whose scope we should shrink instead (§6.2) |

## 5. Graphic design and visual review for agents (Q5)

The problem: agents cannot see an emulator. CI artifacts are hard for agents to reach (no `gh` CLI, and the GitHub tools
do not download artifacts). The owner reviews design on a phone. What works reliably is an image that the agent renders
itself and reads with the image-capable Read tool, plus mechanical checks for everything that can be stated as a rule.

* **P14 `scripts/screenshots.sh`**: runs the Roborazzi record or compare tasks on the JVM (Robolectric, no emulator) and
  writes PNGs and diff images to `build/`. Implementers attach the changed images to the PR description (light/dark × en/da,
  as the PR template already asks). Reviewers run the script and read the PNGs. CI compares against committed goldens
  and uploads the diffs as an artifact for the owner. Posting images into PR comments needs `pull-requests: write` and image
  hosting, so defer that.
* **P22 Design tokens, one source of truth**: `design/tokens.json` holds colors (light and dark), type scale, and spacing
  in integer dp. The M0.5 artifact reads it. Kotlin tokens in `Theme.kt` stay hand-written. A unit test asserts that they
  equal the JSON (parity), and a WCAG AA contrast test checks every foreground/background pair (4.5:1 for text, 3:1 for
  large text and UI). No code generation step. M0.5-03 should produce the JSON, not only an artifact.
* **P25 No raw values in UI code**: a Konsist or detekt rule bans `Color(0x…)` and `.dp`/`.sp` literals outside the
  theme package. Add it together with P7.
* **P23 Design-review prompt** (`agents/prompts/design-reviewer.md`, role in `roles.yaml`, Opus high) **[P]**, spawned
  only for PRs that change UI code or goldens. Checklist:
  * tokens only;
  * touch targets ≥ 48 dp;
  * contrast (backed by the test);
  * Danish text expansion: no truncation in `values-da`;
  * font scale 200%;
  * dark theme;
  * empty, loading, error and offline states;
  * content descriptions;
  * the screen matches the M0.5 wireframe and story ID.

  Each finding cites a screenshot file and a composable.
* Rejected: emulator screenshots in the agent loop (needs KVM and a heavy container in every review session; the CI `ui`
  job keeps behaviour coverage), and visual diffs with a tolerance threshold (a threshold is a gate that can be lowered;
  start at an exact match).

## 6. M0 retrospective (Q6)

### 6.1 Numbers (from #15, PRs #1 and #16)

| Measure | Value |
|---|---|
| Logged cost | about $64. Workers $52.6 (M0-1 $4.28, M0-2 $5.02, tooling about $23.4, process about $6.1, follow-ups about $8, merge review and fixes $4.66, cleanup and CI unstick $1.12) and orchestrator #1 $11.3. Several review costs are logged only as "+ review" (unknown); orchestrator #2 is not logged yet |
| Review rounds | PR #1: 12 (R1–R12; two batches hit the 4-round cap). PR #16: at least 6 (r1, follow-ups R1–R4 (cap), focused merge review, r5) |
| Convergence | Findings per round (blocker/major/minor/nit) for the plan batch: 3/9/7/2 → 1/4/4/2 → 0/2/3/3 → 0/0/2/1. Batch 1: 0/7/6/2 → … → 0/0/1/1. Blockers appear only in rounds 1–2; round 4 is almost all minor and nit findings |
| PR size | #1: 18,918 lines on GitHub (4,838 counted by the guard), 65 commits. #16: 2,335 lines, 83 commits. **Both needed `big-pr`**; the cap was raised 3000 → 6000 for PR #1 and stays at 6000 (`ci.yml:98`) |
| Unreviewed commits after the last review round | c1b54ff (batch 1 fixes after the cap); 8fdf219 (README touch-up) and **ba0eae3 (the guard cap change, a gate change)** on #1; e74f957 and fb6dfc1 (minor fixes after r5) on #16 |
| Stalls and blocks | Tooling sessions stalled on a context_guard bug that assumed a 200k window (about half of the $23.4). One worker was spawned in the wrong environment and blocked. One GitHub run was stuck in the queue (409 on cancel) and needed a touch-up commit. Android SDK licences needed the owner to type "go ahead" in 2 sessions (#18), then a setup script (#29); in this session `ANDROID_HOME=/opt/android-sdk` with `licenses/` is present, but no Gradle build was run here to prove it |
| Follow-ups | 8 of 8 allowed for M0 (#21–#28): 6 are PreToolUse shell-model bypasses, 1 is a guard false positive (#27), 1 is hook-test gaps (#28) |

### 6.2 What went wrong, and what to change

| # | Problem | Evidence | Change |
|---|---|---|---|
| R1 | The PreToolUse guard is an arms race | 969 lines modelling shell syntax; each round found new forms (env prefixes, piped shells, `cd` modelling, `remote add --mirror`) | Freeze the model. Document it as a tripwire against accidents, not a security boundary (ORCHESTRATION §9 new F18). The boundary is branch protection, required CODEOWNERS review and squash-only (M0-08 plus owner). After that is on, close #21–#26 as by-design (D1) |
| R2 | Merge method not enforced | `main` has "Merge pull request #1" (2f9ee1c): 65 branch commits, including handoff files, are now in `main`'s history, against PLAN §5.6 and §9.3 (`PLAN.md:352`) | Owner turns on branch protection with squash only (D5). Before asking for a merge, the orchestrator states "squash" in the request |
| R3 | Multi-batch PRs defeat the size cap | Both M0 PRs needed `big-pr`; the 6000 cap remains | From M0.5 on: one batch = one PR, no stacking. Lower the `big-pr` value to 1500 (D2). `big-pr` only for generated or mechanical diffs |
| R4 | Gate changes merge unreviewed after the cap | ba0eae3 changed the guard cap after the last round | New ORCHESTRATION §7.2 rule: any commit after the last round gets one **delta review** (fresh reviewer, range limited to the new commits, about $1–2) before the merge request. Gate or threshold changes always do. Record `reviewed_through` |
| R5 | Metrics are not in the agreed format and the sources are lost | #15 has **0 comments**: no `metrics:session/round/incident` CSV rows (ORCHESTRATION §6), only a free-form table with "~" and "+ review" (§6 says "never estimates"). The SessionEnd hook writes to gitignored `metrics/sessions/` inside ephemeral containers, so it is lost (`.gitignore`, `session_end_metrics.py:1-5`). `scripts/agent-metrics`, `docs/agent-metrics.csv` and `docs/agent-tuning.md` do not exist | The orchestrator posts one CSV comment per idle worker (from `get_session` usage) and one per round. P11 adds `scripts/agent_metrics.py` to parse those comments into the CSV at milestone end. Drop the SessionEnd hook as a metrics source for cloud sessions (keep it for local runs). New columns: `env`, `post_cap_commits`, `owner_interventions` |
| R6 | Stale PR descriptions at merge | #1 body: "Still to do…", "CI has not run on GitHub yet". #16 body: "Not yet reviewed" | The last implementer commit refreshes the PR body (scope, review table, test evidence). The orchestrator checks it before the merge request (implementer prompt **[P]**) |
| R7 | Protected prompts drift from the process | `agents/prompts/orchestrator.md:3,5,7` still say `docs/status.md`; ORCHESTRATION §8 says "until M0-11…" | Do M0-11 first. Add a path check (P12) so stale paths fail CI. Batch protected edits into a few tooling sessions |
| R8 | Wrong-environment spawns | 1 blocked worker; the rule lives only in #15 "habits" | Move the "pick the environment by touched paths" rule into ORCHESTRATION §7.1, with the protected path list. Every task's `notes` names its environment (§8 below does) |
| R9 | Rounds spent on minor findings | Round 4 is almost all minor and nit findings | Default: once a round has no blocker or major, the orchestrator defers the remaining minors (FOLLOW-UPS) instead of running another round, unless the minor is in a gate. Saves about $2–3 per round |
| R10 | Environment prerequisites discovered by workers | SDK licences (#18, #29) | Before spawning, a "fresh-session smoke" task checks the env (SDK present, `verify.sh --fast` passes) whenever the env setup script changes |

## 7. Prioritised proposals

| ID | Item | Value | Effort | Cost / CI time | Risk | Rec. |
|---|---|---|---|---|---|---|
| P1 | `guards.sh`: suppressions for ruff, mypy, ESLint, TS, coverage and formatters (`noqa`, `type: ignore`, `eslint-disable`, `@ts-*`, `pragma: no cover`, `c8`/`istanbul ignore`, `prettier-ignore`, `fmt: off`); new config files in `CFGSRC`; the 10 existing `# noqa` lines get `justified:` **[P]** | H | S | $5–8 / +0 s | false positives (guard history) | Adopt first |
| P2 | CI: shellcheck (`-S warning`), actionlint, zizmor; SHA-pin actions (Dependabot keeps them current); `persist-credentials: false` **[P]** | H | S | $5–8 / +20 s | low | Adopt |
| P3 | ruff check plus mypy (default) for `scripts/`, in `verify.sh` and CI; fix the 40 findings **[P]** | M | S–M | $8–12 / +10 s | churn in hook files | Adopt |
| P4 | Firebase tests to strict TS (`tsc --noEmit` step; ts-jest or Vitest) | H | S | $5–8 / +15 s | runner compatibility with TS 6 | Adopt |
| P5 | ESLint `strictTypeChecked` plus Prettier for `firebase/` | M | S | with P4 / +10 s | low | Adopt |
| P6 | Kotlin `allWarningsAsErrors` in all modules | M | S | $3–5 / 0 | Dependabot bumps fail on new deprecations (desired) | Adopt |
| P7 | Konsist architecture test: no `Float`/`Double`/`kotlin.math` floats in `:core:domain`; P25 raw-value ban in UI | M | S | $5–8 / +15 s | Konsist and Kotlin 2.4 compatibility (fallback: a guard grep) | Adopt |
| P8 | `app.cash.licensee` with an allowlist | M | S | $3–5 / +10 s | allowlist is an owner decision (D3) | Adopt before M1 deps |
| P9 | Compose detekt rules and selected non-default detekt rules | M | S | later | noise on little code | Defer to M2 |
| P10 | Gradle dependency verification | L | M | n/a | breaks every Dependabot PR | Reject |
| P11 | `scripts/agent_metrics.py` (state-issue CSV comments → `docs/agent-metrics.csv`) plus orchestrator CSV logging | H | M | $10–15 / +2 s | none | Adopt |
| P12 | Docs check: relative links and backticked repo paths exist (planned paths allowlisted) **[P]** (CI) | M | S | $5–8 / +2 s | allowlist upkeep | Adopt |
| P13 | Network-blocking JUnit extension (PLAN §5.4) | M | S | $3–5 / 0 | low | Adopt |
| P14 | Roborazzi plus `scripts/screenshots.sh` plus CI artifact upload; ATF accessibility checks **[P]** (CI) | H | M | $10–15 / +1–3 min | Robolectric rendering drift | Adopt in M1 |
| P15 | `enableAccessibilityChecks()` in Compose UI tests | H | S | with P14 / +0 | low | Adopt in M1 |
| P16 | PIT plus kotest-pitest on `:core:domain`, threshold 80 | M | S | $5–8 / +1–2 min | plugin compatibility | Adopt in M1 |
| P17 | Rules fuzzing with fast-check against a TS reference model | H | M | $10–15 / +1–2 min | the model can share bugs with the rules | Adopt in M1 (with rules) |
| P18 | Sync/merge simulation property tests | H | M | later | none | Defer: M2/M3 planner input |
| P19 | Test-impact summary (uncovered changed lines) **[P]** (CI) | M | M | $10–15 / +10 s | none | Defer to M1 |
| P20 | ruff format, mypy `--strict` | L | M | big diffs | churn | Defer (D6) |
| P21 | markdownlint; mutmut on the hooks; `explicitApi()`; emulator screenshots for agents | L | – | – | – | Reject |
| P22 | `design/tokens.json` plus parity and contrast tests | H | S–M | $5–10 / +5 s | none | Adopt: JSON in M0.5-03, tests in M1 |
| P23 | Design-review role, prompt and checklist **[P]** | H | S | $3–5 per UI PR | none | Adopt in M0.5 |
| C1 | ORCHESTRATION.md: R3, R4, R8, R9, F18 (R1), metrics rules (R5), smoke task (R10) | H | S | $3–5 | none | Adopt |
| C2 | Prompts: R6 (refresh the PR body), environment pick, delta review, design reviewer **[P]** | M | S | fold into M0-11 | none | Adopt |

Estimated total for "adopt before M1" (P1–P8, P11–P13, P23, C1, C2): about $70–110 in agent cost, and about 1 min of added
CI wall-clock, mostly in parallel jobs. Grouped as below, that is 4 tooling-environment sessions and 4 normal sessions.

## 8. Ready-to-paste tasks (for `docs/tasks.toml`; not applied here, another worker owns that file)

These tasks run alongside the M0.5 design work (design is docs only), so M1 coding starts with the gates in place. Add each
id to `M0.5-FU.depends_on` (or `M1-FU` for the M1 tasks; `tasks.py validate` enforces that). Effort and environment go in
`notes` because the schema has no field for them. Run `scripts/tasks.py validate` after pasting.

```toml
[[task]]
id = "M0.5-O2"
title = "Decide the #20 adoption list (docs/reviews/m0-process-tooling-review.md sections 7 and 9: D1-D6)"
milestone = "M0.5"
status = "todo"
assignee = "owner"
risk = "normal"
depends_on = []

[[task]]
id = "M0.5-04"
title = "guards.sh: suppressions of new linters (noqa, type: ignore, eslint-disable, @ts-*, coverage, formatter) and their config files (P1)"
milestone = "M0.5"
status = "todo"
assignee = "implementer"
risk = "normal"
depends_on = ["M0.5-O2"]
notes = "Tooling env. Effort S, implementer high (gate). Test-first: one negative case per syntax in test_guards_sh.py. Justify the 10 existing # noqa lines."

[[task]]
id = "M0.5-05"
title = "CI: shellcheck, actionlint, zizmor; SHA-pin actions; persist-credentials false (P2)"
milestone = "M0.5"
status = "todo"
assignee = "implementer"
risk = "normal"
depends_on = ["M0.5-04"]
notes = "Tooling env. Effort S. Pinned binaries with checksums like gitleaks. Fix .githooks/pre-push:6 SC2046 with a justified disable."

[[task]]
id = "M0.5-06"
title = "ruff check (E,F,W,B,UP,SIM) and mypy (default) for scripts/, in verify.sh and CI (P3)"
milestone = "M0.5"
status = "todo"
assignee = "implementer"
risk = "normal"
depends_on = ["M0.5-04", "M0-10"]
notes = "Tooling env. Effort S-M. Root ruff.toml/mypy.ini plus CODEOWNERS entry. No ruff format (deferred, D6)."

[[task]]
id = "M0.5-07"
title = "Firebase rules tests to strict TypeScript, ESLint strictTypeChecked and Prettier (P4, P5)"
milestone = "M0.5"
status = "todo"
assignee = "implementer"
risk = "normal"
depends_on = ["M0.5-04"]
notes = "Tooling env (ci.yml gets tsc and lint steps). Effort S. ts-jest if it supports the installed TS major, else Vitest."

[[task]]
id = "M0.5-08"
title = "Kotlin allWarningsAsErrors; licensee with the owner's allowlist (P6, P8)"
milestone = "M0.5"
status = "todo"
assignee = "implementer"
risk = "normal"
depends_on = ["M0.5-O2"]
notes = "Normal env (Gradle files, CODEOWNERS review). Effort S."

[[task]]
id = "M0.5-09"
title = "Konsist: no floating point in core/domain, no raw colors/dp in UI; network-blocking JUnit extension (P7, P13, P25)"
milestone = "M0.5"
status = "todo"
assignee = "implementer"
risk = "normal"
depends_on = ["M0.5-O2"]
notes = "Normal env. Effort S. Fallback if Konsist does not support Kotlin 2.4: a guards.sh grep (then tooling env)."

[[task]]
id = "M0.5-10"
title = "Docs check: relative links and backticked repo paths exist, planned paths allowlisted (P12)"
milestone = "M0.5"
status = "todo"
assignee = "implementer"
risk = "normal"
depends_on = ["M0.5-04", "M0-11"]
notes = "Tooling env (CI wiring). Effort S. Stdlib Python, test-first."

[[task]]
id = "M0.5-11"
title = "Metrics: orchestrator CSV comments per ORCHESTRATION 6 and scripts/agent_metrics.py to docs/agent-metrics.csv (P11, R5)"
milestone = "M0.5"
status = "todo"
assignee = "implementer"
risk = "normal"
depends_on = ["M0.5-O2"]
notes = "Normal env unless CI wiring is added (then tooling). Effort M. Backfill M0 rows from #15 with empty fields where unknown."

[[task]]
id = "M0.5-12"
title = "ORCHESTRATION.md retro changes: delta review, one batch per PR, env pick, default deferral, F18 tripwire, smoke task (C1)"
milestone = "M0.5"
status = "todo"
assignee = "process"
risk = "normal"
depends_on = ["M0.5-O2"]
notes = "Normal env (docs only). Effort S. Protected prompt parts go to M0.5-13."

[[task]]
id = "M0.5-13"
title = "Prompts: design-reviewer role and checklist, PR-body refresh, delta review (P23, C2)"
milestone = "M0.5"
status = "todo"
assignee = "implementer"
risk = "normal"
depends_on = ["M0-11", "M0.5-12"]
notes = "Tooling env (agents/, REVIEW.md). Effort S. Fold into the M0-11 session if it has not started yet."

[[task]]
id = "M1-03"
title = "Roborazzi screenshots (light/dark x en/da), scripts/screenshots.sh, CI diff artifact, ATF and enableAccessibilityChecks (P14, P15)"
milestone = "M1"
status = "todo"
assignee = "implementer"
risk = "normal"
depends_on = ["M1-01"]
notes = "Tooling env (CI). Effort M. Exact-match goldens (no tolerance)."

[[task]]
id = "M1-04"
title = "Design tokens: Theme.kt parity test against design/tokens.json and WCAG AA contrast test (P22)"
milestone = "M1"
status = "todo"
assignee = "implementer"
risk = "normal"
depends_on = ["M0.5-03", "M1-03"]
notes = "Normal env. Effort S. M0.5-03 must emit design/tokens.json."

[[task]]
id = "M1-05"
title = "PIT plus kotest-pitest on core/domain, mutationThreshold 80 (P16)"
milestone = "M1"
status = "todo"
assignee = "implementer"
risk = "normal"
depends_on = ["M1-01"]
notes = "Normal env plus a CI step (tooling) if it is not inside the unit job's Gradle call. Effort S."

[[task]]
id = "M1-06"
title = "Rules fuzzing: fast-check against a TS reference model of PLAN 3.1 (P17)"
milestone = "M1"
status = "todo"
assignee = "implementer"
risk = "high"
depends_on = ["M1-01", "M0.5-07"]
notes = "Normal env. Effort M. Depends on the first real rules task from the M1 plan; the planner wires that dependency."

[[task]]
id = "M1-07"
title = "Test-impact summary: uncovered changed lines to the step summary and verify.sh (P19)"
milestone = "M1"
status = "todo"
assignee = "implementer"
risk = "normal"
depends_on = ["M1-01"]
notes = "Tooling env (CI). Effort M."
```

Deferred items that need follow-up issues (label `follow-up`, but not counted against a milestone's 8 because they are not
review findings; suggest the label `deferred-tooling`): P9 (target M2), P18 (M2/M3 planner input), P20 (no target).

## 9. Owner decisions

| ID | Question | Recommendation |
|---|---|---|
| D1 | Freeze the PreToolUse shell model and close #21–#26 as by-design once branch protection is on? | Yes. It saves the M0-FU burn-down cost (six follow-ups of shell edge cases) |
| D2 | Lower the `big-pr` diff value from 6000 to 1500 (`ci.yml:98`)? | Yes. M0 is merged; 6000 now weakens the gate for any labelled PR |
| D3 | Licence allowlist for licensee: Apache-2.0, MIT, BSD-2/3-Clause; Google/Android SDK terms per artifact (Firebase, ML Kit) | Allow these SPDX ids; allow Google terms per artifact as each is added |
| D4 | Approve the adopt/defer/reject column in §7 as a whole, or per item | Approve as a whole; reject individual items if needed |
| D5 | Turn on branch protection on `main` (squash only, required checks, CODEOWNERS review) now, ahead of the M0-08 guide | Yes. PR #1 has already landed as a merge commit |
| D6 | Run `ruff format` once on `scripts/` (big mechanical diff in protected files) or never? | Not now. Revisit when hooks next change substantially |

## 10. Checks for this PR

Docs only. `GUARD_BASE=origin/main scripts/guards.sh` was run, and the relative link check from §1 was run on this file. The §8 snippet, pasted into a scratch copy of `docs/tasks.toml` with the FU dependencies added, passes `scripts/tasks.py --file <copy> validate` (49 tasks).
No markdown linter exists in the repo. Unit, Gradle and rules tests were skipped: no code changed.
