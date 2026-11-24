# Handoff: M1-66 auth wiring 1, round 1 fix round (branch m1/auth-wiring-66)

Delete this file in the PR's final commit (squash merge keeps it off `main`).
Write it when the context hook reminds you (60% of a 1M window, 40% of a 200k one; hard stage 80% / 60%), commit it, and end the session. The next session starts from this file.

## Goal
PR #368 (draft): M1-66 narrowed to the Credential Manager wrapper (Sign in with Google button flow) in `:core:data`, `:app` on
`:core:data` with licensee. Now: the round 1 fix round ordered by orchestrator #40 (session_013srDQjzTThi6fiwUCgbrfr) after
review R1 (comment 7120462121) and S1 (comment 7120410680), both changes_requested, no blocker or major.

## Done
- Everything up to 1bcf75d: verify.sh all 77 steps passed, CI green; WORKER-RESULT comment 7120207727; M1-88 draft comment
  7119090146 (Hilt bindings, do not apply here).
- Round 1 fix round (second implementer session), pushed:
  - ddfe7d5 failing `ManifestSurfaceTest` (JUnit 5, reads the merged RELEASE manifest; `app/build.gradle.kts`
    `ReleaseManifestArgs` passes its path, `SingleArtifact.MERGED_MANIFEST`); 4 of 4 failed for the right reasons.
  - 450352d R1-01 = S1-03: new `core/data/src/main/AndroidManifest.xml` removes USE_BIOMETRIC, USE_FINGERPRINT,
    GenericIdpActivity, RecaptchaActivity (`tools:node="remove"`); app manifest declares INTERNET. Test 4/4 green, lint ok.
  - 6718237 R1-02 text, nits R1-03 = S1-01, S1-02.

## Next (in order)
1. `scripts/verify.sh` at 6718237 (about 50 minutes). Guarded diff is 538 lines without this file (618 with it: CI's
   guards job fails until this file is deleted).
2. Refresh the PR body (see Decisions made), delete this file in the last commit, push, post the WORKER-RESULT comment,
   send orchestrator #40 a one-line WORKER-RESULT (fix commits: 163 changed lines in 12 files).

## Decisions made
- Button flow (`GetSignInWithGoogleOption`), not the two-step Google ID option: both reviewers agree (R1, S1).
- Split M1-88 (bindings) and M1-89 (#357): both reviewers agree; 389 guarded lines.
- `credentials-play-services-auth` is `api` in `:core:data` (lint CredentialDependency).
- Removals live in `:core:data`'s manifest, not the app's: lint MissingClass (`:app:lintDebug`) fails on the activity names,
  because firebase-auth is only on `:core:data`'s compile classpath; no suppression. The library `<application>` carries
  `allowBackup="false"` for the build guard (M1-58). The merger report shows the library entries REJECTED.
- Kept with reasons in the test: READ_GSERVICES (reCAPTCHA SDK reads the GSF android_id, no catch at that level, once
  reCAPTCHA protection is on: a console switch), RevocationBoundService and ProfileInstallReceiver (signature/DUMP).
- RecaptchaActivity is started only from `FirebaseAuth.zzQ/zzR(PhoneAuthOptions)` (firebase-auth 25.0.0 bytecode);
  GenericIdpActivity only from `OAuthProvider`. Propose to the orchestrator: M3-O1 (PR #367) replaces the release
  google-services.json copies after enabling Google sign-in (R1-02).

## Open findings
- R1-01 = S1-03, minor, fixed (ddfe7d5 test, 450352d fix).
- R1-02, minor, fixed (6718237).
- R1-03 = S1-01, nit, fixed (6718237).
- S1-02, nit, fixed (6718237).

## Commands to resume
```
git fetch origin m1/auth-wiring-66 && git checkout m1/auth-wiring-66
scripts/install-hooks.sh
scripts/verify.sh
```

## Facts that save time
- Merged manifests at 1bcf75d (`:app:processDebugMainManifest`, `:app:processReleaseMainManifest`; output under
  `app/build/intermediates/merged_manifest/<variant>/`). Permissions, identical in both variants:
  - ACCESS_NETWORK_STATE;
  - INTERNET;
  - USE_BIOMETRIC and USE_FINGERPRINT, from androidx.biometric 1.1.0 (an api dependency of credentials 1.6.0, used only by
    its `provider` package);
  - `com.google.android.providers.gsf.permission.READ_GSERVICES`, from com.google.android.recaptcha 18.6.1 through
    firebase-auth;
  - `dk.bjarkebjarke.tally.DYNAMIC_RECEIVER_NOT_EXPORTED_PERMISSION` (androidx.core, also declared as a permission).
- Exported in release:
  - MainActivity;
  - GenericIdpActivity and RecaptchaActivity (firebase-auth, BROWSABLE);
  - RevocationBoundService (play-services-auth, protected by REVOCATION_NOTIFICATION);
  - ProfileInstallReceiver (protected by DUMP).
- Debug also exports `androidx.compose.ui.tooling.PreviewActivity` and `androidx.activity.ComponentActivity`
  (debugImplementation ui-tooling and ui-test-manifest). Robolectric sees the debug manifest, so ManifestSurfaceTest
  parses the release one (path from Gradle) instead.
- GenericIdpActivity serves only browser sign-in with an OAuthProvider (Tally has none).
- RecaptchaActivity: the reviewers believe it serves only phone auth's browser reCAPTCHA. Check the firebase-auth 25.0.0
  classes in `~/.gradle/caches/modules-2` before removing it.
- READ_GSERVICES: used by the reCAPTCHA SDK, which Firebase Auth runs for email and password only when the project turns on
  reCAPTCHA protection (off in tally-c1a15). If you cannot show it is unneeded, keep it with that reason.
- Maven Central answers 429 now and then (a plugin can then show as "not found"): retry. A verify run takes about 50
  minutes (the gate self-tests run). A push runs the pre-push hook (guards, hook tests, unit tests): about 10 minutes.

## Waiting on the owner
- none
