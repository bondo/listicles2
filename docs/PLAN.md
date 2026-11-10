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
| Review | Every change is a PR → CI gates → a separate Claude session with no authoring context reviews it against `REVIEW.md` → fix and re-review until only nits remain (max 4 rounds per batch, then the owner decides) → the owner squash-merges |
| Repo | **Public** (unlimited free GitHub Actions minutes). No secrets in the repo; secrets live in GitHub secrets |

## 2. Repository layout

```
/app                  Android app (Compose UI, navigation, DI wiring)
/core/domain          Pure Kotlin/JVM: models, scaling, merging, search/sort/filter, validation
/core/data            Firestore + Auth repositories, mappers, UPC lookup client (Ktor/OkHttp)
/core/testing         Fakes (in-memory repositories), test fixtures
/firebase             firestore.rules, firestore.indexes.json, firebase.json, rules tests (Jest)
/docs                 PLAN.md, ORCHESTRATION.md, ARCHITECTURE.md, ADRs
/scripts              verify.sh and guard scripts used by CI and git hooks
REVIEW.md             Review rubric and severity definitions
CLAUDE.md             Agent instructions: the only commands to run, and the rules
```

`core/domain` has **no Android or Firebase dependencies**, so most logic gets fast JVM tests.

## 3. Data model (Firestore)

```
users/{uid}                      { householdId }                       // only readable by the user
households/{hid}                 { name, createdBy, createdAt, ownerUid, deleted: bool }
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
Notation: `get`/`exists` see the state **before** a batch, `getAfter`/`existsAfter`
see it **after**. `M(x)` means `exists(/households/$(hid)/members/$(x))`. `O(x)` means
`get(/households/$(hid)).data.ownerUid == x`. `LIVE` means
`get(/households/$(hid)).data.deleted == false`. Every rule below requires `LIVE` **except**
Create household (no doc exists yet) and Cleanup (which only applies when `deleted == true`).

**Reads**: members (`M(uid)`, `LIVE`) can read the household doc and everything under it.
`users/{uid}` can be read and written only by that user, and holds nothing but
`householdId`.

**Writes**, path by path:

| Path / action | Allowed when |
|---|---|
| Create household + owner (one batch) | Household: `!exists(household)`, `createdBy == ownerUid == uid`, `deleted == false`, **and** `existsAfter(members/uid)`. Member doc: `!exists(household)` **and** `getAfter(household).ownerUid == uid` **and** `role == owner`. Household docs are never deleted (see Delete household), so `!exists` can never be true again for an id that has existed. A former creator can't become owner again, and nobody can reclaim leftover data. |
| Create invite `invites/{code}` | `M(uid)` of `householdId`; `createdBy == uid`; `createdAt == request.time`; `expiresAt <= request.time + duration.value(7, 'd')`; `code.size() >= 16`. No updates. |
| Read one invite (`get`) | Any signed-in user (they need the code). |
| Query invites (`list`) | Only queries filtered on `householdId == hid` where `M(uid)`, so members can see and revoke their household's invites. Nobody can enumerate other codes. |
| Delete invite | Its creator or the owner (revoke); **any member** once `expiresAt < request.time` (cleanup); the joiner in the join batch (below). |
| Join (one batch) | Create `members/{uid}` with `role == member`, `joinedAt == request.time`, `viaInvite == code`, where: `!M(uid)` before the batch; the invite exists, points at `hid` and hasn't expired; the invite's creator is **still a member** (`M(invite.createdBy)`); **and** `!existsAfter(invites/{code})`, so the join is only valid if the same batch deletes the invite. That delete is allowed only if `!M(uid) && getAfter(member).viaInvite == code`, so an existing member can't burn someone else's invite. Single use follows from the delete. |
| Update own member doc | Only `displayName` may change. |
| Leave | A member who is not the owner (`!O(uid)`) deletes their own member doc. The client also deletes that member's invites (allowed: the creator may delete their own invites). |
| Remove member | `O(uid)`, and the target isn't the owner before **or after** the batch (`target != getAfter(household).data.ownerUid`), so a batch can't hand ownership to someone and remove them at the same time. The same batch deletes the removed member's open invites. Even if that cleanup is skipped, the `M(invite.createdBy)` check makes those invites unusable while the person is not a member. Accepted residual risk: if they rejoin through someone else's link, any of their old invites that haven't expired (7 days at most) start working again. |
| Transfer ownership (one batch) | Updates `household.ownerUid` and the `role` of both member docs. Household update: `O(uid)`, only `ownerUid` changes, and the new owner is a member both before and after the batch (`M(new)` and `existsAfter(members/new)`). Each member-doc update: only `role` changes, `O(uid)` before the batch, and the new role equals `getAfter(household).ownerUid == thisDoc ? owner : member`. `ownerUid` is the single source of truth, so there is always exactly one owner. `role` is a cached copy for display, and rules use `O(x)`. |
| Lists and items | `M(uid)` plus field validation (below). |
| Delete household | `O(uid)`. **Soft delete**: first one update sets `deleted: true`. This update may change only `deleted` (false → true) and `name` (→ empty); `ownerUid`, `createdBy` and `createdAt` stay as they are. From that moment `LIVE` is false, so every read and write under the household is denied to everyone except the owner's cleanup. Then the client deletes items → lists → invites → members in pages. **Cleanup rule**: while `deleted == true`, the owner (`O(uid)`) may read, list (including the invites query on `householdId`) and delete everything under the household; nobody else may do anything. The household doc itself stays as a tombstone (`{ createdBy, createdAt, ownerUid, deleted: true, name: "" }`; field validation accepts the empty name only on tombstones), so its id can never be reused. A crash mid-cleanup leaves data no one can access, and the next app start resumes the cleanup. |

Rules can't count members, so "the owner can't leave while others remain" is
enforced by the rule shapes above: the owner can't use Leave, so they must transfer
ownership or delete the household.

**Spike first (M1, PR 1)**: prove in the emulator that (a) the invite `list` rule,
filtered on `householdId` with a membership `exists()`, is accepted, (b) the join
batch with `existsAfter`/`getAfter` works, and (c) the transfer batch works. If (a)
fails, the fallback is to nest invites under the household, with a top-level
`inviteCodes/{code} → hid` index used only for `get`.

**Field validation** on every write:
* types, string lengths and allowed enum values;
* rule invariants: `amount >= 0`, `extra >= 0`, `1 <= perNights <= 365`,
  `min <= max`, `1 <= nights <= 365`, `1 <= travellers <= 50`;
* `updatedBy == request.auth.uid` and `updatedAt == request.time`;
* `createdAt` can't change.

**Account deletion** (required by Google Play): in-app "Delete my account". A member
leaves; an owner with other members must transfer ownership first, and the UI
guides them; a last member deletes the household. Then the app deletes
`users/{uid}` and the Auth user. If Firebase demands a recent sign-in
(`FirebaseAuthRecentLoginRequiredException`), the app asks the user to sign in
again first.

**Expired invites**: a member's app queries its household's invites when the household
screen opens and deletes the expired ones. TTL policies are not relied on.

**App Check** (Play Integrity, free) is turned on before the first release, as extra
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

**Pipeline** for each item. Every step uses `Math.addExact`/`multiplyExact`, and
inputs are bounded by validation (`nights <= 365`, `travellers <= 50`, `amount`,
`extra`, `min`, `max` <= 999):

1. **Base**: `FIXED` → `amount`; `PER_NIGHTS` → `amount * ceilDiv(nights, perNights)`,
   where `ceilDiv(a, b) = (a + b - 1) / b`. For example 1 per night is `perNights = 1`,
   and 1 shampoo per 7 nights is `perNights = 7`.
2. `+ extra` (`extra >= 0`).
3. Clamp to `[min, max]` when set. `min`, `max` and `extra` apply **per person**, because
   a rule describes what one traveller needs.
4. If the template is `perPerson`: `× travellers`.
5. Within one template, duplicate match keys are **summed**: they are the same item,
   entered twice.
6. Across templates, group by match key and take the **max**.
7. Final cap at 9,999, applied after the max. The cap **can** be hit with extreme inputs,
   and the UI shows "9,999+". All intermediate steps use `Long` with
   `addExact`/`multiplyExact`, so nothing overflows before the cap.

**Merging**: `combine(templates, nights, travellers): List<TripItem>` applies the pipeline.
* When keys collide, the display name and `sortKey` come from the template that is first
  in the user's selection order. Notes and tags are unioned. Source templates are recorded.
* Output order is deterministic: by first template's `sortKey`, then by name.

**Match key** (`CatalogKey`):
1. Unicode NFC normalization.
2. Remove invisible format and control characters: zero-width space, BOM, and also ZWJ
   and ZWNJ, which is intentional for item names, even though it merges some emoji
   sequences.
3. Collapse every Unicode whitespace, including NBSP and U+0085, into one space; trim.
4. `lowercase(Locale.ROOT)`, then NFC again.

Æ/Ø/Å are kept, so "bær" ≠ "baer".

**Search, sort and filter**: pure functions over item lists (text match on name, notes
and barcode, using the same normalization; tag filter; sort by name, created or updated).

Testing:
* Kotest + JUnit5.
* **Property-based tests** with Unicode-aware generators (not just ASCII). Invariants:
  * quantities don't depend on template order or grouping: combining in any
    permutation gives the same quantities per key;
  * each result is at least `min(input quantity, 9,999)` for every input with that key;
  * combining a template with itself changes nothing;
  * results never decrease as nights or travellers increase;
  * results are never negative and never exceed 9,999. Scaling is checked against a `BigInteger` reference
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
     and `ExtraTranslation` are errors, `HardcodedText` is an error). `targetSdk`
     follows `compileSdk`; if they differ, `OldTargetApi` is disabled with a
     `// justified:` comment rather than failing the build silently. Detekt: M0
     evaluates detekt 2.x, which supports Kotlin 2.4 and type resolution
     (`detektMain`/`detektTest`). If it isn't stable enough, M0 stays on 1.23
     without type resolution and records that gap in an ADR.
   * Danish and English plural strings use `<plurals>`, with a unit test per locale
     for 0, 1 and many.
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
3. Findings are posted as one PR comment containing a JSON block (format in
   `REVIEW.md`; `docs/ORCHESTRATION.md` §7.2 says how it is used): each finding has a stable ID (`R1-03`; rounds are
   numbered per PR and never reset per batch), a severity (`blocker | major | minor | nit`), a file and line,
   and a status (`open | fixed | disputed | withdrawn`). This makes the round-over-round
   metrics in section 9.4 possible.
4. The author fixes everything above nit, or marks it `disputed` with a reason, and pushes.
5. Each later round runs in a **new** reviewer session that sees only the commits since the
   last round, the open findings, and `REVIEW.md`. It re-checks open findings and reviews
   the new code. It doesn't re-review unchanged code, so the loop converges.
6. When only nits remain, the reviewer posts "ready (nits only)" and you squash-merge.
   If round 4 of a batch still has findings above nit, the loop stops and you decide.

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
| **Orchestrator** | Sonnet / low | One long-lived session | `PLAN.md`, `docs/ORCHESTRATION.md`, the state issue, `WORKER-RESULT` blocks | Spawns sessions, updates the state issue, asks the owner for merges and decisions (autonomy rules: `docs/ORCHESTRATION.md` §1.1); never commits |
| **Planner** | Opus / high | Fresh session, once per milestone | `PLAN.md`, the milestone, the relevant code | `docs/milestones/Mx.md`: PR breakdown, acceptance tests per PR; the PR-sized tasks with dependencies in `docs/tasks.toml` |
| **Implementer** | Sonnet / medium | Fresh session per PR | Its PR's section of `Mx.md`, `CLAUDE.md` | Branch + PR; tests written first; `verify.sh` green |
| **Reviewer** | Opus / high | Fresh session per review round | Diff, PR description, `REVIEW.md`, previous findings | Findings labeled `blocker / major / minor / nit`, with the file and line; never edits or pushes to the PR branch (`docs/ORCHESTRATION.md` §7.2) |
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
  (the `WORKER-RESULT` block, `docs/ORCHESTRATION.md` §7.3); tokens and cost come from
  `get_session`, not from the worker.

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
* The orchestrator follows the same rule, but it never commits: its state lives in the state issue
  and it hands over with the checklist in `docs/ORCHESTRATION.md` §5.
* The threshold warning comes from tooling, not memory: a status-line script plus a
  hook that injects a reminder once 50% is crossed. M0 checks the exact hook
  mechanism against the current Claude Code docs.

### 9.4 Performance reviews

Each metric must have a data source proven in M0; a metric whose source can't be
proven is dropped, not guessed. The candidate sources are a SessionEnd hook that
writes token usage from the transcript to `metrics/sessions/<id>.json`, the
reviewer's JSON findings comment, and `get_session` → `external_metadata.usage` (cost and
tokens per session; confirmed to work on 2026-11-10). Until the script exists, rows are logged on the
state issue in the format of `docs/ORCHESTRATION.md` §6.

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
