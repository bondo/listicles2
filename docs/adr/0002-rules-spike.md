# ADR 0002: rules spike, PLAN 3.1 items (a) to (e)

Status: accepted (M1-09, 2026-11-23). Firestore emulator 1.22.0 (firebase-tools 15.36.0, `@firebase/rules-unit-testing` 5.0.2).
Re-check when the emulator is upgraded: the item (e) tests then show whether its limits changed.

## Context
[PLAN section 3.1](../PLAN.md) asks M1-09, before the rules tasks M1-10 to M1-12, M1-53 and M1-54, to prove in the emulator that
(a) the invite `list` rule filtered on `householdId` with a membership `exists()` is accepted, (b) the join batch with
`existsAfter`/`getAfter` works, (c) the transfer batch works, (d) the list query on `sharedWith` with `M(hid)` and `LIVE` is
accepted, and (e) every batch stays within the access-call limits: 10 `get`/`exists` calls per single-document request, query
or write in a batch, and 20 per batch[^calls]. If (a) failed, invites would move under the household.

## How
`firebase/test/spike.rules` holds one block per item, written from the PLAN 3.1 row with every access call of the row, in
the layout of the Decision. `firebase/test/spike.test.ts` inserts the blocks under the documents match of
`firebase/firestore.rules` and runs 46 allow and deny tests in one seeded world; item (e) adds blocks that only make n calls
on n documents. The blocks are never deployed: `firestore.rules` is unchanged. A scratch mutation pass (each condition of the
blocks dropped in turn), the self-review and review round 1 found five conditions no test caught; each now has a test.

## Results
| Item | Result |
|---|---|
| (a) | Works, also in the shape the owner decided on #280 (M1-O12): a plain member's query filtered on `householdId` and `createdBy == uid`, the owner's on `householdId` alone. Denied: a plain member without the `createdBy` filter or with another's uid in it, no `householdId` filter, no filter, another household, a tombstone, and `householdId in [mine, another]` (each value is checked). |
| (b) | Works: in one batch the member create sees the invite deleted (`existsAfter`) and the users doc set (`getAfter`), the joiner's invite delete sees the new member doc (`getAfter`). Denied: either write missing, a stale `householdId` of the same household (rejoin before the self-heal, OQ-5), a second member doc (#206), another invite of the household deleted in the same batch, role `owner`, `joinedAt` not the request time, an expired invite, a creator who left, another household's invite, a tombstone; the invite's delete by a member whose doc names the code (P3's re-created code) and by a non-member outside a join. |
| (c) | Works: the household update checks both roles after the batch, each role update the `ownerUid` after it. Denied: the household update alone, only one of the role updates, a plain member's whole batch, a non-member as new owner, a tombstone, another field on either document, the owner's role update alone. |
| (d) | Works: `sharedWith == hid` for a member of the live household, and the creator's `createdBy == uid`. Denied: another household, a tombstone, `createdBy` another user, no filter. |
| (e) | The emulator enforces 10 calls per single-document request and per write in a batch, and 20 per batch (permission denied, "Service call error"), and it charges the calls of an `||` operand that fails before the one that grants (a scratch run showed the same for allow statements, in source order). A `let` is evaluated, and its calls charged, when its function runs, and an argument when its function is called, used or not (only an error in an unused one is ignored); `&&` skips its right operand. But it caches calls on one document, also across the writes of a batch (21 writes reading one document pass), and it allows a query 20 calls, not 10. So emulator tests prove counts of distinct documents only, and nothing for a query between 11 and 20 calls. The documentation says only that "some document access calls may be cached"[^calls]; the worst case, every call counted, is counted by hand below. |

### (e) Calls per batch, worst case
Every call counted, no caching, from the PLAN 3.1 rows as the blocks write them. A write is charged its own path and every
path tried before it; under the layout of the Decision each path tried before a batch's own fails on a condition that makes
no call, so a write is charged its own path. Paged batches add a margin of one call per write; the fixed ones have room to
spare (the join's member create: 7 of 10).

| Batch (task) | Calls | Fits 10 / 20 |
|---|---|---|
| Join (M1-54) | member create 7, invite delete 3, users-doc set 2 (P5) = 12 | yes, the largest fixed batch |
| Create household (M1-10) | household 2, owner member doc 6 (the household `let`, then the row's `!exists`), users-doc set 2 = 10 | yes |
| Transfer (M1-53) | household update 4, each role update 2 = 8 | yes |
| Create invite (M1-12); query invites (M1-12) or lists (M2) | membership 1, household 1 (LIVE, P2's name or `O(uid)`) = 2 | yes |
| Delete an invite (M1-12) | creator's, owner's or tombstone cleanup's 1, a member's expired cleanup 2, the joiner's 3 | yes |
| P6 delete and users-doc clear (M1-11); display name (M1-10, M1-39) | 2; 1 | yes |
| Leave (M1-11, M1-31) | member delete 1, users-doc clear 1, each own invite 1, each + margin 1 = 4 + 2k | k ≤ 8 |
| Remove member (M1-11, M1-31) | member delete 3, marker 3, each invite 1, each + margin 1 = 8 + 2k | k ≤ 6 |
| A page of deletes: the invites Leave or Remove leaves out, the tombstone cleanup (M1-11, M1-31) | each 1 + margin 1 | 10 a page |
| Expired-invite cleanup (M1-18) | each delete 1 (creator's or owner's path: a plain member lists only their own, #280) + margin 1 | 10 a page |

## What does not work, or needs care
* Rules are not filters, in the emulator too: a query must carry the equality filters the rule reads through `resource.data`.
* Some conditions are checked twice in one batch, so no test can isolate them: in the join `invite.householdId == hid` (the
  invite delete's `getAfter`), `LIVE` in the member create and the invite delete (the users-doc set's P5 check) and
  `exists(users/uid)` (a `get()` of no document fails); in the transfer `LIVE` and `O(uid)` on both documents and `M(new)`
  before and after (the role checks); in the list query `sharedWith != null`. They stay, as PLAN 3.1 has them, so each rule
  holds on its own; their deny tests in M1-53 and M1-54 pass through either check. M1-53 still isolates the transfer's
  `LIVE` and `O(uid)` on each document, in worlds the app never makes (a member's cached role already `owner` while
  `ownerUid` is unchanged); `M(new)` cannot be isolated even so. M1-54 isolates the join's `invite.householdId == hid` the
  same way: another household's invite, deleted in the batch through the owner's path by its owner, who has no member doc
  there.
* A field of a document that `getAfter` finds absent is an error, which denies: the joiner's delete relies on that.

## Decision
* Invites stay top level; the nested-invites fallback is not needed.
* M1-12 (a), M1-54 (b), M1-53 (c) and M2 (d) each move their block into `firestore.rules` with its field validation (P4)
  and full allow and deny tests, delete it from `spike.rules` and keep `spike.test.ts` green; with the last block, the file
  and its insertion go and the tests run on `firestore.rules` alone.
* Layout, which the counts rely on (M1-10 to M1-12, M1-53, M1-54, M2): each method of a match has one allow statement,
  whose function reads the household once, in a `let` at its top: every path needs it, and a `let` is charged when its
  function runs. Inside each path the conditions that make no call (document ids and the caller, `createdBy`, `role`,
  `expiresAt`, the changed keys, and `ownerUid` and `deleted` from the `let`) come first; its `get`/`exists` calls follow in
  its `&&` chain, inline or in an argument of a function called there, never in a `let`. The paths go in this order, so
  each path tried before a batch's own fails without a call. Invite delete: creator, owner, tombstone cleanup, a member's
  expired cleanup (`expiresAt` first), joiner. Member delete: Leave, P6, tombstone cleanup, Remove. Member create: the
  owner's and the joiner's, told apart by `role`. Batches are sized to the worst case above.

## Consequences
* M1-31: Leave keeps at most 8 of the leaver's invite deletes in its batch and Remove member at most 6 of the removed
  member's; more go first, in pages of up to 10, as do the tombstone cleanup's deletes (PLAN 3.1 spike result).
* M1-18: the expired-invite cleanup deletes in pages of up to 10, each through the creator's or the owner's path.
* M2 planning (M2-01): an item write reads its list and, in a shared list, `M` and `LIVE`, so 3 calls and the margin: 5
  item writes a batch in the worst case (list delete, anonymise). Whether production caches like the emulator is unknown;
  only a test on a real project shows it.
* If a later emulator enforces 10 calls for a query or stops caching, an (e) test fails: revisit this ADR.

[^calls]: https://firebase.google.com/docs/firestore/security/rules-conditions#access_call_limits (10 per single-document request and query, 20 per batched write, 10 per operation in it; "Some document access calls may be cached, and cached calls do not count towards the limits"; fetched 2026-11-23)
