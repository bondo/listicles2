# Handoff: M1-66 auth wiring 1, round 1 fix round (branch m1/auth-wiring-66)

Delete this file in the PR's final commit (squash merge keeps it off `main`).
Write it when the context hook reminds you (60% of a 1M window, 40% of a 200k one; hard stage 80% / 60%), commit it, and end the session. The next session starts from this file.

## Goal
PR #368 (draft): M1-66 narrowed to the Credential Manager wrapper (Sign in with Google button flow) in `:core:data`, `:app` on
`:core:data` with licensee. Now: the round 1 fix round ordered by orchestrator #40 (session_013srDQjzTThi6fiwUCgbrfr) after
review R1 (comment 7120462121) and S1 (comment 7120410680), both changes_requested, no blocker or major.

## Done
- Everything up to 1bcf75d: verify.sh all 77 steps passed, CI green; WORKER-RESULT comment 7120207727; M1-88 draft comment
  7119090146 (Hilt bindings, do not apply here). Handed off at 60% context before any fix-round commit (this file only).

## Next (in order)
1. R1-01 = S1-03 (minor, fix now), test first. New Robolectric test in `app/src/test/kotlin/dk/bjarkebjarke/tally/`
   (for example `ManifestSurfaceTest`) that pins with exact sets:
   - requested permissions: `packageManager.getPackageInfo(packageName, GET_PERMISSIONS).requestedPermissions`;
   - exported components: activities, services, receivers and providers with `exported == true`.
   Commit it red, then edit `app/src/main/AndroidManifest.xml` (add `xmlns:tools`):
   - `tools:node="remove"` for `android.permission.USE_BIOMETRIC` and `android.permission.USE_FINGERPRINT`;
   - `<activity android:name="com.google.firebase.auth.internal.GenericIdpActivity" tools:node="remove" />`;
   - RecaptchaActivity and READ_GSERVICES only if email and password sign-in does not need them (see Facts), else keep each
     with a one-line reason;
   - declare `android.permission.INTERNET` with a one-line reason (Firebase), like ACCESS_NETWORK_STATE. Keep INTERNET.
2. R1-02 (minor): in `core/data/src/main/res/values/google_sign_in.xml` (comment) and the companion KDoc of
   `CredentialManagerGoogleCredentials`, say that the value only comes from a google-services.json downloaded after Google
   sign-in is enabled, so the release secret must be replaced then. Do not edit PR #367 (the orchestrator carries the step).
3. Nits R1-03 = S1-01 and S1-02, same commit if trivial: "Google ID option" becomes "Sign in with Google" in
   `gradle/libs.versions.toml` (the credentials comment), the class KDoc of `CredentialManagerGoogleCredentialsTest`, the M1-66
   title in `docs/tasks.toml`, `core/domain/.../session/GoogleCredentials.kt` line 4, and `docs/milestones/M1.md` (M1-14
   paragraph, "Credential Manager with the Google ID option"). `config/licensee/policy.gradle` line 1: add `:core:data`.
4. Plain `git push` (foreign-commit check first), `scripts/verify.sh` (about 50 minutes; gate tests run), no loop-wait for CI,
   keep the PR draft. Refresh the PR body (decision lines for the manifest), delete this file in the last commit, then send
   orchestrator #40 a one-line WORKER-RESULT with the new head and the lines changed.

## Decisions made
- Button flow (`GetSignInWithGoogleOption`), not the two-step Google ID option: both reviewers agree (R1, S1).
- Split M1-88 (bindings) and M1-89 (#357): both reviewers agree; 389 guarded lines.
- `credentials-play-services-auth` is `api` in `:core:data` (lint CredentialDependency).

## Open findings
- R1-01 = S1-03, minor, open: unused permissions and exported Firebase Auth activities in the merged manifest.
- R1-02, minor, open: web client id needs a re-downloaded google-services.json; say so.
- R1-03 = S1-01, nit, open (accepted, fix if trivial): "Google ID option" wording.
- S1-02, nit, open (accepted, fix if trivial): policy.gradle header.

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
  (debugImplementation ui-tooling and ui-test-manifest). Unit tests see the debug manifest; say so in the test.
- GenericIdpActivity serves only browser sign-in with an OAuthProvider (Tally has none).
- RecaptchaActivity: the reviewers believe it serves only phone auth's browser reCAPTCHA. Check the firebase-auth 25.0.0
  classes in `~/.gradle/caches/modules-2` before removing it.
- READ_GSERVICES: used by the reCAPTCHA SDK, which Firebase Auth runs for email and password only when the project turns on
  reCAPTCHA protection (off in tally-c1a15). If you cannot show it is unneeded, keep it with that reason.
- Maven Central answers 429 now and then: retry. A verify run takes about 50 minutes (the gate self-tests run).

## Waiting on the owner
- none
