# Handoff: M1-67 auth data 2, Firebase session layer in :core:data (branch m1/auth-data-67)

Delete this file in the PR's final commit (squash merge keeps it off `main`).

## Goal
M1-67, draft PR #348: fix round 1 (R1 7100800058: R1-01..03; S1 7100817140: S1-02 = R1-03, S1-03; S1-01 deferred
to #357 with owner OK, decision 7101961993). Orchestrator #37 is named on #15.

## Done
- Round 0: f8e514b (red), 986eb27, ae7b54e, 9d6878f, 02fbaf9, merges d116961 and abcd34e; CI green at d116961.
- Round 1 red pair pushed: e4218c3 (R1-01, R1-02 tests; NonCancellable out), d66252b (S1-03 test; clear()'s catch
  out). `ui` at d66252b (job 137734213003): `tests="10" failures="3"`, exactly the 3 new tests:
  IllegalStateException (terminated client), AssertionError line 214 (cache survived), FirebaseFirestoreException
  (failed delete). The handoff commit keeps that code, so `ui` stays red until step 1.

## Next (in order)
1. Green commit, `FirestoreSession.kt`: start from `git show 9d6878f:<file>` (NonCancellable and the catch back).
   R1-01: `firestore()` out of the try in `awaitPendingWrites()`, plus `catch (expected: IllegalStateException)`
   answering `false` ("a clear() still running terminated the instance: a second sign-out while the first one
   finishes"); class KDoc: the "`SignOut` calls ... never overlap." sentence becomes "..., and
   [awaitPendingWrites] meanwhile answers a failed wait."
2. Docs commit. Privacy section 2: the Q5 marker becomes `[To confirm (M1-O15): on the Firebase Auth emulator
   (M1-67) the sign-in record keeps all of these and, for every sign-in method, also when the account was created
   and when you last signed in; M1-O5 decides whether this text names those times.]` (da: `Skal bekræftes`, same
   content). After "...for your account)." add `[To confirm (M1-66, #357): also when Firebase ends your session by
   itself, for example after the account was deleted or its password changed on another phone; until then the
   copy stays until the next sign-out on this phone.]` (and da). `docs/tasks.toml`: owner task M1-O15 after M1-O14
   (check once with a real Google sign-in which fields the Auth record keeps; depends_on M1-O1, M1-66; notes: what
   the emulator showed, console or `firebase auth:export`, fix the privacy text, the times are M1-O5's call);
   M1-66 notes: "Burns down #357 (PR 348 S1-01, owner-ok): clear the local data on every change to signed out,
   also one Firebase starts by itself after a refused token refresh." No new agent task (S1-01 lives in #357).
3. Full `scripts/verify.sh`, push, CI green; PR body (round 1 rows, red and green runs, M1-O15, #357);
   WORKER-RESULT comment; `send_message` to the orchestrator named on #15.

## Facts that save time
- No KVM here: emulator tests run only in CI's `ui` job (a push cancels the running one). Diff guard: about 550
  lines after step 2 (limit 600).
- The Auth emulator runs locally (`npm ci` in `firebase/`, `npx firebase emulators:start --only auth`).

## Waiting on the owner
- none for this PR (M1-O5 reads the markers)
