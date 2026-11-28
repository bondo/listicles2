# Handoff: M1-25 Account screen (branch m1/account-25)

Delete this file in the PR's final commit.

## Goal
M1-25 (docs/milestones/M1.md row 21): Account screen (wireframe 18), sign-out UI (AUTH-03, wireframes 39 and 45), the home avatar. The Crashlytics part is held back until the owner accepts one licence (below).

## Done
- Tests first (2ef118b), then the Account screen, view model, navigation (avatar opens Account over home, back pops, sign-out returns to sign-in), en and da strings, privacy link (Q10).

## Held back: Crashlytics opt-in (needs the owner)
`com.google.firebase:firebase-crashlytics` (in the BoM 35.2.0, resolves to 21.1.0) brings in exactly one artifact that `licensee` rejects, with the Android SDK terms:
- `com.google.firebase:firebase-measurement-connector:20.0.1`
Nothing else is flagged (checked on androidDebug and androidRelease). `firebase-analytics` is not on the classpath. Licence acceptance is the owner's: needs a line in `config/licensee/google-sdk-terms.txt`.
When accepted, rebuild from this description (about 150 lines):
1. `libs.firebase.crashlytics` in the catalog and `app/build.gradle.kts`; `gradle/verification-metadata.xml` via `--write-verification-metadata sha256` over the hook's task set plus `:app:compileDebugUnitTestKotlin :app:compileReleaseKotlin :core:data:compileDebugKotlin` (the first run on `releaseRuntimeClasspath` alone missed some poms).
2. Manifest `<meta-data android:name="firebase_crashlytics_collection_enabled" android:value="false"/>`, tested in `ManifestSurfaceTest` (merged release manifest).
3. Domain `CrashReports { isSending(); setSending(on) }` (do not name a method `enabled`/`setEnabled`: the disabled-test guard matches it), `PreferencesCrashReports(context, collection)` with `applyStored()` called in `TallyApplication.onCreate`, an `AccountModule` provider calling `FirebaseCrashlytics.getInstance().setCrashlyticsCollectionEnabled`, the VM `setCrashReports`, a `Switch` row (toggleable, role Switch) with strings `account_crash_title` / `account_crash_body` (wireframe 18: "Send crash reports" / "Off until you turn it on. Helps fix crashes."; da "Send nedbrudsrapporter" / "Slået fra, indtil du slår det til. Hjælper med at rette nedbrud.").
4. Tests: switch writes through a fake; preference off by default and survives a new instance; a test that `com.google.firebase.analytics.FirebaseAnalytics` and `com.google.android.gms.measurement.AppMeasurement` are not loadable (with a negative case); a scan of `app/src/main` that finds no `setUserId` or `setCustomKey(s)` (negative case on sample strings).
5. Pending for M1-25 acceptance: sign-out clearing last-opened times; no such store exists before M2, so `LocalUserData.clear()` stays the one place that must clear it.

## Commands to resume
```
git fetch origin m1/account-25
scripts/install-hooks.sh
scripts/verify.sh
```

## Facts that save time
- A commit runs spotless and detekt, and `detekt` depends on `licensee`, so a new licence blocks every commit.
- The hook blocks `git checkout` with uncommitted changes: use `git show HEAD:path > path`.
