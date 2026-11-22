# Android best practices checklist

Owner rule (issue #15, 2026-11-12): from M1 on, product code follows Google's Android guidance. Implementers cite this
file in their prompts, reviewers check against it (`REVIEW.md` item 11), and a deviation needs a recorded decision
(an ADR in `docs/adr/` or a `decision` comment on the state issue). **Status: approved. Approved by the owner 2026-11-15; the issue 197 rows are re-approved by the owner's merge of PR #221.** Decision record: https://github.com/bondo/listicles2/issues/15#issuecomment-6898068569

Every item below was taken from a page that was fetched and read on 2026-11-12, except the Play Data safety item in section 9
(read 2026-11-15) and the issue 197 rows (read 2026-11-19, PR #221). Priorities in the architecture
section ("strongly recommended" and so on) are Google's own labels. Google says these are recommendations, not strict requirements.

**Status column**
- `tooling`: a check in `scripts/verify.sh` and CI fails when it is broken (what the check covers is stated).
- `review`: no tool checks it; the reviewer does.
- `later`: not applicable until the code exists (the milestone is stated), then `review` unless a follow-up automates it.

Facts about this repo were read from `build.gradle.kts`, `app/build.gradle.kts`, `gradle.properties`,
`config/detekt/detekt.yml`, `scripts/verify.sh`, `docs/PLAN.md` and `REVIEW.md` on `main` at `ed6ec5b`.
The architecture rules (M0.5-11) are on main: plain JUnit tests in `core/domain/src/test/kotlin/dk/bjarkebjarke/tally/architecture/` (`ArchitectureRules.kt`, `DataSourceRules.kt`, `DomainNoFloatingPointTest.kt`, `UiNoRawValuesTest.kt`, `NoDataSourceInUiTest.kt`, `NoGlobalScopeTest.kt` and others) run in `verify.sh` unit tests. They are JUnit tests that use Konsist to collect the files and regex rules to check their text: no floating point in domain code, no raw colours, `dp`, `sp` or `em` in UI outside the theme, no Firebase, DataStore, Room or data-layer type in a composable or ViewModel file (`DataSourceRules`, M1-50), and no `GlobalScope` in any source set.

## 1. Architecture
Sources: [Guide to app architecture](https://developer.android.com/topic/architecture) and
[Architecture recommendations](https://developer.android.com/topic/architecture/recommendations).

| Rule | Status |
|---|---|
| UI layer (Compose + ViewModel state holders) and data layer (repositories over data sources); domain layer only when logic is shared or complex ("recommended in big apps") | review (M1) |
| Composables and ViewModels never touch a data source (Firestore, DataStore, ...) directly; only repositories do | tooling: `NoDataSourceInUiTest` (imports and qualified names of `com.google.firebase`, `androidx.datastore`, `androidx.room` and `dk.bjarkebjarke.tally.data` in a file with a composable or a ViewModel); review for the rest |
| Single source of truth per data type: the owner exposes immutable types and takes events or function calls to change them | review (M1) |
| Unidirectional data flow: state down, events up | review (M1) |
| ViewModel at screen level only; no `Context`, `Activity`, `Resources` or `AndroidViewModel` in it; `ViewModel` instances are not passed down to child composables (State hoisting page) | tooling: `NoPlatformInViewModelTest` for `Context`, `Activity` and `AndroidViewModel` (M1-57); `Resources` and the rest: review (M1) |
| Expose one `uiState: StateFlow<...>` (`stateIn(..., WhileSubscribed(5_000), ...)` for streams); `MutableStateFlow` stays private | review (M1) |
| Collect with `collectAsStateWithLifecycle`; do not send one-off events from the ViewModel to the UI, update state instead | review (M1) |
| Reusable UI components use plain state holder classes, not ViewModels | review (M1) |
| Dependency injection, constructor injection first; Hilt when the app has several screens with ViewModels (PLAN section 1 already chooses Hilt) | review (Hilt with KSP since M1-30) |
| Pure-Kotlin domain code with no Android classes | tooling in part: `core/domain` is its own JVM module; the no-float rule is tooling: `DomainNoFloatingPointTest` in the unit tests |
| Use Jetpack libraries instead of hand-written boilerplate: lifecycle-aware collection (`collectAsStateWithLifecycle`), Navigation 3 for navigation, Hilt for dependency injection, DataStore for preferences | review |

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
| Saved state across process death: UI state the user typed (form fields, selection) uses `rememberSerializable` (or `rememberSaveable` without kotlinx.serialization) in composables or `SavedStateHandle` in the ViewModel, not just in-memory state ([Save UI states](https://developer.android.com/topic/libraries/architecture/saving-states)) | review (M1) |
| Previews for every stateless screen and component, using multipreview (`@PreviewLightDark`, `@PreviewFontScales`) and a `locale` preview for Danish; previews cannot build ViewModels | review |
| Follow the Compose API guidelines (naming, `modifier` parameter, Kotlin style) | tooling in part: spotless and ktlint, detekt `FunctionNaming` with `Composable` exempted, plus the Compose detekt rules (compose-rules 0.4.28: modifier parameter, naming, parameter order, no `MutableState` parameters, no Material 2 imports; `UnstableCollections` stays off on purpose, see the stability row above), gated by `testDetektRules` on fixtures in `config/detekt/fixtures`; the rest `review` |

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
| Inject dispatchers; never hardcode `Dispatchers.*` in classes; tests use a `TestDispatcher` with `runTest` | tooling: `NoDispatchersOutsideDiTest` (`Dispatchers` only in a Dagger or Hilt `@Module` file, M1-57); detekt `InjectDispatcher` enabled but active only where detekt is type-resolved (core modules today, not `:app`) |
| Suspend functions are main-safe: the class doing blocking work moves it with `withContext` | review |
| The ViewModel creates the coroutines; the data layer exposes `suspend` for one-shot calls and `Flow` for streams | review |
| No `GlobalScope`; work that must outlive a screen uses an injected external scope | tooling: `NoGlobalScopeTest` (every source set); detekt `GlobalCoroutineUsage` enabled and fixture-gated (`testDetektRules`) |
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
| JUnit 4 tests (Robolectric, Roborazzi, `createComposeRule`) really run in `:app` unit tests | tooling: `junit-vintage-engine` is on the `:app` test runtime, `failOnNoDiscoveredTests` is on, and `scripts/check_test_results.py` (run after `testDebugUnitTest`) fails when a test class has no result XML |
| Screenshot tests and accessibility checks in UI tests | tooling (M1-03): Roborazzi goldens, light/dark x en/da, and `enableAccessibilityChecks`; before M1-03, PLAN section 5 planned both. Correction (2026-11-17, contradiction C7 of the best-practices investigation on issue #15): Google does have a tool, [Compose Preview Screenshot Testing](https://developer.android.com/studio/preview/compose-screenshot-testing), still experimental; its page says the standalone plugin is no longer maintained and recommends AGP test suites on AGP 9.5+ (this repo is on AGP 9.5.1). M1-03 chose Roborazzi (JVM, exact-match goldens, `scripts/screenshots.sh`, runs in the `screenshots` CI job) and `enableAccessibilityChecks` in `androidTest`; the Google tool stays experimental, and a switch needs a recorded decision. Correction accepted by the owner on 2026-11-17 (issue #15 comment 6947871526) |

## 7. Accessibility
Sources: [Make apps more accessible](https://developer.android.com/guide/topics/ui/accessibility/apps),
[Accessibility principles](https://developer.android.com/guide/topics/ui/accessibility/principles).

| Rule | Status |
|---|---|
| Touch targets at least 48dp x 48dp for interactive elements (Material components already do this; custom ones must set it) | review now (REVIEW.md item 6); tooling later (UI accessibility checks) |
| Text contrast at least 4.5:1, except large text (18sp and up, or 14sp bold and up), which needs 3:1 ([WCAG 1.4.3](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html)) | review now; tooling later |
| Non-text contrast at least 3:1 for UI components and graphical objects needed to understand the UI: text-field outlines, checkbox borders, icons, focus indicators ([WCAG 1.4.11](https://www.w3.org/WAI/WCAG22/Understanding/non-text-contrast.html); [Android design: accessibility](https://developer.android.com/design/ui/mobile/guides/foundations/accessibility#design-vision)) | review now; tooling later |
| `contentDescription` for every icon button; `null` for decorative images; no "button" in the text; unique per list item | review now (Google says Android Lint, Compose tests and test tools can flag common issues; which lint checks fire here is not verified) |
| Use `Role`, `stateDescription`, `heading()`, `mergeDescendants` for groups; custom accessibility actions for swipe or drag gestures | review |
| Do not rely on colour alone; test with TalkBack | review |
| Text is in `sp`; layouts still work at 200% font scale (no clipped or overlapping text; no fixed heights on text containers) ([Android 14: non-linear font scaling to 200%](https://developer.android.com/about/versions/14/features#non-linear-font-scaling), [Android design: accessibility](https://developer.android.com/design/ui/mobile/guides/foundations/accessibility#design-vision), [WCAG 1.4.4](https://www.w3.org/WAI/WCAG22/Understanding/resize-text.html)) | review (`@PreviewFontScales`, see section 2) |

## 8. Performance
Sources: [Baseline Profiles](https://developer.android.com/topic/performance/baselineprofiles/overview) and the performance rows of the architecture recommendations.

| Rule | Status |
|---|---|
| R8 on for release (`isMinifyEnabled = true`) | tooling in part: set in `app/build.gradle.kts`; nothing checks the release build runs, a release smoke build is proposed |
| Baseline Profile and Startup Profile, generated by Macrobenchmark, with the Baseline Profile Gradle plugin (generation builds must not be obfuscated) | later (before the first release; milestone to be set by the planner) |
| Macrobenchmark to catch startup and jank regressions | later |
| Defer state reads and avoid allocating in recomposition when a measured issue shows up | review |

## 9. Security and privacy
Sources: [Security checklist](https://developer.android.com/privacy-and-security/security-tips),
[Network security config](https://developer.android.com/privacy-and-security/security-config),
[Auto Backup](https://developer.android.com/identity/data/autobackup) and
[Provide information for Google Play's Data safety section](https://support.google.com/googleplay/android-developer/answer/10787469) (Play Console Help, read 2026-11-15).

| Rule | Status |
|---|---|
| Never commit API keys; keep them out of the source repository | tooling in part: the `secrets` (gitleaks) CI job and GitHub push protection catch a key inside a committed file; `.gitignore` keeps `google-services.json` (in any directory) and key and credential files out of `git add -A`, tested by `scripts/test_gitignore_secrets.py`; no guard blocks such a file by name once it is force-added, so the `google-services.json` rule in CLAUDE.md is also a review item |
| Cleartext traffic is off by default from API 28; do not opt in. Use a network security config only if a real need appears | tooling: `scripts/check_build_guards.py` fails on `usesCleartextTraffic` or `cleartextTrafficPermitted` other than `false` in every manifest and every `res/xml*` network security config, and on a value it cannot read; the `src/androidTest/` source set is exempt (the test APK talks plain HTTP to the Auth emulator and is never shipped), every other source set is checked (M1-58) |
| Backup: the manifest sets `android:allowBackup="false"` today. If that is ever turned on, add `dataExtractionRules` and `fullBackupContent` rules that exclude device-specific data | tooling: `scripts/check_build_guards.py` fails on `allowBackup` other than `false` (missing counts as true in the main manifest) unless both `dataExtractionRules` and `fullBackupContent` are `@xml/<name>` resources that exist, and when no manifest with an `<application>` is found (M1-58) |
| Deep links and intents: App Links use `android:autoVerify="true"` plus a hosted `assetlinks.json`; treat data from an incoming link or intent (invite code) as untrusted input and validate it; set `android:exported` explicitly and keep components unexported unless needed ([Verify App Links](https://developer.android.com/training/app-links/verify-applinks), [Security checklist](https://developer.android.com/privacy-and-security/security-tips)) | review (M1-20) |
| Sign-in uses Credential Manager (`androidx.credentials`), not legacy `GoogleSignIn`; on sign-out call `clearCredentialState()` ([About Credential Manager](https://developer.android.com/identity/credential-manager), [Implement Sign in with Google](https://developer.android.com/identity/sign-in/credential-manager-siwg-implementation)) | review (M1-14) |
| Request the fewest permissions; validate input; keep data minimal (also Firestore rules, covered in REVIEW.md item 2) | review |
| Play Data safety form must match what the app collects. The page states that the developer alone is responsible for complete and accurate declarations, including data handled by third-party libraries and SDKs, and that Google may take enforcement action on a discrepancy between app behaviour and declaration. A privacy policy is required to complete the form, even for an app that collects no user data | review (the form is filled in Play Console, outside the repo) |

## 10. Play quality
Sources: [Target API requirement](https://developer.android.com/google/play/requirements/target-sdk),
[Window insets and edge-to-edge](https://developer.android.com/develop/ui/compose/layouts/insets),
[Predictive back](https://developer.android.com/guide/navigation/custom-back/predictive-back-gesture),
[Window size classes](https://developer.android.com/develop/ui/compose/layouts/adaptive/window-size-classes),
[Localization](https://developer.android.com/guide/topics/resources/localization).

| Rule | Status |
|---|---|
| From 2026-08-31 new apps and updates must target API 36 or higher. `targetSdk` is 37 | tooling: `scripts/check_build_guards.py` fails on a `targetSdk` below 36 or one it cannot read (M1-51) |
| Edge-to-edge: handle `WindowInsets` (a `Scaffold` helps); it is enforced when targeting SDK 35+ | review |
| Predictive back: do not intercept back with `onBackPressed` or `KEYCODE_BACK`; do not opt out | review |
| Adaptive layouts by window size class (compact under 600dp, medium 600 to 840dp, expanded 840 to 1200dp, large 1200 to 1600dp, extra-large from 1600dp; large and extra-large need the `supportLargeAndXLargeWidth` opt-in); do not use "is tablet" logic; state survives configuration changes | review (M1+) |
| All strings in resources, with a complete default `app/src/main/res/values/strings.xml` and `app/src/main/res/values-da/` | tooling: lint `MissingTranslation` is an error and `warningsAsErrors` is on (`app/build.gradle.kts`); lint `HardcodedText` covers XML only; the JUnit rule `UiHardcodedStringRules` (`:core:domain:test`) fails on a string literal that starts one of these values: the first positional argument of `Text(` or `showSnackbar(`, the second positional argument of `Icon(` or `Image(`, a named `text`/`contentDescription`/`label` (except on animation APIs)/`placeholder`/`title`/`message`/`supportingText`/`actionLabel`/`onClickLabel`/`stateDescription` argument, or a `contentDescription`/`stateDescription` assignment in `semantics { }`; review checks everything else: a literal inside or after an expression (`if`/`when`, `name + " items"`, `AnnotatedString(...)`, `String.format(...)`, `buildAnnotatedString`), positional arguments of other functions (the app's own composables, `Toast`), other semantics properties and `this.contentDescription`, and `<plurals>` |
| Account deletion: an app that lets users create an account must let them delete it in the app and give a web link for the deletion request ([Play account deletion requirements](https://support.google.com/googleplay/android-developer/answer/13327111)) | review (M1-32, AUTH-04; the web page lives on the OQ-21 domain) |
| Per-app language: declare supported locales with `generateLocaleConfig` (Android 13+ system picker) ([Per-app language preferences](https://developer.android.com/guide/topics/resources/app-languages)) | review (M1-24) |
| Dark theme: every screen supports light and dark ([Material 3 colour scheme in Compose](https://developer.android.com/develop/ui/compose/designsystems/material3#color-scheme), [Dark theme](https://developer.android.com/develop/ui/views/theming/darktheme)) | review (`@PreviewLightDark`, section 2) |
| Give translators context comments; mark non-translatable parts with `xliff:g` | review |

## 11. Dependency and Gradle hygiene
Source: [Version catalogs](https://developer.android.com/build/migrate-to-catalogs).

| Rule | Status |
|---|---|
| Dependencies and plugins only through `gradle/libs.versions.toml`, kebab-case names, `alias(libs.plugins...)` | tooling in part: the catalog exists; nothing fails a hardcoded `"group:name:version"`, a guard is proposed |
| Configuration cache and build cache on | tooling in part: set in `gradle.properties` |
| Kotlin style and formatting | tooling: spotless with ktlint, detekt with `maxIssues: 0`, Kotlin `allWarningsAsErrors` |
| JVM modules use only Java and Android API available at minSdk 26 (lint NewApi skips pure JVM modules; no desugaring is configured) | tooling: `checkJdkRelease` (JDK 17 API) and `checkJavaApiLevel` (`scripts/check_java_api_level.py` reads the main classes of every JVM module against `api-versions.xml` of the compileSdk platform; M1-37) |
| Lint with warnings as errors | tooling: `:app:lintDebug` in `verify.sh` |
| Dependency freshness | Dependabot (lint freshness checks are disabled on purpose with a `// justified:`) |
| Dependency verification | tooling: `gradle/verification-metadata.xml` holds a sha256 for every resolved artifact (plugins, build tools, lint, test and Android configurations), enforced by Gradle in every build; `scripts/check_gradle_repos.py` fails when the file is missing, verification is switched off, or an artifact has no sha256 |

### Regenerating dependency verification metadata
After any dependency, plugin or Gradle wrapper bump (including a Dependabot PR), a build fails with "Dependency verification failed" until the file is updated. Regenerate it from scratch with the tasks CI runs (Gradle never removes stale entries, so delete the file first), then review the diff (old versions of the bumped artifacts removed, new ones added, nothing else):

```
rm gradle/verification-metadata.xml
./gradlew --no-configuration-cache --refresh-dependencies --write-verification-metadata sha256 \
  spotlessCheck detekt :core:domain:detektMain :core:domain:detektTest :core:testing:detektMain :core:testing:detektTest \
  :app:lintDebug testDebugUnitTest :core:domain:test koverVerify :app:verifyRoborazziDebug :app:assembleDebug :app:assembleDebugAndroidTest :core:data:assembleDebugAndroidTest :core:data:lintDebug
```

The file must be generated on Linux (CI's platform), and then given the other two operating systems' `aapt2` jars. AGP resolves `com.android.tools.build:aapt2:<version>:<os>` for the build host's OS only, so a Linux run records only the `linux` jar and a macOS or Windows build fails verification. Regenerating on macOS or Windows instead would drop the `linux` jar and break CI. After the command above, add the other two from a throwaway project (`<version>` is the `aapt2` version in the file; the write mode only adds entries):

```
mkdir -p /tmp/aapt2-os/gradle && cp gradle/verification-metadata.xml /tmp/aapt2-os/gradle/ && cd /tmp/aapt2-os
echo 'dependencyResolutionManagement { repositories { google() } }' > settings.gradle.kts
cat > build.gradle.kts <<'EOT'
val cfgs = listOf("linux", "osx", "windows").map { os ->
    configurations.create("aapt2$os") { isTransitive = false }
        .also { dependencies.add(it.name, "com.android.tools.build:aapt2:<version>:$os@jar") }
}
tasks.register("resolveAll") { doLast { cfgs.forEach { println(it.files) } } }
EOT
<repo>/gradlew --no-configuration-cache --write-verification-metadata sha256 resolveAll
cp gradle/verification-metadata.xml <repo>/gradle/   # the diff against the repo file is only the osx and windows jars
```

`scripts/check_gradle_repos.py` fails when the `aapt2` component lacks any of the three jars.

`--refresh-dependencies` is required: Gradle does not record BOM and parent POM files it already has in its metadata cache, so without it a warm `~/.gradle` writes an incomplete file that only fails on a fresh CI runner. With it, the result is the same as from an empty cache.

Robolectric (issue 213): its `android-all-instrumented` jar is resolved by Gradle (configuration `robolectricAndroidAll` in `app/build.gradle.kts`, version in the catalog), so it is verified like every other artifact. `syncRobolectricAndroidAll` copies it to the `robolectric-android-all` directory in the `:app` build directory, and every test JVM runs with `-Drobolectric.offline=true -Drobolectric.dependency.dir=<that directory>`, so Robolectric never downloads at test runtime and the test-JVM network block stays as it is. `testDebugUnitTest` depends on the sync task, so the command above already records the jar. Robolectric runs the app's `targetSdk` (SDK 37, set in `robolectric.properties`; `RobolectricUnderNetworkBlockTest` fails when they differ), so UI and screenshot tests see the Android version the app targets. A Robolectric version bump needs the matching `robolectricAndroidAll` version and, for another SDK level, one more dependency on that configuration.

Checksums only, no PGP signatures: most Android and Kotlin artifacts are not signed with keys Gradle can verify, and a checksum is enough to stop a mirror or CDN from silently changing an artifact. Never add `trusted-artifacts` or set `org.gradle.dependency.verification` to `off` or `lenient`; the check rejects both. The `ui` job's `:app:connectedDebugAndroidTest` needs no extra entries beyond the assemble tasks above (it needs a device, so it is not in the command); if an AGP bump adds artifacts only that task resolves, `ui` fails and the file is regenerated again. Add a new CI task to the command above when CI starts running one.

## Proposed follow-ups (not implemented here)
Each would be its own PR, test-first, per CLAUDE.md.
1. **Konsist architecture rules** after M0.5-11: composables and ViewModels may not import Firestore, DataStore or Room types and no `GlobalScope` (done, M1-50); ViewModels may not use `android.content.Context`, `Activity` or `AndroidViewModel`, and no `Dispatchers.` outside a Dagger or Hilt `@Module` file (done, M1-57).
2. **detekt coroutines rules**: partly done (issue 38). `GlobalCoroutineUsage` is enabled and fixture-tested. `InjectDispatcher` is enabled and fixture-tested with a type-resolved fixture, but it only fires in type-resolved tasks (`detektMain`/`detektTest`), which today exist only for `:core:domain` and `:core:testing`. Still open: a type-resolved detekt run for `:app` and the planned `:core:data`, so the rule reaches code that will write `Dispatchers.IO`.
3. **Guard for hardcoded dependency coordinates** in `*.gradle.kts` (everything must come from the catalog). Task M1-59.
4. ~~Guard that `targetSdk` is at least the Play minimum~~ Done (M1-51, `scripts/check_build_guards.py`, see section 10); raise `TARGET_SDK_FLOOR` when the date changes.
5. ~~Manifest guard: fail on `usesCleartextTraffic="true"`, `cleartextTrafficPermitted="true"`, or `allowBackup="true"` without backup rules~~ Done (M1-58, `scripts/check_build_guards.py`, see section 9); the `src/androidTest/` source set is exempt from the cleartext rule.
6. **Compose compiler stability report** as a CI artifact (no gate) once there are screens.
7. **Release smoke build** with R8 on, run in CI, once M1 has a release variant.
8. **Roborazzi and accessibility checks** are already in PLAN section 5; make sure their tasks cite sections 6 and 7 above.

## Owner decisions (2026-11-13, updated 2026-11-15)
1. Navigation 3 (section 3).
2. Firestore offline persistence only, no Room (section 4).
3. `support.google.com` is now allowed (2026-11-15); the Play Data safety item is sourced from the Play Console Help page, read 2026-11-15 (section 9).

No open questions remain; the owner approved the checklist on 2026-11-15 (status line above).
