# Listicles – Implementation Plan

Android app for shared household lists (inventories such as DVDs, and packing lists
that combine into scaled trip checklists). Changes sync in real time between members.

## 1. Decisions

| Area | Decision |
|---|---|
| Client | Kotlin + Jetpack Compose, single Activity, MVVM + unidirectional state, Hilt DI |
| Backend | Firebase (Spark/free): Auth (Google sign-in via Credential Manager) + Cloud Firestore. **No Cloud Functions** (they need the paid Blaze plan), so all integrity checks live in security rules |
| Sync | Firestore snapshot listeners; offline cache on; one document per item; updates write only the changed fields; same-field conflicts resolve last write wins |
| Sharing | Households: every list belongs to a household; members join through a **single-use invite link** (random code of 16+ characters, expires after 7 days, can be revoked) |
| Inventory lists | Generic items (name, notes, quantity, tags, optional barcode) with search, sort and filter |
| Barcode | Google ML Kit barcode scanning (on-device, free) + CameraX |
| Title lookup | `ProductLookup` interface; first implementation is the UPCitemdb trial (no key, ~100/day per IP); manual entry if the lookup fails; the result is always editable. Terms of use recorded in an ADR |
| Packing scaling | Trip length in **nights**. Per-item rule: `FIXED` or "`amount` per `perNights` nights", with optional `extra`, `min`, `max`; whole numbers only |
| Packing merge | Items matched by normalized name (computed when merging); **max** wins. Templates marked **per person** are multiplied by the number of travellers before the max |
| Trips | Generating a trip creates a **snapshot** checklist (amount, packed flag, one-off additions); later template edits don't change it |
| i18n | English + Danish; all strings in resources; CI fails on missing translations |
| AI at runtime | No AI code apart from on-device ML Kit. No LLM or cloud AI calls |
| Distribution | Signed APK on GitHub Releases on each `v*` tag; Play internal-testing pipeline prepared but turned off until the $25 account exists |
| Review | Every change is a PR → CI gates → a separate Claude session with no authoring context reviews it against `REVIEW.md` → fix and re-review until only nits remain (max 4 rounds, then the owner decides) → the owner squash-merges |
| Repo | **Public** (unlimited free GitHub Actions minutes). No secrets in the repo; secrets live in GitHub secrets |

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
users/{uid}                      { householdId }                       // only readable by the user
households/{hid}                 { name, createdBy, createdAt }
households/{hid}/members/{uid}   { role: owner|member, displayName, joinedAt, viaInvite? }
invites/{code}                   { householdId, createdBy, createdAt, expiresAt }
households/{hid}/lists/{lid}     { kind: INVENTORY|PACKING_TEMPLATE|TRIP, name, createdAt, updatedAt,
                                   perPerson?: bool,                                   // templates
                                   trip?: { nights, travellers, sourceListIds[], generatedAt } }
households/{hid}/lists/{lid}/items/{iid}
   { name, notes, tags[], quantity, barcode?, sortKey, createdAt, updatedAt, updatedBy,
     rule?: { kind: FIXED|PER_NIGHTS, amount, perNights, extra, min?, max? },  // templates
     packed?: bool }                                                          // trips
```

The match key used for merging is **not stored**. It is computed from `name` when lists
are combined, so a later change to the normalization rules can't break existing data.

### 3.1 Security rules (no Cloud Functions, so everything is enforced here)

Every rule below gets at least one allow test and one deny test in the emulator.

* **Read/write household data** only if `households/{hid}/members/{request.auth.uid}` exists.
* **Create a household**: one batched write creating `households/{hid}` with
  `createdBy == uid` and `members/{uid}` with `role == owner`. The member rule checks
  `getAfter(household).data.createdBy == uid`, so nobody can create an owner record
  for a household they didn't create in the same batch.
* **Create an invite**: only a member of `householdId`; `createdBy == uid`;
  `createdAt == request.time`; `expiresAt <= request.time + 7d`; code is at least 16
  characters (the client generates 16+ random characters from a 32-symbol
  alphabet, about 80 bits). **No updates.** `get` is allowed for signed-in users who know
  the code; `list` is denied, so codes can't be enumerated.
* **Join**: in one batch, create `members/{uid}` with `role == member`,
  `joinedAt == request.time`, `viaInvite == code`, where the invite exists, points at
  `hid` and hasn't expired, **and** delete `invites/{code}` (checked with
  `getAfter` / `existsAfter`). That makes links single use.
* **Revoke an invite**: its creator or the owner deletes it.
* **Leave**: a member deletes their own member doc. The owner can't leave without
  transferring ownership first, unless they are the last member, in which case
  they delete the household (see below).
* **Remove a member / transfer ownership**: owner only. Transfer is a batch that sets
  the new owner and demotes the old one.
* **No self-promotion**: members can update only `displayName` on their own member doc.
* **Field validation** on every write: types, string lengths, allowed enum values, rule
  invariants (`amount >= 0`, `perNights >= 1`, `min <= max`, `nights >= 1`,
  `travellers >= 1`), `updatedBy == request.auth.uid`, `updatedAt == request.time`,
  and `createdAt` can't change.
* **Deletion**: Firestore doesn't delete subcollections automatically, so the client
  deletes in pages (items, then lists, then members, then the household). The rules
  allow the owner to do this.
* **Account deletion** (required by Google Play): in-app "Delete my account" leaves the
  household (or deletes it if this is the last member), deletes `users/{uid}`, then
  deletes the Firebase Auth user.
* **Expired invites**: a member's app deletes its household's expired invites when it
  opens the household screen. TTL policies are not relied on.
* **App Check** (Play Integrity, free) is turned on before the first release, as extra
  protection against scripted abuse.

### 3.2 Sync semantics

* Writes use `update()` on specific fields, never `set(merge)`. An offline edit to an
  item that was deleted meanwhile fails instead of bringing the item back; the UI
  shows "this item was removed".
* Quantity +/- buttons use `FieldValue.increment`, so concurrent "+1"s both count.
  Typing an exact number is last write wins.
* Timestamps use `serverTimestamp()`. They are read with
  `ServerTimestampBehavior.ESTIMATE` so pending local writes still sort correctly.
* Tests: emulator integration tests for concurrent increments, an edit racing a
  delete, and offline-then-reconnect (`disableNetwork` / `enableNetwork`).

### 3.3 Free-tier budget

* One snapshot listener per open list, detached when the screen closes, so items
  are served from the local cache when you go back. Search, sort and filter run
  on the client over that listener's data. Lists are capped at 2,000 items
  (enforced by the UI and documented).
* Estimate: 10 users, each opening 5 lists a day, 300 items per list, is about
  15k reads a day, under the 50k limit. The data-layer PR for M2 must include a
  read-cost estimate per screen.
* GitHub Actions: the repo is public, so minutes are unlimited.

## 4. Domain logic (core/domain)

All arithmetic uses whole numbers (`Int`/`Long`). No floating point anywhere in the domain.

**Scaling**: `quantityFor(rule, nights)`, where `nights >= 1`:
* `FIXED`: `amount`
* `PER_NIGHTS`: `amount * ceilDiv(nights, perNights)`, where
  `ceilDiv(a, b) = (a + b - 1) / b` (for example 1 per night is
  `perNights = 1`, and 1 shampoo per 7 nights is `perNights = 7`)
* then `+ extra`, then clamp to `[min, max]` when set. Overflow is guarded:
  results are capped at 9,999 and checked with `Math.multiplyExact`.

**Merging**: `combine(templates, nights, travellers): List<TripItem>`.
1. Scale each item. Items from a `perPerson` template are multiplied by `travellers`.
2. Within one template, duplicate names are summed: they are the same item, entered twice.
3. Across templates, group by match key and take the **max**.
4. Notes and tags are unioned. Source templates are recorded. Output order is
   deterministic: by first template's `sortKey`, then by name.

**Match key** (`CatalogKey`): Unicode NFC normalization, trim, collapse every Unicode
whitespace including NBSP, then `lowercase(Locale.ROOT)`. Æ/Ø/Å are kept, so
"bær" ≠ "baer".

**Search, sort and filter**: pure functions over item lists (text match on name, notes
and barcode, using the same normalization; tag filter; sort by name, created or updated).

Testing:
* Kotest + JUnit5.
* **Property-based tests** with Unicode-aware generators (not just ASCII). Invariants:
  merge is commutative and associative; the result is at least each input; merging
  a template with itself changes nothing; results never decrease as nights or
  travellers increase. Scaling is checked against a `BigInteger` reference
  implementation.
* **Mutation testing** (PIT) on `core/domain`, so tests without real assertions
  can't satisfy the coverage gate. The mutation score floor is 85%.
* Kover floors: **95% line and 90% branch on core/domain**, 80% overall across
  `domain`, `data` and `app` (generated and Compose preview code excluded).

## 5. Tooling-first process (guardrails)

The goal: an agent (or a person) *cannot* merge something broken, because tools
enforce the rules rather than goodwill.

1. **One entrypoint**: `./scripts/verify.sh` runs exactly what CI runs: spotless,
   detekt, Android Lint, unit tests, Kover verify, rules tests in the emulator,
   repository integration tests in the emulator. Output is quiet by default: one
   line per step, plus details only for failures. `CLAUDE.md` tells agents to run
   only this.
2. **Git hooks** (installed by `scripts/install-hooks.sh`, which a session-start hook
   runs automatically): pre-commit runs spotless and detekt on the changed modules,
   and pre-push runs the unit tests.
3. **Claude Code hooks** in `.claude/settings.json`, which agents can't skip:
   * PreToolUse denies `git commit --no-verify`, `git push --force`, `git reset --hard`
     on shared branches, and pushes to `main`.
   * PreToolUse denies agent edits to the process files: `CLAUDE.md`, `REVIEW.md`,
     `agents/`, `.claude/`, `scripts/guards.sh` and `.github/`, unless the session
     was started for a `tooling` task (an environment flag set at spawn).
   * A context-% warning (section 9.3).
4. **CI (GitHub Actions)**, required checks on `main`:
   * `static`: spotless, detekt, Android Lint (warnings are errors, `MissingTranslation`
     and `ExtraTranslation` are errors, `HardcodedText` is an error)
   * `unit`: JVM tests + Kover verify + PIT on `core/domain`
   * `firebase`: Firebase emulator (project `demo-listicles`, **no secrets needed**)
     → Jest rules tests + Kotlin data-layer integration tests
   * `ui`: Compose UI tests on an API 34 emulator against the Firebase emulator,
     with accessibility checks turned on (`enableAccessibilityChecks`: touch target
     size, contrast, content descriptions). Roborazzi screenshot tests (JVM) in
     light/dark × en/da.
   * `guards` (`scripts/guards.sh`) fails on:
     * `@Ignore`, `@Disabled`, `xit`, `.only`
     * `@Suppress`, `tools:ignore`, `ktlint-disable`, `detekt:` suppressions, or
       `lint.disable` / `.editorconfig` rule-offs, unless the line carries
       `// justified: <reason>` (the reviewer checks these)
     * any detekt or lint baseline file
     * a lowered `minBound`, PIT threshold or lint severity, by comparing against `main`
     * changed screenshot reference images, unless the PR has the `golden-update` label
     * a diff over 600 changed lines outside generated files
   * `secrets`: gitleaks
   * Unit tests run with network access blocked (a JUnit extension that fails if a
     socket opens), so tests can't silently depend on the internet.
5. **CODEOWNERS**: the owner is required reviewer for `.github/`, `scripts/`, `.claude/`,
   `agents/`, `CLAUDE.md`, `REVIEW.md`, `firebase/firestore.rules`, and screenshot
   reference images. Labels that agents could set themselves are not trusted on
   their own; CODEOWNERS is the real control.
6. **Branch protection** on `main`: PR required, all checks green, CODEOWNERS review
   required, **squash merge only**, no force-push. You set this in GitHub settings
   (step-by-step guide in the foundation PR).
7. **Dependency hygiene**: Gradle version catalog, Dependabot, Gradle wrapper validation.

## 6. Review loop

1. The author session opens a small PR (one concern, target under about 400 changed lines),
   using a PR template that covers scope, test evidence, and screenshots for UI changes.
2. After CI is green, a **fresh Claude session** (no shared context) reviews the diff against
   `REVIEW.md`: correctness, security rules, test adequacy (do the tests fail when the
   code is wrong?), offline/sync behavior, i18n, accessibility, free-tier cost, and
   every `// justified:` suppression.
3. Findings are posted as one PR comment containing a JSON block: each finding has a
   stable ID (`R1-03`), a severity (`blocker | major | minor | nit`), a file and line,
   and a status (`open | fixed | disputed | withdrawn`). This makes the round-over-round
   metrics in section 9.4 possible.
4. The author fixes everything above nit, or marks it `disputed` with a reason, and pushes.
5. Each later round runs in a **new** reviewer session that sees only the commits since the
   last round, the open findings, and `REVIEW.md`. It re-checks open findings and reviews
   the new code. It doesn't re-review unchanged code, so the loop converges.
6. When only nits remain, the reviewer posts "ready (nits only)" and you squash-merge.
   If round 4 still has findings above nit, the loop stops and you decide.

## 7. Milestones (each one is one or more PRs, each reviewed)

| # | Scope | Done when |
|---|---|---|
| M0 | **Foundation**: agent setup (section 9: role prompts, `.claude/` settings, status line, handoff template, metrics script) + Gradle multi-module skeleton, version catalog, spotless/detekt/lint/Kover, `verify.sh`, hooks, CI workflows, Firebase emulator config + an empty rules test, REVIEW.md, CLAUDE.md, PR template, branch-protection guide | All CI jobs run green on a hello-world app plus a trivial test, and a test that's deliberately broken makes CI fail |
| M0.5 | **Product design** (no code): user stories with acceptance criteria (`docs/product/stories.md`), app-flow diagram (`docs/product/flow.md`, Mermaid), screen wireframes and design tokens (colors, type, spacing, dark mode) published as an artifact for review | You approve stories, flow and design. Each later milestone's acceptance tests are traced to story IDs |
| M1 | Auth + households: Google sign-in, create household, single-use invite link, join, leave, remove member, transfer ownership, delete account; rules + tests | Two emulator users can join one household, and an outsider is denied (rules tests) |
| M2 | Inventory lists: CRUD lists and items, real-time sync, offline, search/sort/filter, en/da | A UI test shows an edit on client A appearing on client B through the emulator |
| M3 | Packing domain: scaling, per-person templates and merging in `core/domain`, with property tests and PIT | Coverage and mutation floors met, and all invariants are property-tested |
| M4 | Packing UI + trips: template editor with rule editor, "create trip" (select templates, nights and travellers), trip checklist, one-off items | End-to-end UI test from templates to a trip with the expected amounts |
| M5 | Barcode: CameraX + ML Kit scanning, UPCitemdb lookup with a mocked HTTP test (MockWebServer), duplicate warning | Scanner logic tested with an injected fake decoder, and lookup failure falls back to manual entry |
| M6 | Release: signed APK on tag → GitHub Release; Play internal-track workflow (disabled) | Tag `v0.1.0` produces an installable signed APK |

## 8. What the owner needs to do (no code)

* Create a Firebase project (Spark plan) and enable Google sign-in and Firestore.
  Add `google-services.json` as a GitHub secret (CI tests use the emulator and don't need it).
* Register the debug and release SHA-1 fingerprints in Firebase.
* Create a release keystore and add it to GitHub secrets (M6).
* Make the repository public (decided: unlimited free Actions minutes).
* Add yourself as CODEOWNER (the M0 PR adds the file; you confirm the handle).
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
* Handoff files are deleted in the PR's final commit. Because merges are squash-only, they never reach `main`'s history.
* The orchestrator follows the same rule: at about 50% it writes `handoff/orchestrator.md` (milestone, open PRs, waiting-on-owner items) and a fresh orchestrator continues from it.
* The threshold warning comes from tooling, not memory: a status-line script plus a
  hook that injects a reminder once 50% is crossed. M0 checks the exact hook
  mechanism against the current Claude Code docs.

### 9.4 Performance reviews

Each metric must have a data source proven in M0; a metric whose source can't be
proven is dropped, not guessed. The candidate sources are a SessionEnd hook that
writes token usage from the transcript to `metrics/sessions/<id>.json`, and the
reviewer's JSON findings comment.

`scripts/agent-metrics` pulls the sessions linked to each PR, using PR or branch
tags set at spawn time, and appends a row to `docs/agent-metrics.csv`:

| Metric | Why |
|---|---|
| Tokens (in/out/cache) per role per PR | Cost |
| Number of sessions and handoffs per PR | How well the context limit works |
| `verify.sh` failures before the first push, and CI red runs | Implementer quality |
| Review rounds; findings by severity | Implementer quality, and whether the reviewer is useful |
| Escaped defects: bugs found after merge, traced back to a PR (label `escaped`, which you or the agent that finds the bug sets, with a link to the PR) | Reviewer quality, the most important signal |
| Reviewer false positives: findings marked `disputed` and then `withdrawn` (from the JSON findings) | Reviewer precision |

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
