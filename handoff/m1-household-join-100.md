# Handoff: M1-100 household data 1b, invite lookup and join (branch m1/household-join-100)

Delete this file in the PR's final commit (squash merge keeps it off `main`).
Write it when the context hook reminds you (60% of a 1M window, 40% of a 200k one; hard stage 80% / 60%), commit it, and end the session. The next session starts from this file.

## Goal
HH-03: the join screen's lookup of an invite code (its stored `householdName`, P2; expiry on the client, the rest denied by
the rules) and the join batch of PLAN 3.1 (single use, `displayName` copied, P9), emulator tests with two and three users.
`docs/milestones/M1.md` (M1-18 section, split note), `docs/tasks.toml` M1-100.

## Done
- 2059bfe failing tests (domain property tests, emulator tests), interface and stubs
- 5913d2c `Invites.isWellFormed`/`householdId`, `inviteLookup` (core/domain)
- 18a8d96 `FirestoreHouseholds.invite` and `join`

## Next (in order)
1. Draft PR to main; verifier subagent (agents/prompts/verifier.md) on the diff; review rounds.
2. Final commit: M1-100 `status = "done"` in docs/tasks.toml and this file deleted.

## Decisions made
- No firestore.rules change: the invite get (M1-12) and join (M1-54) rules on main already hold; rules tests exist.
- A denied lookup read is `InviteLookup.Unusable`, a denied join batch `Membership.InviteUnusable`; other errors Failed.
- Revoke is M1-101; the emulator test revokes with a raw delete by the creator. Creator-left join denial is covered by
  `firebase/test/join.test.ts` only (Leave/Remove are M1-31).

## Open findings
- none yet

## Commands to resume
```
git fetch origin m1/household-join-100 && git checkout m1/household-join-100
scripts/install-hooks.sh
scripts/verify.sh
```

## Facts that save time
- Emulator tests (`HouseholdsEmulatorTest`) run only in CI's `ui` job; locally only compile them.
- Pre-commit runs spotless and detekt (ReturnCount limit 2, line length 120); `./gradlew spotlessApply` at the root fixes format.
- Pre-push runs the unit tests, so a test-first commit is pushed together with its fix.

## Waiting on the owner
- none
