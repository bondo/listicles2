# Listicles – Implementation Plan

Android app for shared household lists (inventories such as DVDs, and packing lists
that combine into scaled trip checklists). Changes sync in real time between members.

## 1. Decisions

| Area | Decision |
|---|---|
| Client | Kotlin + Jetpack Compose, single Activity, MVVM + unidirectional state, Hilt DI |
| Backend | Firebase (Spark/free): Auth (Google sign-in via Credential Manager) + Cloud Firestore. **No Cloud Functions** (they need the paid Blaze plan), so all integrity checks live in security rules |
| Sync | Firestore snapshot listeners; offline cache on; one document per item; updates write only the changed fields; same-field conflicts resolve last write wins |
| Sharing | Households: every list belongs to a household; members join with an invite code or link |
| Inventory lists | Generic items (name, notes, quantity, tags, optional barcode) with search, sort and filter |
| Barcode | Google ML Kit barcode scanning (on-device, free) + CameraX |
| Title lookup | UPCitemdb trial API (no key, ~100 lookups/day); manual entry if the lookup fails; the result is always editable |
| Packing scaling | Per-item rule: `FIXED`, `PER_DAY`, `PER_N_DAYS`, with optional `extra`, `min`, `max`; round up |
| Packing merge | Items are matched by stable `catalogKey` (normalized name); the **max** scaled quantity wins |
| Trips | Generating a trip creates a **snapshot** checklist (amount, packed flag, one-off additions); later template edits don't change it |
| i18n | English + Danish; all strings in resources; CI fails on missing translations |
| AI at runtime | No AI code apart from on-device ML Kit. No LLM or cloud AI calls |
| Distribution | Signed APK on GitHub Releases on each `v*` tag; Play internal-testing pipeline prepared but turned off until the $25 account exists |
| Review | Every change is a PR → CI gates → a separate Claude session with no authoring context reviews it against `REVIEW.md` → fix and re-review until only nits remain → the owner merges |

## 2. Repository layout

```
/app                  Android app (Compose UI, navigation, DI wiring)
/core/domain          Pure Kotlin/JVM: models, scaling, merging, search/sort/filter, validation
/core/data            Firestore + Auth repositories, mappers, UPC lookup client (Ktor/OkHttp)
/core/testing         Fakes (in-memory repositories), test fixtures
/firebase             firestore.rules, firestore.indexes.json, firebase.json, rules tests (Jest)
/docs                 PLAN.md, ARCHITECTURE.md, ADRs
/scripts              verify.sh and guard scripts used by CI and git hooks
REVIEW.md             Review rubric and severity definitions
CLAUDE.md             Agent instructions: the only commands to run, and the rules
```

`core/domain` has **no Android or Firebase dependencies**, so most logic gets fast JVM tests.

## 3. Data model (Firestore)

```
users/{uid}                      { displayName, householdId }
households/{hid}                 { name, createdBy, createdAt }
households/{hid}/members/{uid}   { role: owner|member, joinedAt, viaInvite }
invites/{code}                   { householdId, createdBy, expiresAt }
households/{hid}/lists/{lid}     { kind: INVENTORY|PACKING_TEMPLATE|TRIP, name, createdAt, updatedAt,
                                   trip?: { days, sourceListIds[], generatedAt } }
households/{hid}/lists/{lid}/items/{iid}
   { name, catalogKey, notes, tags[], quantity, barcode?, sortKey,
     rule?: { kind, amount, perDays, extra, min, max },   // packing templates
     packed?: bool,                                       // trips
     updatedAt (serverTimestamp), updatedBy }
```

Security rules (each one tested in the emulator):
* A user can read or write a household subtree only if `members/{uid}` exists.
* Joining: a user may create their own `members/{uid}` doc only if `invites/{code}` points at
  that household and hasn't expired (`viaInvite` == code, checked with `get()`).
* Field validation: types, string lengths, allowed `kind` values, rule invariants
  (`min <= max`, `perDays >= 1`), `updatedBy == request.auth.uid`.
* No client may change another member's role. Only the owner can delete the household.

Free-tier budget: per-item docs and listeners, with about 10 users, stay well under
50k reads and 20k writes per day. Lists are paged and listeners are only attached
to the screen being viewed.

## 4. Domain logic (core/domain)

**Scaling**: `quantityFor(rule, days)`:
* `FIXED`: `amount`
* `PER_DAY`: `ceil(amount * days)`
* `PER_N_DAYS`: `amount * ceil(days / perDays)`
* then `+ extra`, then clamp to `[min, max]`. `days >= 1` is validated.

**Merging**: `combine(templates, days): List<TripItem>`. The domain layer groups items
by `catalogKey` (lowercase, trimmed, whitespace collapsed, diacritics kept so æ/ø/å still
match), scales each one, and takes the max. Notes and tags are unioned, the source
lists are recorded, and the order is deterministic.

**Search, sort and filter**: pure functions over item lists (text match on name, notes
and barcode; tag filter; sort by name, created or updated). They are unit- and property-tested.

Testing: Kotest + JUnit5, **property-based tests** (kotest-property) for scaling and
merging invariants, e.g. "merge is commutative", "result ≥ each input", "idempotent
when combining a list with itself", "monotonic in days". Kover floor: **95% line and
90% branch on core/domain**, 80% overall.

## 5. Tooling-first process (guardrails)

The goal: an agent (or a person) *cannot* merge something broken, because tools
enforce the rules rather than goodwill.

1. **One entrypoint**: `./scripts/verify.sh` runs exactly what CI runs: spotless,
   detekt, Android Lint, unit tests, Kover verify, rules tests in the emulator,
   repository integration tests in the emulator. `CLAUDE.md` tells agents to run only this.
2. **Git hooks** (installed by Gradle task): pre-commit runs spotless and detekt on the
   changed modules, and pre-push runs the unit tests.
3. **CI (GitHub Actions)**, required checks on `main`:
   * `static`: spotless, detekt (no baseline growth), Android Lint (warnings are errors,
     MissingTranslation is an error)
   * `unit`: JVM tests + Kover verify
   * `firebase`: Firebase emulator (project `demo-listicles`, **no secrets needed**)
     → Jest rules tests + Kotlin data-layer integration tests
   * `ui`: Compose UI tests on an API 34 emulator (reactivecircus/android-emulator-runner)
     against the Firebase emulator; Roborazzi screenshot tests (JVM) in light/dark, en/da
   * `guards`: a script that fails on `@Ignore`/`@Disabled`/`xit`, a lowered coverage
     threshold, new detekt baseline entries, or changes to `.github/` or `scripts/`
     without a `tooling` label
4. **Branch protection** on `main`: PR required, all checks green, linear history,
   no force-push. You set this in GitHub settings (step-by-step guide in the
   foundation PR).
5. **Dependency hygiene**: Gradle version catalog, Dependabot, Gradle wrapper validation.

## 6. Review loop

1. The author session opens a small PR (one concern, target under about 400 changed lines),
   using a PR template that covers scope, test evidence, and screenshots for UI changes.
2. After CI is green, a **fresh Claude session** (no shared context) reviews the diff against
   `REVIEW.md`: correctness, security rules, test adequacy (do the tests fail when the
   code is wrong?), offline/sync behavior, i18n, accessibility, free-tier cost.
   Each finding is labeled `blocker | major | minor | nit`.
3. The author fixes everything above nit and pushes, then the reviewer re-reviews the new commits.
4. When only nits remain, the reviewer posts a "ready (nits only)" summary and you merge.

Each review round runs in a **new** reviewer session, so the reviewer never sees the
author's reasoning. It gets only the diff, the PR description, `REVIEW.md`, and the
previous round's open findings.

## 7. Milestones (each one is one or more PRs, each reviewed)

| # | Scope | Done when |
|---|---|---|
| M0 | **Foundation**: agent setup (section 9: role prompts, `.claude/` settings, status line, handoff template, metrics script) + Gradle multi-module skeleton, version catalog, spotless/detekt/lint/Kover, `verify.sh`, hooks, CI workflows, Firebase emulator config + an empty rules test, REVIEW.md, CLAUDE.md, PR template, branch-protection guide | All CI jobs run green on a hello-world app plus a trivial test, and a test that's deliberately broken makes CI fail |
| M1 | Auth + households: Google sign-in, create household, invite code/link, join, leave; rules + tests | Two emulator users can join one household, and an outsider is denied (rules tests) |
| M2 | Inventory lists: CRUD lists and items, real-time sync, offline, search/sort/filter, en/da | A UI test shows an edit on client A appearing on client B through the emulator |
| M3 | Packing domain: scaling + merging in `core/domain` with property tests | Coverage floor met, and all invariants are property-tested |
| M4 | Packing UI + trips: template editor with rule editor, "create trip" (select templates + days), trip checklist, one-off items | End-to-end UI test from templates to a trip with the expected amounts |
| M5 | Barcode: CameraX + ML Kit scanning, UPCitemdb lookup with a mocked HTTP test (MockWebServer), duplicate warning | Scanner logic tested with an injected fake decoder, and lookup failure falls back to manual entry |
| M6 | Release: signed APK on tag → GitHub Release; Play internal-track workflow (disabled) | Tag `v0.1.0` produces an installable signed APK |

## 8. What the owner needs to do (no code)

* Create a Firebase project (Spark plan) and enable Google sign-in and Firestore.
  Add `google-services.json` as a GitHub secret (CI tests use the emulator and don't need it).
* Register the debug and release SHA-1 fingerprints in Firebase.
* Create a release keystore and add it to GitHub secrets (M6).
* Turn on branch protection using the guide from M0.
* Later: a Play developer account if you want the Play track.

## 9. Agents, effort levels and token budget

### 9.1 Roles

| Role | Model / effort | Runs as | Gets | Produces |
|---|---|---|---|---|
| **Orchestrator** | Sonnet / low | One long-lived session | `PLAN.md`, `docs/status.md`, child-session summaries | Spawns sessions, updates status, asks the owner for merges and decisions |
| **Planner** | Opus / high | Fresh session, once per milestone | `PLAN.md`, the milestone, the relevant code | `docs/milestones/Mx.md`: PR breakdown, acceptance tests per PR |
| **Implementer** | Sonnet / medium | Fresh session per PR | Its PR's section of `Mx.md`, `CLAUDE.md` | Branch + PR; tests written first; `verify.sh` green |
| **Reviewer** | Opus / high | Fresh session per review round | Diff, PR description, `REVIEW.md`, previous findings | Findings labeled `blocker / major / minor / nit`, with the file and line |
| **Explorer** (subagent) | Haiku / low | Subagent inside an implementer or reviewer | A narrow question | File paths and short excerpts, no dumps |
| **CI triage** (subagent) | Haiku / low | Subagent inside an implementer | Failing job log | The failing test or rule and the minimal error |

Escalation rules (written down so agents don't decide on their own):
* An implementer that fails `verify.sh` 3 times on the same error, or gets 2 review
  rounds with blockers, hands off to a fresh implementer at **high** effort.
* Security rules, sync and merge logic, and the release workflow are tagged `risk:high`
  in `Mx.md`. Their implementers run at high effort, and their review runs at max effort.
* De-escalation (lower effort or a cheaper model for a role) happens only through the
  metrics retro (section 9.4), never ad hoc.

Role definitions are checked in, so they get reviewed and versioned like code:
* `.claude/agents/explorer.md` and `.claude/agents/ci-triage.md`: subagent definitions,
  with model and effort in their frontmatter.
* `agents/prompts/{orchestrator,planner,implementer,reviewer}.md`: opening prompts for the sessions.
* `agents/roles.yaml`: the single source of truth for each role's model, effort and token budget.

### 9.2 Token-saving rules (in CLAUDE.md)

* Read files in parts and search narrowly. Delegate broad searches to the Explorer.
* Never paste full CI logs. Use CI triage, or the `verify.sh` summary, which prints only failures.
* `verify.sh` has quiet output by default (one line per step, plus failure details).
* One PR = one concern, about 400 lines or fewer. Smaller diffs mean cheaper reviews.
* Reviewers don't re-run the whole suite. They rely on the CI result and only run
  targeted tests when a finding needs proof.
* The orchestrator never reads child transcripts. It reads only the final summary
  (fixed format: status, PR link, open items, tokens used).

### 9.3 Context limits and handoff

* **One PR per implementer session. One review round per reviewer session.**
* A status line shows the context % in every session.
* At **about 50%** context, the session finishes its current step, writes
  `handoff/<branch>.md` from a template, commits it, and ends.
  The template covers: goal, what's done, what's next, decisions made, open
  findings, and commands to resume. The orchestrator starts a fresh session with
  that file as input. `/compact` is only a fallback, e.g. in the middle of a step
  that can't be split.
* Handoff files are deleted in the PR's final commit, so they never reach `main`.
* The threshold warning comes from tooling, not memory: a status-line script plus a
  hook that injects a reminder once 50% is crossed. M0 checks the exact hook
  mechanism against the current Claude Code docs.

### 9.4 Performance reviews

`scripts/agent-metrics` pulls the sessions linked to each PR, using PR or branch
tags set at spawn time, and appends a row to `docs/agent-metrics.csv`:

| Metric | Why |
|---|---|
| Tokens (in/out/cache) per role per PR | Cost |
| Number of sessions and handoffs per PR | How well the context limit works |
| `verify.sh` failures before the first push, and CI red runs | Implementer quality |
| Review rounds; findings by severity | Implementer quality, and whether the reviewer is useful |
| Escaped defects: bugs found after merge, traced back to a PR (label `escaped`) | Reviewer quality, the most important signal |
| Reviewer false positives (findings the author rejected and a later round agreed) | Reviewer precision |

At the **end of each milestone**, a retro session (Sonnet / medium) reads only the CSV and
`docs/agent-tuning.md`. It proposes at most 3 changes, e.g. "drop the implementer to
low effort for UI-only PRs", "tighten REVIEW.md section X". Each change comes as a
reviewed PR to `agents/roles.yaml` or the prompts, with the expected effect logged.
The next retro checks whether that effect happened, and reverts the change if not.

Guardrail: quality metrics take precedence over cost. A change that cuts tokens but
raises escaped defects or blockers per PR gets reverted.

Starting budgets (calibrated after M0): implementer about 300k tokens/PR, reviewer
about 100k tokens per round, planner about 150k per milestone. Going over a budget
doesn't stop work. It flags the PR for the retro.
