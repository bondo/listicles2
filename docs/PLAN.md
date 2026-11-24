# Tally (repo: bondo/tally) – Implementation Plan

Status: working draft, matched to the owner-approved stories and flow and to the decisions of 2026-11-15 to 2026-11-19
(task OQ-15; OQ-15 decided 2026-11-18, issue #15 comment 6991933333); the plan itself is not owner-approved (see issue #15).

Android app for shared household lists. In v1 every list is private to its creator until the creator shares it
with their household; lists are *plain* or *collection* lists (`docs/product/stories.md`). Changes sync in real
time between members. Packing lists, trips and barcodes move to after v1 (milestones M3 to M5; v1 is M1, M2 and M6; section 7, OQ-36, OQ-15).

## 1. Decisions

| Area | Decision |
|---|---|
| Client | Kotlin + Jetpack Compose, single Activity, MVVM + unidirectional state, Hilt DI |
| Backend | Firebase (Spark/free): Auth + Cloud Firestore. **No Cloud Functions** (they need the paid Blaze plan), so all integrity checks live in security rules |
| Sign-in | Google via Credential Manager (the legacy Google Sign-In API is deprecated[^gsi]) **and** email + password with mandatory email verification, both in v1 (OQ-23). Optional TOTP two-step verification for password accounts (OQ-24), only if the Identity Platform upgrade needs no billing (OQ-25). No email-link sign-in (OQ-27). Details: section 3.4 |
| Data location | Firestore database in **`eur3`** (EU multi-region, Belgium and the Netherlands; cannot be changed after creation[^loc]). Firebase Authentication processes data only in the US[^authus]. The privacy text (OQ-30) names both |
| Sync | Firestore snapshot listeners; offline cache on; one document per item; updates write only the changed fields; same-field conflicts resolve last write wins |
| Lists | Private to their creator by default (Q3, VIS-01); the creator may share a list with their household (VIS-02) and stop sharing it (VIS-04). A household is needed only to share (OQ-1). Type `kind` is `PLAIN` or `COLLECTION`, chosen at creation and fixed (OQ-32). Access: the creator does everything; household members of a list shared with their household do everything except stop the share or change its creator or household (OQ-2, OQ-3, OQ-4). A member who joins later sees every list already shared (OQ-16, confirmed 2026-11-18) |
| Items (v1) | Name + "I have it"; collection lists add an optional release year and re-release year (1900 to the current year + 50, OQ-6, OQ-19). Sorted per type (OQ-8, OQ-33), "show only missing" filter, progress "12 of 30" (OQ-9). Equal names are allowed, with a quiet "Already in this list" hint while typing (OQ-11). An item belongs to its list (OQ-18). No notes, tags, quantity, barcode or search in v1 (stories section 8) |
| Backup | No Firestore backups (they need Blaze). An in-app export of every list I can see (my own lists and lists shared with me) to a JSON or CSV file through the system file picker, in M2, before the first external tester; it also covers data portability (OQ-38, scope decided) |
| Sharing | Households: one per user; members join through a **single-use invite link** (code `<householdId>_<secret>`, a random 22-character secret of 132 bits bound to its household, M1 plan P3, #243; expires after 7 days, can be revoked). Household, invite and sharing actions need a connection (OQ-22) |
| After v1 (M3 to M5 and later) | Packing templates, scaling, merging and trips (section 4); barcode scanning (ML Kit + CameraX) and title lookup (UPCitemdb); infinite global undo/redo internally for each list, with conflict handling (owner requirement, 2026-11-18, quoted in section 7; the leave-room constraint on v1 is in section 3.2). Not in M1 or M2 (OQ-36 2026-11-17, OQ-15 2026-11-18, section 7) |
| i18n | English + Danish; all strings in resources; CI fails on missing translations. Android 13+: the system per-app language setting, made visible by an auto-generated `LocaleConfig`[^lang]; Android 8-12 follow the phone language; no in-app picker, `minSdk` stays 26 (OQ-12, decided 2026-11-17) |
| Crash reporting | Firebase Crashlytics **off by default**, turned on by an opt-in setting ("Send crash reports")[^crash]; **no Google Analytics**; declared in the privacy text and Play Data safety; in place before the first external tester (decided 2026-11-17) |
| App Check | Play Integrity provider requiring **device integrity only**, not Play recognition or licensing (the default requires `PLAY_RECOGNIZED`, which a GitHub APK cannot meet[^pi]); debug provider in CI and the emulator; about two weeks of metrics before enforcing; set up before the first external tester (decided 2026-11-17) and enforced before it (owner, #204, #15 comment 7003828200) |
| AI at runtime | No AI code and no LLM or cloud AI calls (on-device ML Kit only if barcode scanning returns after v1) |
| Distribution | Signed APK on GitHub Releases on each `v*` tag, signed with an owner-held GitHub key (never committed). Play later, with its own Play App Signing key: **separate keys**, so moving from the GitHub APK to the Play build needs an uninstall (cloud data is kept; decided 2026-11-17). Play account type and the closed test are deferred until Play release is planned. Android developer verification: a free limited-distribution account when available in Denmark (owner task, issue #120) |
| Review | Every change is a PR → CI gates → a separate Claude session with no authoring context reviews it against `REVIEW.md` → fix and re-review until only nits or deferred minors remain (max 4 rounds per batch, then one escalation reviewer decides fix, split or owner) → the merge agent squash-merges every READY PR that is not owner-only; an owner-only PR waits for the owner's approval or the approver's record (`docs/ORCHESTRATION.md` §7.5) |
| Repo | **Public** (unlimited free GitHub Actions minutes). No secrets in the repo; secrets live in GitHub secrets |

[^gsi]: https://developer.android.com/identity/sign-in/legacy-gsi-migration
[^loc]: https://firebase.google.com/docs/firestore/locations
[^authus]: https://firebase.google.com/support/privacy ("Firebase Authentication processes data exclusively in the United States")
[^lang]: https://developer.android.com/guide/topics/resources/app-languages#auto-localeconfig (`androidResources { generateLocaleConfig = true }` plus `res/resources.properties` with `unqualifiedResLocale`; the system setting exists on Android 13+ only)
[^crash]: https://firebase.google.com/docs/crashlytics/android/customize-crash-reports#enable-reporting (manifest `firebase_crashlytics_collection_enabled=false`, then `setCrashlyticsCollectionEnabled(true)` on opt-in)
[^pi]: https://firebase.google.com/docs/app-check/android/play-integrity-provider ("By default, App Check requires the PLAY_RECOGNIZED app recognition label"; the advanced settings can require device integrity instead)

## 2. Repository layout

```
/app                  Android app (Compose UI, navigation, DI wiring)
/core/domain          Pure Kotlin/JVM: models, sorting, filtering, validation (scaling and merging after v1)
/core/data            Firestore + Auth repositories, mappers
/core/testing         Fakes (in-memory repositories), test fixtures
/firebase             firestore.rules, firebase.json, rules tests (Jest); firestore.indexes.json comes with the first composite query (none in M1)
/docs                 PLAN.md, ORCHESTRATION.md, ADRs (adr/), milestone plans, product docs
/scripts              verify.sh and guard scripts used by CI and git hooks
REVIEW.md             Review rubric and severity definitions
CLAUDE.md             Agent instructions: the only commands to run, and the rules
```

`core/domain` has **no Android or Firebase dependencies**, so most logic gets fast JVM tests.

## 3. Data model (Firestore)

```
users/{uid}                      { householdId, name? }                // only the user; name: AUTH-12 (P9)
households/{hid}                 { name, createdBy, createdAt, ownerUid, deleted: bool }
households/{hid}/members/{uid}   { role: owner|member, displayName, joinedAt, viaInvite? }
households/{hid}/removed/{uid}   { removedAt }                         // owner only: unsharing still to do
invites/{code}                   { householdId, householdName, createdBy, createdAt, expiresAt }  // code: <householdId>_<secret>
lists/{lid}                      { kind: PLAIN|COLLECTION, name, createdBy, sharedWith: hid|null,
                                   schemaVersion, createdAt, updatedAt, updatedBy }
lists/{lid}/items/{iid}          { name, have: bool, releaseYear?, reReleaseYear?,   // years: COLLECTION only
                                   createdBy|null, createdAt, updatedAt, updatedBy|null }  // null = anonymised (proposal, OQ-18)
config/app                       { minVersionCode }                    // anyone reads, even signed out; owner edits in the console
```

Lists are **top level**, not under a household: a list exists without a household (OQ-1), and it stays with its
creator when they leave, are removed or the household is deleted (OQ-5, OQ-17), so only `sharedWith` changes and no
data moves. LIST-01 runs two queries: `createdBy == uid` and `sharedWith == myHousehold`. A member who joins later
sees the lists already shared (the second query; OQ-16, confirmed 2026-11-18). An item belongs to the list it is in
(OQ-18): items a person added to other people's lists stay there, shown as added by a former member once the person is
no longer a member; items others added to that person's shared lists go with those lists (they go with the creator).
`schemaVersion` and the `minVersionCode` field of the app config document let a newer app ask older installs to
update ("Update the app" screen): GitHub APKs cannot be force-updated. "Most recently used" (OQ-35, decided
2026-11-18) is the last time *I* opened the list, kept on the device only (no Firestore reads or writes); lists never
opened on this device follow `updatedAt`. Where the overview progress counts (OQ-9) are stored is decided in M2 planning (section 3.3).

### 3.1 Security rules (no Cloud Functions, so everything is enforced here)

Every rule below gets at least one allow test and one deny test in the emulator.
P1 to P9 are the rules decisions of the M1 plan (`docs/milestones/M1.md` section 8), written into this section by M1-35.
Notation: `uid` is always the caller, `request.auth.uid` (P1, #206), so a path such as `/users/uid` or `members/uid`
is the caller's own doc; `{uid}` in a path is the document id, which a row ties to the caller where it says so. `get`/`exists` see the state **before** a batch, `getAfter`/`existsAfter`
see it **after**. `M(x)` means `exists(/households/$(hid)/members/$(x))`. `O(x)` means
`get(/households/$(hid)).data.ownerUid == x`. `LIVE` means
`get(/households/$(hid)).data.deleted == false`. Every household, member, invite and shared-list rule below
requires `LIVE` **except** Create household (no doc exists yet), Cleanup and a member's delete of their own member
doc (only when `deleted == true`, P6) and the tombstone read (below); the users-doc set checks the reverse, that the
household is live after the batch (P5). Rules that involve no household need no `LIVE`: `users/{uid}`, the `config` app document, Create
list, and the creator's own access to their lists and items.

**Signed in** means `request.auth != null && request.auth.token.email_verified == true`[^ev]. Every rule below,
including the invite `get`, requires it, with two exceptions: the own `users/{uid}` doc needs only
`request.auth != null` (AUTH-06, HH-03), and the `config` app document is readable by anyone, even signed out (so an
old app can say "Update the app" before sign-in or verification). The `config` app document has no client writes. No rule relies on a two-step (MFA) claim.

**Reads**: members (`M(uid)`, `LIVE`) can read the household doc, its members and its invites (a plain member lists
only the invites they created, the owner all: Query invites below, #280); the `removed`
markers are owner-only (no recursive member read rule over the household).
`users/{uid}` can be read and written only by that user, and holds nothing but
`householdId`, which enforces one household per user (HH-01, HH-03), and `name`, the user's own name (AUTH-12, P9). The
`householdId` field is always present: the doc is
created with `householdId: null` (first sign-in, or before the first household action), and no write may drop
the field. Deleting the doc is allowed only when `householdId` is `null`, never while it holds a value, live or stale
(P5, #210 item 1; account deletion leaves or self-heals first):
* `name` may be missing (the start gate then shows the name step, AUTH-12); when written it is a string of 1-50 code
  points, non-empty after trim (P4). The own-doc exception for unverified users (above, Signed in) covers it, so create account
  saves the name before verification. It is not the Auth profile `displayName`, which Google sign-in fills in. The
  member doc's `displayName` is a copy: set from `name` in the create-household and join batches (M1-18) and changed
  together with it in one batch (M1-39); no rule compares the two. Tests (M1-08): allow create with and without
  `name`, an update of `name` alone, by an unverified user too, a 50-code-point name with non-BMP characters; deny a
  51-code-point name, spaces only, a non-string, an unknown field;
* set (`null` → `hid`) only together with `existsAfter(/households/hid/members/uid)` **and**
  `getAfter(/households/$(hid)).data.deleted == false` (the create-household and join batches; P5, #210 item 2: a user
  cannot point back at a tombstone whose cleanup still keeps their member doc); a direct change from one household to
  another is denied;
* cleared (`hid` → `null`) only when `!existsAfter(/households/hid/members/uid)` (in the Leave batch, after
  a removal, or under a tombstone once the user's own member doc is gone: P6 deletes it first or in the same batch,
  and the owner's cleanup deletes the owner's). The owner never writes another user's doc: a removed member's or a
  deleted household's former member's app sees the stale value at start and clears it itself (self-heal; the tombstone's own owner clears it after the cleanup instead, see Delete household).
  Self-heal order: first set `sharedWith = null` on the user's own lists shared with the stale `hid` (all
  pages; M2), then, for a tombstone, delete the user's own member doc (P6, Delete household row), then clear `householdId`. Join needs a cleared value, so the person cannot rejoin, and so
  re-share their lists, before the unsharing has finished (OQ-5).
* Tests (M1-08, member and household docs seeded with rules off): allow create with `householdId: null`, set while the
  own member doc exists in a live household (the create-household and join batches themselves: M1-10, M1-54), clear after
  removal, clear under a tombstone once the own member doc is gone, delete the doc when `null`; deny create with a household, set without
  membership, `hid1` → `hid2`, clear while still a member of a live household, clear while the own member doc still exists under a tombstone,
  drop the field, delete the doc while
  `householdId` holds a live household and while it holds a stale one (after removal, and a tombstone; P5), set
  `null` → the id of a tombstone while the user's member doc still exists there (P5), any write to another user's doc
  (all M1-08). Tests (M1-11, where the Leave and P6 member-doc deletes exist): allow the clear in the Leave batch and in
  one batch with the P6 delete under a tombstone. A user may also `get` their own `members/{uid}` path in any household (it may not
  exist) and the household doc while it is a tombstone and their `householdId` points at it: that is the
  signal for the HH-06 "household deleted" dialog and for the self-heal, except for the tombstone's own owner (`ownerUid` is the user), whose start resumes the cleanup and the owner's clear (Delete household row) with no HH-06 dialog and no self-heal clear.
A list is readable by its creator (`createdBy == uid`) always, and by others only when
`sharedWith != null && M(sharedWith) && LIVE(sharedWith)`. Items follow their list (`get` of the parent list). Item rules match `/lists/{lid}/items/{iid}`, never a bare `/lists/{lid}/{document=**}`: with `rules_version = '2'` that also matches the list doc, so the item rule would apply to list writes too (the #199 trap). M2 deny test: a write to the list doc (`createdBy`, `sharedWith`, `kind`) that only the item rule would allow.

[^ev]: https://firebase.google.com/docs/reference/rules/rules.firestore.Request#auth

**Writes**, path by path:

| Path / action | Allowed when |
|---|---|
| Create household + owner (one batch) | Household: `hid.matches('^[A-Za-z0-9]{20}$')` (Firestore's auto-id; P3, #243), `!exists(household)`, `createdBy == ownerUid == uid`, `deleted == false`, **and** `existsAfter(members/uid)`. Member doc: its id is `request.auth.uid` (P1, #206) **and** `!exists(household)` **and** `getAfter(household).ownerUid == uid` **and** `role == owner` **and** `joinedAt == request.time` (as in Join) **and** the one-household check (below). Tests (M1-10): deny a member doc for another uid, alone and as a second member doc next to the caller's own; deny a household id of 19 or 21 characters or with `_`, `-`, `.` or `*` (P3); allow the 20-character auto-id. The P4 key and length tests of both docs are in field validation (below). Household docs are never deleted: no rule allows `delete` on `households/{hid}`, for anyone, live or tombstone (see Delete household). So `!exists` can never be true again for an id that has existed. A former creator can't become owner again, and nobody can reclaim leftover data. Tests: deny re-creating a deleted household's id (tombstone in place), also by its former owner with the owner member doc in the same batch. |
| Create invite `invites/{code}` | `M(uid)` of `householdId`; `createdBy == uid`; `createdAt == request.time`; `expiresAt <= request.time + duration.value(7, 'd')`; `code.matches('^[A-Za-z0-9]{20}_[A-Za-z0-9_-]{22}$') && code.split('_')[0] == householdId`: the code is `<householdId>_<secret>`, the secret 22 characters from a secure random source (132 bits), so a deleted code can be re-created only for its own household (P3, #243, #210 item 3; no data goes into the pattern, so the check holds on its own); `householdName == get(/households/$(householdId)).data.name` (P2, #200; spike (e) counts the read). No updates. Tests (M1-12): allow a member's create with the household's name and a well-formed code; deny a stored name that differs from the household's, a code with another household's prefix (a revoked or used code of `h1` re-created by a member of `h2`, the #243 probe), a secret of 21 or 23 characters or with a character outside the alphabet, a code without the prefix, and a create by a member of a household seeded (rules off) with a 20-character id holding `.` or `*` that names another household's code. Accepted residual (P3): a member of the same household can re-create a revoked code of that household; they could send a new link anyway. |
| Read one invite (`get`) | Any signed-in user with a verified email (they need the code). The join screen shows the invite's `householdName`, never a name from the URL (P2, M1-20). Under a tombstone (`LIVE`) and for a code that does not exist (used, revoked or never made) the get is denied; M1-20 shows HH-03's message for either. Tests (M1-12): allow a verified non-member with the code to read it, `householdName` included. |
| Query invites (`list`) | Only queries filtered on `householdId == hid` where `M(uid)`; a plain member's query also on `createdBy == uid`, the owner's (`O(uid)`) on `householdId` alone, so a member sees and revokes the invites they created and the owner all of the household's (HH-02). Owner decision on #280 (M1-O12, #15 comment 7081223083): a plain member never learns another member's open code, with which they could rejoin alone after a removal. Nobody can enumerate other codes. Tests (M1-12): allow a plain member's query on `householdId` and `createdBy == uid` and the owner's on `householdId`; deny a plain member's query without the `createdBy` filter or with another member's uid, a query without the `householdId` filter or on `householdId in [mine, another]`, a query by a non-member, a removed member or another household's owner, and one under a tombstone. |
| Delete invite | Its creator or the owner (revoke); **any member** once `expiresAt < request.time` (cleanup; since #280 the app's cleanup uses the creator's and the owner's paths, see Expired invites, and this path stays: it deletes only invites no join accepts); the joiner in the join batch (below). |
| Join (one batch) | Create `members/{uid}`, its id `request.auth.uid` (P1, #206), with `role == member`, `joinedAt == request.time`, `viaInvite == code`, where: `!M(uid)` before the batch; the invite exists, points at `hid` and hasn't expired; the invite's creator is **still a member** (`M(invite.createdBy)`); **and** `!existsAfter(invites/{code})`, so the join is only valid if the same batch deletes the invite. That delete is allowed only if `!M(uid) && getAfter(member).viaInvite == code`, so an existing member can't burn someone else's invite. Single use follows from the delete. The member create also needs the one-household check. Tests (M1-54, P1): deny the #206 batch (the caller's own member doc, a member doc for another uid, the invite delete and the caller's users-doc set), and a batch whose only member doc is for another uid. |
| One-household check (member create in Create household and Join) | `exists(/users/uid)` **and** `get(/users/uid).data.householdId == null` **and** `getAfter(/users/uid).data.householdId == hid`, so the same batch must write the users doc. A missing doc fails the check (no bypass by deleting it). A stale value (after removal or deletion) must be self-healed first. Deny tests: join or create without the users-doc write; with no users doc; while `householdId` points at another household. The extra `get`/`getAfter` count in spike (e). |
| Update own member doc | Only `displayName` may change (`affectedKeys().hasOnly(['displayName'])`), 1-50 code points, non-empty after trim (P4). Tests (M1-10): allow exactly 50 code points; deny 51, spaces only, another member's doc, an added field. |
| Leave | A member who is not the owner (`!O(uid)`) deletes their own member doc. The client also deletes that member's invites (allowed: the creator may delete their own invites) and sets `sharedWith = null` on the lists they created (allowed: creator), so those lists go with them (OQ-5). Order, as for the self-heal: first unshare the user's own lists shared with `hid` (all pages; M2), then send the Leave batch (member delete, invite deletes, users-doc clear), so an interrupted Leave leaves a member with private lists, never shared lists with no way to resume. |
| Remove member | `O(uid)`, and the target isn't the owner before **or after** the batch (`target != getAfter(household).data.ownerUid`), so a batch can't hand ownership to someone and remove them at the same time. The same batch deletes the removed member's open invites and writes the marker `households/{hid}/removed/{uid}` with `removedAt == request.time`: a create **or an overwrite** of a leftover marker, so removing the same person again after a rejoin works (the member delete requires `getAfter(removed/target).data.removedAt == request.time`). Write: only `O(uid)`, only when `M(target)` before and `!existsAfter(members/target)`; the marker holds only `removedAt` (P4). Read, list and delete: only the owner. Tests (M1-11): allow remove, rejoin, remove again; deny a marker create or overwrite with another field (P4); deny a non-owner write, a write while the target stays a member, a non-owner member reading, listing or deleting a marker. **M1 writes and deletes it**: M1 has no lists, so the owner's client deletes the marker right after the Remove batch; M2 inserts the list unsharing below before that delete. The owner's client then sets `sharedWith = null` on the removed member's lists shared with this household, in pages (query `sharedWith == hid && createdBy == target`; allowed to the owner only when `!existsAfter(members/createdBy)`; OQ-5), and deletes the marker last; an unfinished marker is resumed at the owner's next app start. If an unshare is denied because the person is a member again (rejoined through another invite) or the household was deleted meanwhile, the client deletes the marker instead of retrying; cleanup deletes any markers left. The removed member's own app also unshares them at its next start (creator path). Until one of them finishes, the remaining members can still read those lists, which they could already read; the removed member loses access to everyone else's lists at once. A list query on `sharedWith` cannot also check that the creator is a member, because rules are not filters: the condition would depend on each document's `createdBy`. Even if that cleanup is skipped, the `M(invite.createdBy)` check makes those invites unusable while the person is not a member. Accepted residual risk: if they rejoin through someone else's link, any of their old invites that haven't expired (7 days at most) start working again. |
| Transfer ownership (one batch) | Updates `household.ownerUid` and the `role` of both member docs. Household update: `O(uid)`, only `ownerUid` changes, the new owner is a member both before and after the batch (`M(new)` and `existsAfter(members/new)`), **and** after the batch the old owner's member doc has `role == member` and the new owner's has `role == owner` (`getAfter(members/<old ownerUid>).data.role` and `getAfter(members/<new ownerUid>).data.role`; two more calls, counted in spike (e)), so a partial transfer is denied. Each member-doc update: only `role` changes, `O(uid)` before the batch, and the new role equals `getAfter(household).ownerUid == thisDoc ? owner : member`. `ownerUid` is the single source of truth, so there is always exactly one owner. `role` is a cached copy for display, and rules use `O(x)`. The caller check is `O(uid)`, never `M(uid)`: only the current owner can transfer, so a plain member cannot make themselves owner. Tests: allow the owner's transfer batch, also on a household seeded with `createdBy: null`; deny a plain member setting `ownerUid` to themselves, with a single household-doc update and with the full transfer batch (the member-doc updates also need `O(uid)`); deny a signed-in non-member setting `ownerUid` to an existing plain member (the role checks deny any household update without both role updates, so a plain member's full batch is the case that tests the caller checks); deny a transfer to a non-member; deny partial transfers: the household update with no role updates, with only the old owner's role update (no owner), and with only the new owner's role update (two owners). |
| Create list | `createdBy == uid`, `sharedWith == null`, `kind` in `PLAIN`, `COLLECTION`, plus field validation (below). |
| Update list | The creator, or a member of `sharedWith` while `LIVE` (OQ-3). `kind`, `createdBy` and `createdAt` never change. `sharedWith` changes only: by the creator, `null` → their own household (`M(uid)`, `LIVE`) or back to `null` (VIS-02, VIS-04, and the self-heal after leaving, removal or deletion); by the owner in Remove member (above), to `null` only. |
| Items: create, update | Same people as Update list. On create `createdBy == uid` and `createdAt <= request.time` (OQ-37, decided: Undo keeps the original value). An Undo by another member restores the original adder (OQ-18, section 3.2); how the create rule allows that is settled in M2 planning. On update `createdBy` and `createdAt` never change, with one exception: **anonymise**, the planner's proposal for OQ-18 (the owner decided only that the person's name is removed; the shape is confirmed in M2 planning, `risk:high`, `area:security-rules`; the alternative of no rules exception is weighed there, because items store a uid, display names live in `members/{uid}`, and `households/{hid}.createdBy` keeps a uid anyway). An update by the person named in `createdBy` and/or `updatedBy` may set exactly those fields to `null` and change nothing else (`updatedAt` untouched); it is allowed only while that person can still read the list. Years only in `COLLECTION` lists. Deny tests: changing `createdBy` or `createdAt` on update, a future `createdAt`, years in a `PLAIN` list; anonymise: allow the person's own uid → `null`, deny setting another user's uid to `null`, deny changing any other field in the same write, deny `null` → a uid. |
| Delete list, items | Same people as Update list; the client deletes the items first, in pages, then the list. |
| Delete household | `O(uid)`. **Soft delete**: first one update sets `deleted: true`. This update **must** clear the name (`request.resource.data.name == ""`, owner decision on #205) and may change only `deleted` (false → true) and `name` (→ empty); `ownerUid`, `createdBy` and `createdAt` stay as they are, so no household name, for example a street address, outlives the household. From that moment `LIVE` is false, so every read and write under the household is denied to everyone except the owner's cleanup and a member's delete of their own member doc (P6). Then the client deletes invites → `removed` markers → members in pages. Lists shared with the household go back to their creators (OQ-17) without any owner write: from the moment `LIVE` is false only creators pass the list read rule. Each creator's app sees the tombstone at its next start (the tombstone read above), shows the HH-06 dialog, clears `sharedWith` on its own lists, deletes its own member doc (P6) and clears its `householdId`. This follows the stories planner note (`docs/product/stories.md` section 11): creators, not the owner, make their lists private again. The tombstone's name is cleared, so the dialog shows the household name from the app's own copy (kept while the household was live, see "HH-06 household name" below) and, when the device has none (after sign-out or a reinstall), the body without the name: "Your household was deleted. ..." / "Din husstand er slettet. ...", the rest of the approved wireframe 20 text unchanged (owner decision, #15 comments 7011161000 and 7013424005). **Cleanup rule**: while `deleted == true`, the owner (`O(uid)`) may read, list (including the invites query on `householdId`) and delete what is under the household: **one rule per subcollection** (`members/{uid}`, `removed/{uid}`), plus the top-level `invites` with that `householdId`. The one other write: a member may delete their own `members/{uid}` (nobody else's), which the self-heal does before it clears `householdId` (P6, #242; M1-31), so no display name stays when the owner never finishes the cleanup. Nobody else may do anything. Test (M1-31, emulator): a plain member's start under a tombstone deletes their own member doc, then clears `householdId`; after a crash between the two, the next start finishes the clear. Open: follow-up #281 (target M1; R1-A-02, R1-B-07 of PR #265): the member's own invites under an abandoned tombstone keep their uid and `householdName`. It is never written as `match /households/{hid}/{document=**}`: with `rules_version = '2'` a recursive wildcard also matches zero segments, so it would match the household doc itself, and the owner could delete the tombstone and re-create the id (#199). If a recursive match is used, it needs at least one segment (`/households/{hid}/{sub}/{document=**}`). No rule ever allows `delete` on `households/{hid}`, not even for the owner while `deleted == true`. The household doc itself stays as a tombstone (`{ createdBy, createdAt, ownerUid, deleted: true, name: "" }`; field validation accepts the empty name only on tombstones), so its id can never be reused. Tests: allow a soft delete by the owner that clears `name`; deny a soft delete by a member who is not the owner and by a signed-in non-member (with `name` cleared, so only the caller check can fail); deny a soft delete that leaves `name` non-empty, one that changes anything besides `deleted` and `name`, and `deleted` true → false; deny deleting the household doc by the owner while `deleted == true`, by the owner of a live household, and by any other user; allow the cleanup deletes of invites, `removed` markers and members; allow a plain member deleting their own member doc under a tombstone, alone and in one batch with their users-doc clear, and deny them deleting another member's (P6, M1-11; under a live household the Leave row applies unchanged); deny cleanup by a non-owner, and the owner deleting a member doc of a live household outside Remove member (for example their own), which shows that the cleanup rule needs `deleted == true`. Deny every write under a soft-deleted household except the cleanup deletes and P6: the owner's full transfer batch (the household update plus both role updates; the role checks already deny the household update alone), a join with an unexpired invite, an invite create, a member's `displayName` update, and an owner create or update of a member doc (the cleanup allows only read, list and delete). The end-to-end case (delete the tombstone, re-create the id, read a list still shared with it: deny) needs the list read rule, so it is an M2 list-rules test; in M1 the tombstone-delete deny above catches the same hole. A crash mid-cleanup leaves data no one can access, and the next app start resumes the cleanup. When the cleanup has finished, the owner's client clears its own `householdId` (M1-31; M2 first unshares the owner's own lists shared with the household, as in the self-heal order) and deletes the household-name copy; the owner sees no HH-06 dialog. Until then the stale `householdId` lets the next start resume the cleanup (owner decision, #15 comment 7021901747). |

**HH-06 household name.** The dialog's household name does not come from Firestore's offline cache: once the tombstone is read (by the self-heal or a listener), that cache holds the tombstone with `name: ""`. The app keeps its own copy of the live household's id and name (`{householdId, name}`) in app-private storage: M1-18 owns the store and writes it whenever the app reads the live household doc, replacing a copy that holds another household id. The HH-06 state uses the name only when the copy's `householdId` equals the tombstone's id, and otherwise shows the body without the name. The copy is deleted by the code that ends the state: M1-18 on acknowledgement of its HH-06 state and in the removal self-heal; M1-31 wherever it clears `householdId` itself, in Leave and in the owner's clear once the Delete household cleanup has finished (Delete household row); and in the sign-out steps: M1-18 adds the deletion to step 3 of the M1-14 sign-out (next to `clearPersistence`), which M1-32 repeats after the Auth user is deleted, so a device that signed out or deleted the account keeps no name. Tests (M1-18, emulator): the HH-06 state carries the name the device saw while the household was live; a copy saved for household A gives no name for B's tombstone; the copy is gone after acknowledgement, after the removal self-heal and after sign-out. Tests (M1-31): the copy is gone after Leave and after the owner's clear once the cleanup has finished.

**Removal notice** (wireframe 40, P8, #250): the removal self-heal moves the name from the copy, with the same
`householdId` match, into the removal-notice state before it deletes the copy. With no usable copy the notice uses the
approved story text without a name: "You were removed from the household" / "Du er fjernet fra husstanden". Tests:
M1-18 (the state carries the name; a copy for another household gives none), M1-21 (both texts, en and da).

Rules can't count members, so "the owner can't leave while others remain" is
enforced by the rule shapes above: the owner can't use Leave, so they must transfer
ownership or delete the household.

**Spike (M1-09, after the rules base M1-08, which it builds on; #260 item 5)**: prove in the emulator that (a) the invite `list` rule,
filtered on `householdId` with a membership `exists()`, is accepted, (b) the join
batch with `existsAfter`/`getAfter` works, (c) the transfer batch works, (d) the list query
`sharedWith == hid` with `M(hid)` and `LIVE` is accepted, and (e) every batch stays within the
rules limits of 10 `get`/`exists` calls per single-document request or query and 20 per batch[^calls],
counting the reads added by P2 (household name on invite create) and P5 (tombstone check on the users-doc set)
(Remove member and cleanup batches are paged to fit). If (a)
fails, the fallback is to nest invites under the household, with a top-level
`inviteCodes/{code} → hid` index used only for `get`; that index keeps P2 and P3 (it holds `householdName` with the
same equality check, and its create rule has the same code check), with the Create invite row's allow and deny tests.
**Spike result** ([ADR 0002](adr/0002-rules-spike.md)): (a) to (d) work in the emulator, so invites stay top level, and the
invite list works in the shape decided on #280. (e), with every call counted (the emulator caches calls on one document, so
it cannot show this) and the ADR's rule layout: the join is the largest fixed batch, 12 calls; Leave keeps at most 8
invite deletes in its batch and Remove member at most 6, any more go first in pages of up to 10; pages of tombstone-cleanup
or expired-invite deletes hold up to 10.

[^calls]: https://firebase.google.com/docs/firestore/security/rules-conditions#access_call_limits

**Field validation** on every write:
* types, string lengths and allowed enum values. **Keys** (P4, #203): every create checks
  `request.resource.data.keys().hasOnly([...])` and `hasAll([...required])`; every update row checks
  `request.resource.data.diff(resource.data).affectedKeys().hasOnly([...])` with the keys its row names (users doc:
  `householdId`, `name`; own member doc: `displayName`; transfer: `ownerUid` on the household, `role` on each member doc; soft delete: `deleted`, `name`;
  marker overwrite: `removedAt`). Keys, all required unless marked: `users` `householdId`, `name` (optional);
  `households` `name`, `createdBy`, `createdAt`, `ownerUid`, `deleted`; `members` `role`, `displayName`, `joinedAt`,
  `viaInvite` (Join only); `removed` `removedAt`; `invites` `householdId`, `householdName`, `createdBy`, `createdAt`,
  `expiresAt`; lists and items as in section 3 (M2). **Lengths** in code points as the app counts them (in the
  rules `matches('(?s).{1,N}')`, because `size()` counts UTF-16 units; owner decision, #15 comment 7083518706), non-empty after trim: household name, `displayName` and `users.name` 1-50 (`householdName` equals the
  household's; a tombstone's empty name is the one exception, Delete household); M2 planning sets list and item names (proposal: 80 and 200). The same numbers drive the UI field errors
  (M1-13). Tests per collection (M1-08 users, M1-10 households and members, M1-12 invites, M1-54 the join member doc,
  M1-11 markers, M1-53 the transfer updates): an unknown field on create and an update that adds one (deny); a create without one required key (deny; at least
  the owner's member doc without `joinedAt`, M1-10); a transfer that adds `role` to the household doc (deny, M1-53); for each
  name exactly the maximum (allow), the maximum + 1 and spaces only (deny), and 50 code points with non-BMP characters
  (allow; M1-13 has the matching property). That test showed `size()` counting UTF-16 units (M1-08), so the task stopped
  and asked, and the owner chose the regex above rather than a changed number;
* years: whole numbers from 1900 to `request.time.year() + 50`, both optional, no rule between them (OQ-6, OQ-19);
* on documents that have those fields (lists, items; P5, #210 item 6), `updatedBy == request.auth.uid` and
  `updatedAt == request.time`; a `removed` marker's `removedAt == request.time`;
* `createdAt` and `createdBy` can't change on update; on create `createdBy == request.auth.uid` and
  `createdAt == request.time`, except items, where `createdAt <= request.time` (OQ-37, decided 2026-11-17);
* type and presence checks accept `null` for `createdBy`, `ownerUid` and `updatedBy` where the stored value is already `null`; comparisons with the caller (`O(x)`, `M(new)`, `updatedBy == request.auth.uid` on the written value) still apply. "Never changes" is a separate clause per field, so a later narrow exception that sets one of them to `null` (on a tombstone, on `households.createdBy`, on `lists.updatedBy`; #205, M2 planning decides whether kept uids are acceptable at all) is an addition, not a rewrite of the rows above. Tests: allow a transfer and a soft delete on a household seeded with `createdBy: null`, and the tombstone read and the cleanup on a tombstone seeded with `createdBy: null` (M1-10, M1-11); a list update on a list seeded with `updatedBy: null` (M2). `ownerUid` stays a uid in these tests: `null` there would end the cleanup for good, which M2 planning must weigh;
* two exceptions to the bullets above: (1) the item anonymise write of section 3.1 (the planner's proposal for
  OQ-18) only sets `createdBy` and/or `updatedBy` to `null`, changes nothing else, and leaves `updatedAt` as it is;
  (2) the Undo create that restores the original `createdBy` (section 3.2; how rules allow it is settled in M2
  planning).

**Account deletion** (required by Google Play): in-app "Delete my account" (AUTH-04). A member
leaves; an owner with other members must transfer ownership first, and the UI
guides them; a last member deletes the household. Before the member leaves, while they can still write to those
lists, the app anonymises the items the user added to or last changed on other people's shared lists. The owner
decided (OQ-18, 2026-11-18) that those items stay and the person's name is removed; how is the planner's proposal,
kept by the owner as the working design (#15 comment 7000527780: own uid → `null`, nothing else) and to be confirmed
in M2 planning together with the gap below: per list a query on `createdBy == uid` and one on `updatedBy == uid`, in pages,
using the anonymise rule (section 3.1; M2, together with the unsharing steps). Then the
member leaves, and the app deletes the lists the user created (items first, which also removes what others added to
them), `users/{uid}` and the Auth user. A last member's household cleanup (all pages) and the clear of their
`householdId` finish before `users/{uid}` and the Auth user are deleted; a crash in between resumes the cleanup first
(P7, #205 item 5). Test (M1-32): crash after the soft delete, restart, then no member doc remains and the account is
gone. Deletion needs a recent sign-in[^reauth]
(`FirebaseAuthRecentLoginRequiredException`): the app asks for Google, or the password plus a TOTP code when
two-step verification is on, before it starts, so nothing is left half-done.
**Still open, deferred to M2 planning by the owner (#15 comment 7000513565, on questions 6992973369 and
6994571090; to be decided together with the rule shape):** the proposal works only while the person can still write
to the list. If they already left or were removed, or the list's creator stopped sharing it (VIS-04), or the
household was deleted, and they delete their account later, their uid stays in `createdBy`/`updatedBy` on those items
(no name or profile remains, and the UI shows "former member"). Accept this, or anonymise in those cases too (at leave,
removal, stop sharing and household deletion)? The last two need a different mechanism than the proposal above,
because the person loses write access at that moment.
Until it is decided in M2 planning, the proposal must not be treated as complete.
Play also requires a **web** way to request deletion, besides the in-app path[^playdel]. The owner deferred
this decision (2026-11-17): it must be settled before the first external tester and must exist before a Play
release. Options on file: a static page with a mailto link on the owner's domain next to the invite page
(recommended), GitHub Pages, or a Google Form.

[^reauth]: https://firebase.google.com/docs/auth/android/manage-users#re-authenticate_a_user
[^playdel]: https://support.google.com/googleplay/android-developer/answer/13327111 (cited by the 2026-11-17 best-practices investigation, issue #15)

**Expired invites**: the cleanup runs per creator and by the owner (#280). When the household screen opens, a plain
member's app queries the invites it created (`householdId` and `createdBy == uid`), the owner's app all of the
household's (`householdId`), and each deletes the expired ones (the creator's or the owner's path of Delete invite).
The queries have equality filters only and check `expiresAt` on the client, so they need no composite index:
Firestore merges the single-field indexes of equality filters[^merge] (P5, #210 item 5). TTL policies are not relied on.

[^merge]: https://firebase.google.com/docs/firestore/query-data/index-overview ("Use index merging": "Cloud Firestore can merge the indexes for simple equality filters"; fetched 2026-11-24)

**App Check** (Play Integrity, free) as decided in section 1: device integrity only, debug provider
in CI and the emulator[^acdebug], metrics watched for about two weeks before enforcing[^acmon]; set up and enforced
before the first external tester (#204, section 3.3). It is extra protection against scripted abuse, also of sign-up (email
enumeration protection still returns `EMAIL_EXISTS` on sign-up[^enum]; the owner accepts that for v1, OQ-34(d),
2026-11-18: the app shows the same screen either way).

[^acdebug]: https://firebase.google.com/docs/app-check/android/debug-provider
[^acmon]: https://firebase.google.com/docs/app-check/monitor-metrics
[^enum]: https://cloud.google.com/identity-platform/docs/admin/email-enumeration-protection

### 3.2 Sync semantics

* Writes use `update()` on specific fields, never `set(merge)`. An offline edit to an
  item that was deleted meanwhile fails instead of bringing the item back; the UI
  shows "this item was removed".
* "I have it" and edits are last write wins per field. Any stored counter (section 3.3) uses
  `FieldValue.increment`, so concurrent changes both count.
* Undo after deleting an item (ITEM-03) re-creates the document with its old id and fields. The delete is
  written at once, so other members see it at once. The Undo snackbar stays until the user acts, dismisses it or
  leaves the list; nothing waits on it (OQ-39, decided 2026-11-18, Material 3).
* **OQ-37 (decided 2026-11-17, C5 of the investigation):** Undo keeps the original `createdAt`, so the item
  keeps its place in the "oldest added first" tie-break (ITEM-05). Rules cannot tell an Undo from any other
  create, so every item create accepts any `createdAt` not later than `request.time` (a forged older value
  only changes a tie-break order). `createdBy` is the caller, so a normal create records the caller as the
  adder; an Undo is the exception (below). **OQ-18 addition (owner, #15 comment 7000527780, question 2 of
  6992973369):** an Undo by another member restores the ORIGINAL adder, not the member who pressed Undo. The client
  re-creates the item with its original `createdBy` (and `createdAt`); so the create rule has to accept the original
  adder's uid on an Undo. Whether rules can tell this from a forged `createdBy`, or which values the create rule
  accepts instead (as for `createdAt` above), is settled in M2 planning (`risk:high`, `area:security-rules`). That
  rule must also allow a `null` `createdBy` on an Undo (the original adder may already be anonymised). The owner's
  decision covers the adder only: `updatedBy` stays the caller (section 3.1, field validation). M2 planning decides
  whether an Undo may restore the uid of an account deleted in the meantime (for example the client writes `null` when
  the adder is no longer a member; that also covers a member who only left, which ties in with the open gap in section
  3.1, account deletion). The aim is that an Undo does not undo the anonymisation.
* **Leave room (area:sync-merge):** the owner wants infinite undo/redo per list after v1, with conflict handling that lets
  an undo after a conflict show the other side (stories section 9, #15 comment 6991020343). v1 keeps no history and
  stays last write wins per field, as above; the only constraint on the sync-merge design is that it must not rule
  out adding, later, a per-list change history and keeping the losing side of a conflict.
* Timestamps use `serverTimestamp()`. They are read with
  `ServerTimestampBehavior.ESTIMATE` so pending local writes still sort correctly.
* Losing access while offline (stop sharing, removal, household deleted): the queued writes are rejected
  by the rules and dropped, and the user sees a short message (SYNC-02).
* The offline banner (OQ-14) uses snapshot metadata (`isFromCache`, `hasPendingWrites`).
* Tests: emulator integration tests for concurrent increments, an edit racing a
  delete, losing access while offline, and offline-then-reconnect (`disableNetwork` / `enableNetwork`).

### 3.3 Free-tier budget

The Spark plan has no billing: past the daily free quota (50,000 reads, 20,000 writes, 20,000 deletes,
1 GiB stored, reset around midnight Pacific[^quota]) requests fail until the reset. `eur3` costs more than a
single region only once billing exists. What is billed[^price]:
* every document a query or listener returns; a listener that was **disconnected for more than 30
  minutes** is billed as a brand-new query, so reopening a list later re-reads all its items;
* every document a rule reads with `get()`/`exists()`, even when the rule denies the request
  (list and item rules read the list and the membership doc);
* `count()` cannot be used offline or with listeners[^count], so the "12 of 30" progress (OQ-9) comes from
  the open list's listener, and the overview needs either stored counters on the list (kept with
  `increment` in the same batch as item changes) or a listener per list. The estimate below assumes stored
  counters: a listener per list re-reads every item of every visible list after a 30-minute gap (for example
  5 lists × 300 items × 10 opens × 10 users = 150k reads a day, three times the free quota), so it does not
  fit the free tier at these sizes. M2 planning decides.

Rules of thumb:
* One snapshot listener per open list, detached when the screen closes, so items
  are served from the local cache when you go back. Sorting and filtering run
  on the client over that listener's data. Lists are capped at 2,000 items
  (enforced by the UI and documented; the rules cap follows before external testers, below).
* Estimate (redone for C4): 10 users, each opening a 300-item list 10 times a day, more than 30 minutes
  apart, is about 30k item reads, plus about 10 reads per overview open (two queries and rules reads)
  at 10 overview opens per user a day, 1k reads: about 31k reads a day, under the 50k limit but not with a large margin. The data-layer PR for M2 must
  include a read-cost estimate per screen, with re-reads and rules reads, and an emulator test that counts
  reads where the emulator can.
* GitHub Actions: the repo is public, so minutes are unlimited.
* No backups on Spark (scheduled backups and point-in-time recovery need Blaze[^backup]), and any member can
  delete a shared list. OQ-38 (decided 2026-11-18): no Blaze; M2 builds an in-app export to a JSON or CSV file through the
  system file picker, before the first external tester (the owner's words). Scope decided (#15 comment 7000534815):
  every list the user can see, their own lists plus the lists shared with them, replacing "my lists" (any member
  can delete a shared list). The export reads every item once, so it is counted in the M2 read-cost estimate.

**Misuse and the shared quota (accepted risk, #204; owner, #15 comment 7003828200).** The quota is project-wide and
nothing in the rules yet bounds lists per user, items per list or invites per household, so one account (with or without a
household), a scripted member or a buggy client loop can use up a day's writes or reads for every household. The
owner accepts this until the first external tester (section 7): the acceptance covers only the owner's own use (#15 comment 7064913106). Response when it happens, in the Firebase console: disable
the account in Authentication, then remove its data in Firestore, but never delete a `households/{hid}` doc by hand: the
#199 rule holds in the console too, because a deleted household doc frees its id for a takeover. For a household the
account owns: soft-delete it (`deleted: true`, `name: ""`) and delete its invites, `removed` markers and the account's
member doc as the cleanup would, or, with other members, move `ownerUid` and both `role`s to another member first; for a
household it only belongs to: delete its member doc and its invites (as Remove member would). Then delete its own lists
with their items, and its users doc last. Requests work again after the daily reset. Before the
first external tester: App Check is enforced (section 3.1), and the rules cap items per list and invites per household.
The caps need stored counters, so their rule shape (with allow and deny tests, for example deny the 2,001st item and
the invite past the household limit) is decided in M2 planning (M2-01) with the counters above, and the M2 rules task it plans adds those tests.
Accepted residual (owner, #15 comment 7064904144): after the two caps one account can still use up the daily quota
through many lists; App Check and the console response above are the only controls; M2-01 revisits it.

[^quota]: https://firebase.google.com/docs/firestore/quotas
[^price]: https://firebase.google.com/docs/firestore/pricing
[^count]: https://firebase.google.com/docs/firestore/query-data/aggregation-queries
[^backup]: https://firebase.google.com/docs/firestore/backups

### 3.4 Authentication

* Providers: Google (Credential Manager) and email + password, with email enumeration protection on and the
  password policy in Require mode, minimum 12 characters, no composition rules, plus the same check in the
  app[^pw] (OQ-26). One account per email.
* Password accounts must verify their email before the rules let them in (section 3.1, AUTH-06). Email
  templates and the default Firebase pages in English and Danish, language set per request with
  `setLanguageCode`/`useAppLanguage`[^mu] (OQ-29).
* Google is a trusted provider only for `@gmail.com` addresses[^users]. A non-Gmail Google sign-in whose email
  already has a password account fails; v1 shows "This email already has an account. Sign in with your email
  and password." Linking comes after v1 (OQ-31; decided 2026-11-17).
* Optional TOTP (AUTH-09) needs the Identity Platform upgrade (on Spark: up to 3,000 daily active users[^lim])
  and is enabled by the owner through the Admin SDK or REST, not the console[^totp]. A lost authenticator is
  reset by the owner with the Admin SDK[^mfa] (runbook in the M1 plan; OQ-28).
* Recent sign-in before deleting the account and changing the password (AUTH-04, AUTH-11).

[^pw]: https://firebase.google.com/docs/auth/android/password-auth
[^mu]: https://firebase.google.com/docs/auth/android/manage-users
[^users]: https://firebase.google.com/docs/auth/users
[^lim]: https://firebase.google.com/docs/auth/limits
[^totp]: https://firebase.google.com/docs/auth/android/totp-mfa
[^mfa]: https://firebase.google.com/docs/auth/admin/manage-mfa-users

## 4. Domain logic (core/domain)

**After v1 (OQ-36, OQ-15).** The packing design below is kept for later; v1 domain code is
sorting (OQ-33), filtering and validation of lists and items.

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
  can't satisfy the coverage gate. The mutation score floor starts at 80% (owner, #254, #15 comment 7057951193;
  raised once measured, and the guard forbids lowering it).
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
   and pre-push runs the guards, the hook tests and the unit tests (it skips the Gradle unit tests for pushes that only touch
   docs, scripts, hooks, CI, agents or firebase files; unknown paths still build). It runs the hook tests (`--jobs 4`) only
   when the push changes a file they read, run or import (`scripts/hooks/prepush_scope.py --hook-tests`; unknown ranges
   run them); CI's `guards` job runs the full hook suite on every PR.
3. **Claude Code hooks** in `.claude/settings.json`, which agents can't skip:
   * PreToolUse denies `git commit --no-verify`, `git push --force`, `git reset --hard`
     on shared branches, and pushes to `main`.
   * PreToolUse denies agent edits to the process files: `CLAUDE.md`, `REVIEW.md`,
     `agents/`, `.claude/`, `.githooks/`, `scripts/guards.sh`, `scripts/hooks/` and `.github/`, unless the session
     was started for a `tooling` task (an environment flag set at spawn).
   * A context-% warning (section 9.3).
4. **CI (GitHub Actions)**, required checks on `main`:
   * `wrapper`: Gradle wrapper validation (the checksum of `gradle-wrapper.jar`)
   * `static`: spotless, detekt, Android Lint (warnings are errors, `MissingTranslation`
     and `ExtraTranslation` are errors, `HardcodedText` is an error, for XML only; Compose text is checked only by the
     JUnit rule `UiHardcodedStringRules` (`:core:domain:test`), for the call forms listed in its KDoc, and the
     rest is review). `targetSdk`
     follows `compileSdk`; if they differ, `OldTargetApi` is disabled with a
     `// justified:` comment rather than failing the build silently. Detekt: M0
     evaluates detekt 2.x, which supports Kotlin 2.4 and type resolution
     (`detektMain`/`detektTest`). If it isn't stable enough, M0 stays on 1.23
     without type resolution and records that gap in an ADR.
   * Danish and English plural strings use `<plurals>`, with a unit test per locale
     for 0, 1 and many.
   * `unit`: JVM tests + Kover verify + PIT on `core/domain`
   * `firebase`: Firebase emulator (project `demo-tally`, **no secrets needed**)
     → `tsc --noEmit` (strict), ESLint `strictTypeChecked` and Prettier over the TypeScript rules tests, then
     Jest rules tests
   * `ui`: Compose UI tests and the Kotlin data-layer integration tests (`connectedDebugAndroidTest` of `:app` and
     `:core:data` inside `firebase emulators:exec --only auth,firestore`; M1-02, #254) on an API 34 emulator against the Firebase emulator,
     with accessibility checks turned on (`enableAccessibilityChecks`: touch target
     size, contrast, content descriptions).
   * `screenshots` (`scripts/screenshots.sh verify`, M1-03): Roborazzi screenshot tests (JVM), exact-match goldens in
     light/dark × en/da plus one 200 % font-scale Danish light golden per screen; a failing run uploads the diffs as the
     `screenshot-diffs` artifact. Its own job because the artifact step needs `if: failure()`, which the required jobs
     that `scripts/test_ci_scope.py` guards may not have
   * `guards` (`scripts/guards.sh`) fails on:
     * `@Ignore`, `@Disabled`, `xit`, `.only`
     * `@Suppress`, `tools:ignore`, `ktlint-disable`, `detekt:` suppressions, or
       `lint.disable` / `.editorconfig` rule-offs, unless the line carries
       `// justified: <reason>` of at least 3 words of letters (the reviewer checks the content)
     * a raised line length, a lowered `coverageThreshold` / `fail_under`, a weaker ESLint preset, a dropped ruff `select` item or tsconfig
       `include` entry, a new tsconfig `exclude` entry, by comparing against `main`; linter or test config embedded
       in `package.json`. What is still not caught: `docs/guards-known-gaps.md`
     * a command-line flag that is not on the per-tool allowlist (ruff, mypy, tsc, ESLint, Prettier, shellcheck, actionlint; check 2c), unless the
       line carries a valid `justified:` reason; the lists and their reasons are in `scripts/guards.sh`, the rationale in `docs/guards-known-gaps.md`
     * any detekt or lint baseline file
     * a lowered `minBound`, PIT threshold or lint severity, by comparing against `main`
     * changed screenshot reference images, unless the PR has the `golden-update` label
     * a diff over 600 changed lines outside generated files
   * `release-smoke`: the release variant with R8 on builds in CI (`:app:assembleRelease`, unsigned, demo-tally stand-in config, nothing signed or uploaded; M1-33); the stand-in opt-in flag is allowed in this job only
   * `python-lint`: ruff and mypy on `scripts/`, versions pinned, with tests that deliberate violations fail
   * `workflow-lint`: shellcheck, actionlint and zizmor on `.github/` and `scripts/`, pinned binaries
   * `secrets`: gitleaks
   * `tasks`: `scripts/test_tasks.py` and `scripts/tasks.py validate` (the task graph in
     `docs/tasks.toml`); also run by `scripts/verify.sh`, including `--fast`
   * Unit tests run with network access blocked (a JUnit extension that fails if a
     socket opens), so tests can't silently depend on the internet.
5. **CODEOWNERS**: the owner is the designated reviewer for `.github/`, `scripts/`, `.claude/`,
   `agents/`, `CLAUDE.md`, `REVIEW.md`, `firebase/firestore.rules`, the process docs
   (`docs/ORCHESTRATION.md`, `docs/orchestrator-state.md`, `docs/tasks.toml`,
   `docs/FOLLOW-UPS.md`, listed explicitly because `docs/` has no directory rule), and screenshot
   reference images. CODEOWNERS marks these files and requests the owner's review; it is
   not an enforced approval (see item 6). Labels that agents could set themselves are not
   trusted on their own; the review is the reviewer rounds and the merge under the owner's authorization.
6. **Branch protection** on `main`: PR required, all 12 checks green (`wrapper`, `static`, `unit`, `firebase`, `ui`,
   `screenshots`, `release-smoke`, `guards`, `secrets`, `tasks`, `python-lint`, `workflow-lint`; source: GitHub Actions),
   **squash merge only**, no force-push, no deletion, branch up to date. **0 required
   approvals and Code Owners review off**: agents act as the owner's GitHub identity and
   GitHub does not let an author approve their own PR, so a required approval could never
   be met; the review is the reviewer rounds and the merge under the owner's authorization. **Empty bypass list**: a standing owner bypass
   would also bypass for agents. The owner adds themselves for an emergency merge only,
   then removes themselves. A separate machine account for agent PRs is a possible later
   improvement (it would allow 1 approval plus Code Owners review). You set this in GitHub
   settings (step-by-step guide: `docs/BRANCH-PROTECTION.md`).
7. **Dependency hygiene**: Gradle version catalog, Dependabot, Gradle wrapper validation.

## 6. Review loop

1. The author session opens a small PR (one concern, target under about 400 changed lines),
   using a PR template that covers scope, test evidence, and screenshots for UI changes.
2. A **fresh Claude session** (no shared context) reviews the diff against `REVIEW.md` as soon as the author has pushed,
   without waiting for CI (`docs/ORCHESTRATION.md` §7.1; CI must be green before the PR is marked READY and before the merge request):
   correctness, security rules, test adequacy (do the tests fail when the
   code is wrong?), offline/sync behavior, i18n, accessibility, free-tier cost, and
   every `// justified:` suppression.
3. Findings are posted as one PR comment containing a JSON block (format in
   `REVIEW.md`; `docs/ORCHESTRATION.md` §7.2 says how it is used): each finding has a stable ID (`R1-03`; rounds are
   numbered per PR and never reset per batch), a severity (`blocker | major | minor | nit`), a file and line,
   and a status (`open | fixed | disputed | withdrawn | deferred`). This makes the round-over-round
   metrics in section 9.4 possible.
4. The author (the same implementer session in every round) fixes everything above nit and every minor whose fix is about 30 changed lines or fewer,
   or marks it `disputed` with a reason, and pushes. Once no blocker or major is open, a larger or out-of-scope minor, and any nit,
   may be `deferred` to follow-up issues instead of another round.
5. Each later round runs in a **new** reviewer session that gets the whole PR diff, the findings JSON of earlier rounds and `REVIEW.md`,
   and focuses on the commits since the last round: it re-checks open findings, reviews the new code and how the fixes interact with the old code.
6. When only nits or deferred minors remain, the reviewer posts "ready (nits only)" and the orchestrator marks the PR READY. The merge agent squash-merges it, or an owner-only PR waits for the owner or the approver's record (`docs/ORCHESTRATION.md` §7.5).
   If round 4 of a batch still has open findings above nit (deferred minors do not count), one escalation reviewer per PR decides
   fix, split or owner (`REVIEW.md`, Loop and cap); its ruling is final; only a finding above nit still open after a `fix` ruling's round 5 reaches you.

## 7. Milestones (each one is one or more PRs, each reviewed)

| # | Scope | Done when |
|---|---|---|
| M0 | **Foundation**: agent setup (section 9: role prompts, `.claude/` settings, status line, handoff template, metrics script) + Gradle multi-module skeleton, version catalog, spotless/detekt/lint/Kover, `verify.sh`, hooks, CI workflows, Firebase emulator config + an empty rules test, REVIEW.md, CLAUDE.md, PR template, branch-protection guide | All CI jobs run green on a hello-world app plus a trivial test, and a test that's deliberately broken makes CI fail |
| M0.5 | **Product design** (no code): user stories with acceptance criteria (`docs/product/stories.md`), app-flow diagram (`docs/product/flow.md`, Mermaid), screen wireframes and design tokens (colors, type, spacing, dark mode) published as an artifact for review | You approve stories, flow and design (owner-only sign-off; the collaborator comments and reviews, `docs/COLLABORATING.md`). Each later milestone's acceptance tests are traced to story IDs |
| M1 | Accounts + households: Google and email + password sign-in (verification, reset, change password, optional TOTP), the non-Gmail collision message, create household, single-use invite link, join, leave, remove member, transfer ownership, delete account; rules requiring a verified email (`email_verified`, also to read an invite) + allow and deny tests; `LocaleConfig`; Crashlytics opt-in; App Check (monitoring); privacy text draft (OQ-30). The rules and sign-in PRs are `risk:high` (`area:security-rules` for rules). The list parts of leaving, removal, household deletion and account deletion wait for M2. Plan: the M1 milestone doc (task M1-01) | Two verified emulator users (one Google, one password) join one household; an unverified user and an outsider are denied (rules allow and deny tests) |
| M2 | Lists and items (v1): lists without a household, private by default, plain and collection types (`kind`), items with "I have it" and years, sorting per type, "show only missing", progress, "most recently used" kept on the device (OQ-35), duplicate-name hint (OQ-11), Undo snackbar (OQ-39), share and stop sharing, the creator and household-member access rules, real-time sync, offline banner, export of every list I can see to JSON or CSV (OQ-38), en/da; plus the list parts of HH-05, HH-06 and AUTH-04 (unsharing on leave, the `removed` marker unsharing, the creators' self-heal after deletion, anonymising the user's items on other people's lists and deleting the deleted account's lists, OQ-18) with their rules tests. The list rules, sharing and sync PRs are `risk:high` with `area:security-rules` or `area:sync-merge` | A UI test shows an edit on client A appearing on client B through the emulator; rules tests deny reading another user's private list and allow and deny each list part of HH-05, HH-06 and AUTH-04 |
| M3 | *After v1 (OQ-36, OQ-15, decided).* Packing domain: scaling, per-person templates and merging in `core/domain`, with property tests and PIT | Coverage and mutation floors met, and all invariants are property-tested |
| M4 | *After v1 (OQ-36, OQ-15, decided).* Packing UI + trips | End-to-end UI test from templates to a trip with the expected amounts |
| M5 | *After v1 (OQ-36, OQ-15, decided).* Barcode: CameraX + ML Kit scanning, UPCitemdb lookup | Scanner logic tested with an injected fake decoder, and lookup failure falls back to manual entry |
| M6 | Release: signed APK on tag → GitHub Release (owner-held GitHub key); App Check enforcement after the monitoring period; Play workflow prepared but off (Play account deferred) | Tag `v0.1.0` produces an installable signed APK |

**Before the first external tester** (anyone but the owner installs the app): the privacy text is approved
(OQ-30, names Google as processor, Auth in the US and Firestore in `eur3`, Crashlytics); Crashlytics opt-in is in;
App Check is enforced after its monitoring, and the rules cap items per list and invites per household (#204,
section 3.3); the web account-deletion page is decided and the in-app export (OQ-38, M2) is built;
the owner has the developer-verification account if it is required by then (issue #120).

**OQ-36 (decided 2026-11-17) and OQ-15 (decided 2026-11-18): packing, trips and barcodes come after v1, in M3 or
later, and are not part of M1 or M2.** M3, M4 and M5 keep their ids, so `docs/tasks.toml` needs no renumbering;
v1 is M1, M2 and M6; the owner's wording is "M3 or later". Their future (keep, reshape or drop) is decided when
post-v1 work is planned.

**Owner requirement (2026-11-18, #15 comment 6991020343, verbatim):** "After v1, we need to have infinite global
undo/redo internally for each list. This should include conflict handling, so an undo after a conflict shows the
other side of the conflict." It has no milestone yet. The orchestrator's reading of it (per-list history across all
members' changes; a conflict keeps the losing side; so v1 sync design should leave room) was to be confirmed and is
**not** an owner decision. Section 3.2 records the leave-room constraint (added by #162); M2 sync-merge planning
(`area:sync-merge`) takes the quoted requirement as its source and the owner confirms the reading.

## 8. What the owner needs to do (no code)

* Create a Firebase project (Spark plan) named after the app (Tally). Create the Firestore database in
  **`eur3`**: the location cannot be changed later. Enable Google and Email/Password sign-in, email
  enumeration protection, the password policy (Require, minimum 12). Add `google-services.json` as a
  GitHub secret (CI tests use the emulator and don't need it). Step-by-step list: the M1 plan (task M1-01).
* Check that the Identity Platform upgrade asks for no billing (OQ-25); if so, upgrade and enable TOTP
  with the Admin SDK or REST (M1 runbook). Translate the email templates to English and Danish.
* Register the SHA-1 and SHA-256 fingerprints of the debug key and of the GitHub release key in Firebase
  (Google sign-in) and App Check; `assetlinks.json` lists the SHA-256 of every release key (decision B): the
  GitHub key when it is made, the Play App Signing key when Play starts.
* Create the GitHub release keystore, keep it yourself (never committed), and add it to GitHub secrets (M6).
* Register App Check (Play Integrity, device integrity only) and a CI debug token; turn enforcement on
  after about two weeks of metrics, before the first external tester (#204).
* If one account uses up the daily quota: disable it in Authentication and remove its data as section 3.3 says,
  never deleting a `households/{hid}` doc by hand (#199).
* Register a limited-distribution developer account when it is available in Denmark (issue #120).
* Approve the privacy text (OQ-30) before anyone else installs the app.
* Done (#260 item 4): the repository is public (M0-O3), the CODEOWNERS handle is confirmed (M0-O4), branch protection
  is on (M0-O6), and the collaborator setup with labels, 2FA and the live test is finished (M0.5-O3..O5).
* Deferred decisions (2026-11-17): the web account-deletion page (before the first external tester) and the Play
  account type and the 12-tester closed test (when Play release is planned). The palette (T1) was decided later the
  same day: Petrol (issue #15 comment 6956773225). The undo snackbar timing (OQ-39) and backups/export (OQ-38) were
  decided on 2026-11-18 (section 3.2 and 3.3).

## 9. Agents, models and effort levels

### 9.1 Roles

| Role | Model / effort | Runs as | Gets | Produces |
|---|---|---|---|---|
| **Orchestrator** | Opus / medium | One long-lived session | `PLAN.md`, `docs/ORCHESTRATION.md`, the state issue, `WORKER-RESULT` blocks | Spawns sessions, updates the state issue, asks the owner for decisions and for batch approvals of owner-only merges (autonomy rules: `docs/ORCHESTRATION.md` §1.1); never commits |
| **Planner** | Opus / high | Fresh session, once per milestone | `PLAN.md`, the milestone, the relevant code | `docs/milestones/Mx.md`: PR breakdown, acceptance tests per PR; the PR-sized tasks with dependencies in `docs/tasks.toml` |
| **Implementer (Opus)** | Opus / high (max for `risk:high`) | Fresh session per PR, kept across its review rounds | Its PR's section of `Mx.md`, `CLAUDE.md` | Branch + PR; tests written first; `verify.sh` green. For the cases in the split below |
| **Implementer (Sonnet)** | Sonnet / medium (high for tooling) | Same | Same | Same. For every other task |
| **Reviewer** | Opus / high (max for `risk:high`, `area:security-rules` and `area:sync-merge`) | Fresh session per review round | Diff, PR description, `REVIEW.md`, previous findings | Findings labeled `blocker / major / minor / nit`, with the file and line; never edits or pushes to the PR branch (`docs/ORCHESTRATION.md` §7.2) |
| **Re-check reviewer** | Sonnet / medium | Fresh session for the re-check of a small fix-only or docs-only commit (the delta review) | The inputs of any delta review (whole PR diff, description, previous findings, `REVIEW.md`) | The same findings block, focused on the fixed findings (`docs/ORCHESTRATION.md` §7.2.3) |
| **Second reviewer** | Opus / high | Fresh session in the same round, for `risk:high` and the protected areas | Diff, PR description, `REVIEW.md`; not the first reviewer's findings | Findings (`S<round>-<nn>`), merged with the reviewer's |
| **Escalation reviewer** | Opus / max | Fresh session, once per PR after round 4 or on a dispute | The whole review thread | `fix`, `split` or `owner` (`REVIEW.md`, Loop and cap) |
| **Design reviewer** | Opus / high | Fresh session per design-PR round, max 3 rounds | Design PR, review sheet, `design/tokens.json`, wireframes, rubric (`docs/reviews/README.md` §4) | Rubric scores and findings (`D<round>-<nn>`); one joint hand-off comment to the owner and the collaborator; never edits or pushes to the PR branch |
| **Merge agent** | Sonnet / medium | Long-lived session started by the orchestrator, under an owner authorization on #15 | The READY PR list; `scripts/merge_ready.py`, `scripts/update-branch.sh` | Squash merges of READY PRs that are not owner-only (in the order the orchestrator names), and of owner-only PRs once the owner's approval is recorded on #15 (in the owner's batch order; 7007421567 D1, D3); settings outside git stay the owner's (`docs/ORCHESTRATION.md` §7.5) |
| **Explorer** (subagent) | Sonnet / medium | Subagent inside an implementer or reviewer | A narrow question | File paths and short excerpts, no dumps |
| **CI triage** (subagent) | Sonnet / medium | Subagent inside an implementer | Failing job log | The failing test or rule and the minimal error |

Implementer split (owner decision, #15 comment 7032210967): the Opus implementer takes spikes, design or architecture tasks, `risk:high` tasks,
Firestore security rules, sync and merge logic, guard, hook and command-parsing tooling, and a new implementer for a PR that already had 3 or more
review rounds. The Sonnet implementer takes everything else: docs, strings, UI from an approved design, small fixes, dependency bumps, mechanical
refactors and ordinary features with a clear spec. Running sessions keep their model. Reviewers stay fresh Opus. The lists are `agents/roles.yaml` (`use_when`).

Escalation rules (written down so agents don't decide on their own):
* Model and effort come from `agents/roles.yaml`. An agent that needs more asks in its `WORKER-RESULT`, and the orchestrator decides within that file.
  An implementer that fails `verify.sh` 3 times on the same error runs a CI-triage pass first, then, if it does not explain the failure, stops and reports.
* Security rules, sync and merge logic, and the release workflow are tagged `risk:high`
  in `Mx.md`. Their implementers and reviewers run at max effort, and a second reviewer covers the same round.
  A PR that changes `firestore.rules` or its rules tests also carries the label `area:security-rules`, and one that
  changes sync, conflict or merge behaviour carries `area:sync-merge` (the reviewer then checks the rules allow/deny
  matrix, `REVIEW.md` item 13). The M1 plan adds the auth flows that decide who is signed in (password, verification,
  reset, same email), account deletion and the household batches to `risk:high`, in PRs split by concern.
* De-escalation (lower effort or a cheaper model for a role) happens only through the
  metrics retro (section 9.4) or an owner decision, never ad hoc.

Role definitions are checked in, so they get reviewed and versioned like code:
* `.claude/agents/explorer.md` and `.claude/agents/ci-triage.md`: subagent definitions,
  with model and effort in their frontmatter.
* `agents/prompts/{orchestrator,planner,implementer,reviewer,design-reviewer}.md`, plus `second-reviewer.md`, `escalation-reviewer.md` and `verifier.md`: opening prompts for the sessions.
* `agents/roles.yaml`: the single source of truth for each role's model and effort.

### 9.2 Working rules (in CLAUDE.md)

* Read what you need to understand the change, and read whole files you edit. Broad searches may go to the Explorer.
* Never paste full CI logs. Use CI triage, or the `verify.sh` summary, which prints only failures.
* `verify.sh` has quiet output by default (one line per step, plus failure details).
* One PR = one concern, about 400 lines or fewer. Smaller diffs mean cheaper reviews.
* Reviewers run whatever proves a finding: any test, the app's JVM screenshots or a script. CI runs the full suite.
* The orchestrator reads results cheapest first and never whole transcripts; targeted `list_events` on a stall, a block, red CI or before an escalation decision
  (the `WORKER-RESULT` block first, `docs/ORCHESTRATION.md` §7.3); tokens and cost come from
  `get_session`, not from the worker.

### 9.3 Context limits and handoff

* **One implementer session per PR, kept across its review rounds; a fresh reviewer session per round.**
* A status line shows the context % in every session.
* At the **step boundary** (60% of a 1M window, 40% of a 200k one; hard stage 80% / 60%), the session finishes its current step, writes
  `handoff/<branch>.md` from a template, commits it, and ends.
  The template covers: goal, what's done, what's next, decisions made, open
  findings, and commands to resume. The orchestrator starts a fresh session with
  that file as input. `/compact` is only a fallback, e.g. in the middle of a step
  that can't be split.
* Handoff files are deleted in the PR's final commit. Because merges are squash-only, they never reach `main`'s history.
* The orchestrator follows the same rule, but it never commits: its state lives in the state issue
  and it hands over with the checklist in `docs/ORCHESTRATION.md` §5.
* The threshold warning comes from tooling, not memory: a status-line script plus a
  hook that injects a reminder once at each threshold (`scripts/hooks/context_guard.py`).

### 9.4 Performance reviews

Each metric must have a data source proven in M0; a metric whose source can't be
proven is dropped, not guessed. The sources are the orchestrator's CSV comments on the state issue
(`docs/ORCHESTRATION.md` §6), filled from `get_session` → `external_metadata.usage` (cost and tokens per
session; confirmed to work on 2026-11-10) and from the reviewer's findings. The SessionEnd hook writes to the
gitignored `metrics/sessions/` inside ephemeral containers, so it is not a source for cloud sessions (it stays
for local runs).

`scripts/agent_metrics.py` parses those comments, saved under `docs/metrics/`, with no network access, and
writes `docs/agent-metrics.csv` (a row per session, review round and incident):

| Metric | Why |
|---|---|
| Tokens (in/out/cache) per role per PR | Cost |
| Number of sessions and handoffs per PR | How well the context limit works |
| `verify.sh` failures before the first push, and CI red runs | Implementer quality |
| Review rounds; findings by severity | Implementer quality, and whether the reviewer is useful |
| Escaped defects: bugs found after merge, traced back to a PR (a `Caused by: #N` line in the bug issue and one row in the metrics CSV; no per-PR labels) | Reviewer quality, the most important signal |
| Reviewer false positives: findings marked `disputed` and then `withdrawn` (from the JSON findings) | Reviewer precision |

At the **end of each milestone**, a retro session (Opus / high) reads the CSV, `docs/agent-tuning.md` and a sample of transcripts and PR threads. It proposes at most 3 changes, e.g. "drop the implementer to
low effort for UI-only PRs", "tighten REVIEW.md section X". Each change comes as a
reviewed PR to `agents/roles.yaml` or the prompts, with the expected effect logged.
The next retro checks whether that effect happened, and reverts the change if not.

Guardrail: quality metrics take precedence over cost. A change that cuts tokens but
raises escaped defects or blockers per PR gets reverted.

Spend is reported per PR class and milestone; there are no per-session limits on tokens (`agents/roles.yaml`).
