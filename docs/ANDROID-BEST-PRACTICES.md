# Android best practices checklist

Owner rule (issue #15, 2026-11-12): from M1 on, product code follows Google's Android guidance. Implementers cite this
file in their prompts, reviewers check against it (`REVIEW.md` item 11), and a deviation needs a recorded decision
(an ADR in `docs/adr/` or a `decision` comment on the state issue). **Status: draft, the owner approves it before M1.**

Every item below was taken from a page that was fetched and read on 2026-11-12. Priorities in the architecture
section ("strongly recommended" and so on) are Google's own labels. Google says these are recommendations, not strict requirements.

**Status column**
- `tooling`: a check in `scripts/verify.sh` and CI fails when it is broken (what the check covers is stated).
- `review`: no tool checks it; the reviewer does.
- `later`: not applicable until the code exists (the milestone is stated), then `review` unless a follow-up automates it.

Facts about this repo were read from `build.gradle.kts`, `app/build.gradle.kts`, `gradle.properties`,
`config/detekt/detekt.yml`, `scripts/verify.sh`, `docs/PLAN.md` and `REVIEW.md` on `main` at `99e4d4c`.
Konsist rules (M0.5-11, PR #59) are **not on main yet**, so they count as `later`.

## 1. Architecture
Sources: [Guide to app architecture](https://developer.android.com/topic/architecture) and
[Architecture recommendations](https://developer.android.com/topic/architecture/recommendations).

| Rule | Status |
|---|---|
| UI layer (Compose + ViewModel state holders) and data layer (repositories over data sources); domain layer only when logic is shared or complex ("recommended in big apps") | review (M1) |
| Composables and ViewModels never touch a data source (Firestore, DataStore, ...) directly; only repositories do | review (M1); Konsist rule proposed, see follow-ups |
| Single source of truth per data type: the owner exposes immutable types and takes events or function calls to change them | review (M1) |
| Unidirectional data flow: state down, events up | review (M1) |
| ViewModel at screen level only; no `Context`, `Activity`, `Resources` or `AndroidViewModel` in it; `ViewModel` instances are not passed down to child composables (State hoisting page) | review (M1) |
| Expose one `uiState: StateFlow<...>` (`stateIn(..., WhileSubscribed(5_000), ...)` for streams); `MutableStateFlow` stays private | review (M1) |
| Collect with `collectAsStateWithLifecycle`; do not send one-off events from the ViewModel to the UI, update state instead | review (M1) |
| Reusable UI components use plain state holder classes, not ViewModels | review (M1) |
| Dependency injection, constructor injection first; Hilt when the app has several screens with ViewModels (PLAN section 1 already chooses Hilt) | later (M1) |
| Pure-Kotlin domain code with no Android classes | tooling in part: `core/domain` is its own JVM module; the no-float rule is Konsist (later, M0.5-11) |
| Use Jetpack libraries instead of hand-written boilerplate | review |

## 2. Jetpack Compose
Sources: [State hoisting](https://developer.android.com/develop/ui/compose/state-hoisting),
[Stability](https://developer.android.com/develop/ui/compose/performance/stability),
[Previews](https://developer.android.com/develop/ui/compose/tooling/previews),
[API guidelines](https://developer.android.com/develop/ui/compose/api-guidelines).

| Rule | Status |
|---|---|
| Hoist state to the lowest common ancestor that reads or writes it; pass immutable state and event lambdas down. Purely internal UI-element state may stay inside the composable | review |
| A screen has two composables: a stateful one that gets the ViewModel and a stateless one that takes state and events, so the stateless one can be previewed and tested | review |
| Stability: with Kotlin 2.0.20+ strong skipping is on by default, so do not add `@Stable` or `@Immutable` or immutable-collection wrappers without a measured problem; do not allocate new instances of unstable parameters on every recomposition | review; compiler reports proposed |
| Previews for every stateless screen and component, using multipreview (`@PreviewLightDark`, `@PreviewFontScales`) and a `locale` preview for Danish; previews cannot build ViewModels | review |
| Follow the Compose API guidelines (naming, `modifier` parameter, Kotlin style) | tooling in part: spotless and ktlint, detekt `FunctionNaming` with `Composable` exempted; the rest `review` |

## 3. Navigation
Sources: [Navigation in Compose](https://developer.android.com/develop/ui/compose/navigation) and the "single-activity"
row of the architecture recommendations above. Single Activity is already in PLAN section 1.

| Rule | Status |
|---|---|
| Single Activity; screens are destinations; routes are serializable types (type safe) | later (M1) |
| **Owner decision 2026-11-13: Navigation 3.** The architecture recommendations page names it for multi-screen apps (the Navigation page documents Navigation Compose 2.x, so the Navigation 3 docs must be read before M1 navigation work) | later (M1) |
| Handle back with `BackHandler` or `PredictiveBackHandler`, not `onBackPressed` or `KEYCODE_BACK`; state-driven enabled flag | review (M1) |

## 4. Data and offline-first
Source: [Offline-first](https://developer.android.com/topic/architecture/data-layer/offline-first).

| Rule | Status |
|---|---|
| Reads come from the local source and are observable (`Flow`); writes are `suspend` functions | review (M1) |
| The page names Cloud Firestore as a managed offline cache (disk cache, offline write queue, sync). This project uses it, so Room is **not** needed; a Room database would be a deviation that needs a decision | PLAN §1 decision; **owner confirmed 2026-11-13 (Q2): Firestore offline persistence only, no Room**; review |
| Keep network or Firestore document models internal to the data layer and expose a separate model to other layers | review (M1) |
| Model loading and errors as UI state (a sealed `Loading` / `Success` / `Error`) and catch flow errors in the ViewModel | review (M1) |

## 5. Concurrency
Source: [Coroutines best practices](https://developer.android.com/kotlin/coroutines/coroutines-best-practices).

| Rule | Status |
|---|---|
| Inject dispatchers; never hardcode `Dispatchers.*` in classes; tests use a `TestDispatcher` with `runTest` | review; detekt rule evaluation proposed |
| Suspend functions are main-safe: the class doing blocking work moves it with `withContext` | review |
| The ViewModel creates the coroutines; the data layer exposes `suspend` for one-shot calls and `Flow` for streams | review |
| No `GlobalScope`; work that must outlive a screen uses an injected external scope | review; detekt rule evaluation proposed |
| Structured concurrency (`coroutineScope` or `supervisorScope`); never swallow `CancellationException`; catch specific exceptions | review |

## 6. Testing
Sources: [Testing fundamentals](https://developer.android.com/training/testing/fundamentals),
[Test doubles](https://developer.android.com/training/testing/fundamentals/test-doubles),
[Compose testing](https://developer.android.com/develop/ui/compose/testing) and
[Architecture recommendations](https://developer.android.com/topic/architecture/recommendations).

| Rule | Status |
|---|---|
| At minimum: ViewModel unit tests including Flows, repository and data source tests, UI navigation tests as CI regression tests, and Macrobenchmark startup and rendering tests | tooling in part: unit tests and Kover floor 80 are in `verify.sh`; UI and benchmark tests `later` |
| Prefer fakes to mocks (fakes live in the test source set, named `Fake*`); assert on `StateFlow.value` | review (already REVIEW.md item 3) |
| Compose UI tests with `createComposeRule`, run against fake state (hermetic) | later (M1) |
| Screenshot tests and accessibility checks in UI tests | later: PLAN section 5 plans Roborazzi and `enableAccessibilityChecks`. The fetched Compose testing page does not mention screenshot tests, so this item has no Google source |

## 7. Accessibility
Sources: [Make apps more accessible](https://developer.android.com/guide/topics/ui/accessibility/apps),
[Accessibility principles](https://developer.android.com/guide/topics/ui/accessibility/principles).

| Rule | Status |
|---|---|
| Touch targets at least 48dp x 48dp for interactive elements (Material components already do this; custom ones must set it) | review now (REVIEW.md item 6); tooling later (UI accessibility checks) |
| Text contrast at least 4.5:1 (text under 18sp, or bold under 14sp) and 3:1 for other text | review now; tooling later |
| `contentDescription` for every icon button; `null` for decorative images; no "button" in the text; unique per list item | review now (Google says Android Lint, Compose tests and test tools can flag common issues; which lint checks fire here is not verified) |
| Use `Role`, `stateDescription`, `heading()`, `mergeDescendants` for groups; custom accessibility actions for swipe or drag gestures | review |
| Do not rely on colour alone; test with TalkBack | review |

## 8. Performance
Sources: [Baseline Profiles](https://developer.android.com/topic/performance/baselineprofiles/overview) and the performance rows of the architecture recommendations.

| Rule | Status |
|---|---|
| R8 on for release (`isMinifyEnabled = true`) | tooling in part: set in `app/build.gradle.kts`; nothing checks the release build runs, a release smoke build is proposed |
| Baseline Profile and Startup Profile, generated by Macrobenchmark, with the Baseline Profile Gradle plugin (generation builds must not be obfuscated) | later (before the first release; milestone to be set by the planner) |
| Macrobenchmark to catch startup and jank regressions | later |
| Defer state reads and avoid allocating in recomposition when a measured issue shows up | review |

## 9. Security and privacy
Sources: [Security best practices](https://developer.android.com/topic/security/best-practices),
[Network security config](https://developer.android.com/privacy-and-security/security-config),
[Auto Backup](https://developer.android.com/identity/data/autobackup).

| Rule | Status |
|---|---|
| Never commit API keys; keep them out of the source repository | tooling: `secrets` (gitleaks) CI job and the guards; `google-services.json` rule in CLAUDE.md |
| Cleartext traffic is off by default from API 28; do not opt in. Use a network security config only if a real need appears | review (a `cleartextTrafficPermitted="true"` is a finding) |
| Backup: the manifest sets `android:allowBackup="false"` today. If that is ever turned on, add `dataExtractionRules` and `fullBackupContent` rules that exclude device-specific data | review (manifest change) |
| Request the fewest permissions; validate input; keep data minimal (also Firestore rules, covered in REVIEW.md item 2) | review |
| Play Data safety form must match what the app collects | **not sourced**: its page is on `support.google.com`, which this session's proxy refuses (403). **Owner decision 2026-11-13: `support.google.com` stays blocked for now**, so this item remains not sourced and is not cited |

## 10. Play quality
Sources: [Target API requirement](https://developer.android.com/google/play/requirements/target-sdk),
[Window insets and edge-to-edge](https://developer.android.com/develop/ui/compose/layouts/insets),
[Predictive back](https://developer.android.com/guide/navigation/custom-back/predictive-back-gesture),
[Window size classes](https://developer.android.com/develop/ui/compose/layouts/adaptive/window-size-classes),
[Localization](https://developer.android.com/guide/topics/resources/localization).

| Rule | Status |
|---|---|
| From 2026-08-31 new apps and updates must target API 36 or higher. `targetSdk` is 37 | review (nothing fails if someone lowers it; guard proposed) |
| Edge-to-edge: handle `WindowInsets` (a `Scaffold` helps); it is enforced when targeting SDK 35+ | review |
| Predictive back: do not intercept back with `onBackPressed` or `KEYCODE_BACK`; do not opt out | review |
| Adaptive layouts by window size class (compact under 600dp, medium 600 to 840dp, expanded 840 to 1200dp, large 1200 to 1600dp, extra-large from 1600dp; large and extra-large need the `supportLargeAndXLargeWidth` opt-in); do not use "is tablet" logic; state survives configuration changes | review (M1+) |
| All strings in resources, with a complete default `values/strings.xml` and `values-da/` | tooling: lint `MissingTranslation` is an error and `warningsAsErrors` is on (`app/build.gradle.kts`); `<plurals>` and "no hardcoded text" are CLAUDE.md rules checked by review plus lint |
| Give translators context comments; mark non-translatable parts with `xliff:g` | review |

## 11. Dependency and Gradle hygiene
Source: [Version catalogs](https://developer.android.com/build/migrate-to-catalogs).

| Rule | Status |
|---|---|
| Dependencies and plugins only through `gradle/libs.versions.toml`, kebab-case names, `alias(libs.plugins...)` | tooling in part: the catalog exists; nothing fails a hardcoded `"group:name:version"`, a guard is proposed |
| Configuration cache and build cache on | tooling in part: set in `gradle.properties` |
| Kotlin style and formatting | tooling: spotless with ktlint, detekt with `maxIssues: 0`, Kotlin `allWarningsAsErrors` |
| Lint with warnings as errors | tooling: `:app:lintDebug` in `verify.sh` |
| Dependency freshness | Dependabot (lint freshness checks are disabled on purpose with a `// justified:`) |

## Proposed follow-ups (not implemented here)
Each would be its own PR, test-first, per CLAUDE.md.
1. **Konsist architecture rules** after M0.5-11: composables and ViewModels may not import Firestore, DataStore or Room types; ViewModels may not import `android.content.Context`, `Activity` or `AndroidViewModel`; no `GlobalScope`; no `Dispatchers.` outside the DI module.
2. **detekt coroutines rules** (`GlobalCoroutineUsage`, `InjectDispatcher`): evaluate whether they exist and are usable in detekt 1.23.8 before enabling.
3. **Guard for hardcoded dependency coordinates** in `*.gradle.kts` (everything must come from the catalog).
4. **Guard that `targetSdk` is at least the Play minimum** (36 until the date changes).
5. **Manifest guard**: fail on `usesCleartextTraffic="true"`, `cleartextTrafficPermitted="true"`, or `allowBackup="true"` without backup rules.
6. **Compose compiler stability report** as a CI artifact (no gate) once there are screens.
7. **Release smoke build** with R8 on, run in CI, once M1 has a release variant.
8. **Roborazzi and accessibility checks** are already in PLAN section 5; make sure their tasks cite sections 6 and 7 above.

## Owner decisions (2026-11-13)
1. Navigation 3 (section 3).
2. Firestore offline persistence only, no Room (section 4).
3. `support.google.com` is not allowed now; the Play Data safety item stays not sourced (section 9). Revisit if the owner changes the network setting.

No open questions remain; the checklist still needs the owner's approval before M1 (status line above).
