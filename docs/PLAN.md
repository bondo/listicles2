# Tally (repo: listicles2) – Implementation Plan

Status: working draft (sections 1, 2, 3, 4, 7 and 8 updated for the decided v1 scope, task OQ-15, 2026-11-17); not owner-approved (see issue #15).

Android app for shared household lists. In v1 every list is private to its creator until the creator shares it
with their household; lists are *plain* or *collection* lists (`docs/product/stories.md`). Changes sync in real
time between members. Packing lists, trips and barcodes are parked until after v1 (section 7, OQ-36, decided 2026-11-17).

## 1. Decisions

| Area | Decision |
|---|---|
| Client | Kotlin + Jetpack Compose, single Activity, MVVM + unidirectional state, Hilt DI |
| Backend | Firebase (Spark/free): Auth + Cloud Firestore. **No Cloud Functions** (they need the paid Blaze plan), so all integrity checks live in security rules |
| Sign-in | Google via Credential Manager (the legacy Google Sign-In API is deprecated[^gsi]) **and** email + password with mandatory email verification, both in v1 (OQ-23). Optional TOTP two-step verification for password accounts (OQ-24), only if the Identity Platform upgrade needs no billing (OQ-25). No email-link sign-in (OQ-27). Details: section 3.4 |
| Data location | Firestore database in **`eur3`** (EU multi-region, Belgium and the Netherlands; cannot be changed after creation[^loc]). Firebase Authentication processes data only in the US[^authus]. The privacy text (OQ-30) names both |
| Sync | Firestore snapshot listeners; offline cache on; one document per item; updates write only the changed fields; same-field conflicts resolve last write wins |
| Lists | Private to their creator by default (Q3, VIS-01); the creator may share a list with their household (VIS-02) and stop sharing it (VIS-04). A household is needed only to share (OQ-1). Type `kind` is `PLAIN` or `COLLECTION`, chosen at creation and fixed (OQ-32) |
| Items (v1) | Name + "I have it"; collection lists add an optional release year and re-release year (1900 to the current year + 50, OQ-6, OQ-19). Sorted per type (OQ-8, OQ-33), "show only missing" filter, progress "12 of 30" (OQ-9). No notes, tags, quantity, barcode or search in v1 (stories section 8) |
| Sharing | Households: one per user; members join through a **single-use invite link** (random code of 16+ characters, expires after 7 days, can be revoked). Household, invite and sharing actions need a connection (OQ-22) |
| After v1 (parked) | Packing templates, scaling, merging and trips (section 4); barcode scanning (ML Kit + CameraX) and title lookup (UPCitemdb). Not in the v1 scope; parked by owner decision OQ-36 (2026-11-17, section 7) |
| i18n | English + Danish; all strings in resources; CI fails on missing translations. Android 13+: the system per-app language setting, made visible by an auto-generated `LocaleConfig`[^lang]; Android 8-12 follow the phone language; no in-app picker, `minSdk` stays 26 (OQ-12, decided 2026-11-17) |
| Crash reporting | Firebase Crashlytics **off by default**, turned on by an opt-in setting ("Send crash reports")[^crash]; **no Google Analytics**; declared in the privacy text and Play Data safety; in place before the first external tester (decided 2026-11-17) |
| App Check | Play Integrity provider requiring **device integrity only**, not Play recognition or licensing (the default requires `PLAY_RECOGNIZED`, which a GitHub APK cannot meet[^pi]); debug provider in CI and the emulator; about two weeks of metrics before enforcing; set up before the first external tester (decided 2026-11-17) |
| AI at runtime | No AI code and no LLM or cloud AI calls (on-device ML Kit only if barcode scanning returns after v1) |
| Distribution | Signed APK on GitHub Releases on each `v*` tag, signed with an owner-held GitHub key (never committed). Play later, with its own Play App Signing key: **separate keys**, so moving from the GitHub APK to the Play build needs an uninstall (cloud data is kept; decided 2026-11-17). Play account type and the closed test are deferred until Play release is planned. Android developer verification: a free limited-distribution account when available in Denmark (owner task, issue #120) |
| Review | Every change is a PR → CI gates → a separate Claude session with no authoring context reviews it against `REVIEW.md` → fix and re-review until only nits or deferred minors remain (max 4 rounds per batch, then the owner decides) → the owner squash-merges |
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
/firebase             firestore.rules, firestore.indexes.json, firebase.json, rules tests (Jest)
/docs                 PLAN.md, ORCHESTRATION.md, ARCHITECTURE.md, ADRs
/scripts              verify.sh and guard scripts used by CI and git hooks
REVIEW.md             Review rubric and severity definitions
CLAUDE.md             Agent instructions: the only commands to run, and the rules
```

`core/domain` has **no Android or Firebase dependencies**, so most logic gets fast JVM tests.

## 3. Data model (Firestore)

```
users/{uid}                      { householdId? }                      // only readable by the user
households/{hid}                 { name, createdBy, createdAt, ownerUid, deleted: bool }
households/{hid}/members/{uid}   { role: owner|member, displayName, joinedAt, viaInvite? }
households/{hid}/removed/{uid}   { removedAt }                         // owner only: unsharing still to do
invites/{code}                   { householdId, createdBy, createdAt, expiresAt }
lists/{lid}                      { kind: PLAIN|COLLECTION, name, createdBy, sharedWith: hid|null,
                                   schemaVersion, createdAt, updatedAt, updatedBy }
lists/{lid}/items/{iid}          { name, have: bool, releaseYear?, reReleaseYear?,   // years: COLLECTION only
                                   createdBy, createdAt, updatedAt, updatedBy }
config/app                       { minVersionCode }                    // anyone reads, even signed out; owner edits in the console
```

Lists are **top level**, not under a household: a list exists without a household (OQ-1), and it stays with its
creator when they leave, are removed or the household is deleted (OQ-5, OQ-17), so only `sharedWith` changes and no
data moves. LIST-01 runs two queries: `createdBy == uid` and `sharedWith == myHousehold`. A member who joins later
sees the lists already shared (the second query; this matches the OQ-16 assumption). `createdBy` on items keeps room
for OQ-18 (M2 planning). `schemaVersion` and the `minVersionCode` field of the app config document let a newer app ask older installs to
update ("Update the app" screen): GitHub APKs cannot be force-updated. Where "most recently used" (OQ-35) and the
overview progress counts (OQ-9) are stored is decided in M2 planning (section 3.3).

### 3.1 Security rules (no Cloud Functions, so everything is enforced here)

Every rule below gets at least one allow test and one deny test in the emulator.
Notation: `get`/`exists` see the state **before** a batch, `getAfter`/`existsAfter`
see it **after**. `M(x)` means `exists(/households/$(hid)/members/$(x))`. `O(x)` means
`get(/households/$(hid)).data.ownerUid == x`. `LIVE` means
`get(/households/$(hid)).data.deleted == false`. Every household, member, invite and shared-list rule below
requires `LIVE` **except** Create household (no doc exists yet), Cleanup (only when `deleted == true`) and the
tombstone read (below). Rules that involve no household need no `LIVE`: `users/{uid}`, the `config` app document, Create
list, and the creator's own access to their lists and items.

**Signed in** means `request.auth != null && request.auth.token.email_verified == true`[^ev]. Every rule below,
including the invite `get`, requires it, with two exceptions: the own `users/{uid}` doc needs only
`request.auth != null` (AUTH-06, HH-03), and the `config` app document is readable by anyone, even signed out (so an
old app can say "Update the app" before sign-in or verification). The `config` app document has no client writes. No rule relies on a two-step (MFA) claim.

**Reads**: members (`M(uid)`, `LIVE`) can read the household doc and everything under it.
`users/{uid}` can be read and written only by that user, and holds nothing but
`householdId`, which enforces one household per user (HH-01, HH-03):
* set (`null` → `hid`) only together with `existsAfter(/households/hid/members/uid)` (the create-household
  and join batches); a direct change from one household to another is denied;
* cleared (`hid` → `null`) only when `!existsAfter(/households/hid/members/uid)` (in the Leave batch, or after
  a removal) or the household is deleted. The owner never writes another user's doc: a removed member's or a
  deleted household's former member's app sees the stale value at start and clears it itself (self-heal).
* Tests: allow set in create and join, clear in the Leave batch, clear after removal, clear after deletion;
  deny set without membership, `hid1` → `hid2`, clear while still a member of a live household, any write to
  another user's doc. A user may also `get` their own `members/{uid}` path in any household (it may not
  exist) and the household doc while it is a tombstone and their `householdId` points at it: that is the
  signal for the HH-06 "household deleted" dialog and for the self-heal.
A list is readable by its creator (`createdBy == uid`) always, and by others only when
`sharedWith != null && M(sharedWith) && LIVE(sharedWith)`. Items follow their list (`get` of the parent list).

[^ev]: https://firebase.google.com/docs/reference/rules/rules.firestore.Request#auth

**Writes**, path by path:

| Path / action | Allowed when |
|---|---|
| Create household + owner (one batch) | Household: `!exists(household)`, `createdBy == ownerUid == uid`, `deleted == false`, **and** `existsAfter(members/uid)`. Member doc: `!exists(household)` **and** `getAfter(household).ownerUid == uid` **and** `role == owner` **and** the one-household check (below). Household docs are never deleted (see Delete household), so `!exists` can never be true again for an id that has existed. A former creator can't become owner again, and nobody can reclaim leftover data. |
| Create invite `invites/{code}` | `M(uid)` of `householdId`; `createdBy == uid`; `createdAt == request.time`; `expiresAt <= request.time + duration.value(7, 'd')`; `code.size() >= 16`. No updates. |
| Read one invite (`get`) | Any signed-in user with a verified email (they need the code). |
| Query invites (`list`) | Only queries filtered on `householdId == hid` where `M(uid)`, so members can see and revoke their household's invites. Nobody can enumerate other codes. |
| Delete invite | Its creator or the owner (revoke); **any member** once `expiresAt < request.time` (cleanup); the joiner in the join batch (below). |
| Join (one batch) | Create `members/{uid}` with `role == member`, `joinedAt == request.time`, `viaInvite == code`, where: `!M(uid)` before the batch; the invite exists, points at `hid` and hasn't expired; the invite's creator is **still a member** (`M(invite.createdBy)`); **and** `!existsAfter(invites/{code})`, so the join is only valid if the same batch deletes the invite. That delete is allowed only if `!M(uid) && getAfter(member).viaInvite == code`, so an existing member can't burn someone else's invite. Single use follows from the delete. The member create also needs the one-household check. |
| One-household check (member create in Create household and Join) | `get(/users/uid)` has no `householdId` (or does not exist) **and** `getAfter(/users/uid).data.householdId == hid`, so the same batch must write the users doc. A stale value (after removal or deletion) must be self-healed first. Deny tests: join or create without the users-doc write; while `householdId` points at another household. The extra `get`/`getAfter` count in spike (e). |
| Update own member doc | Only `displayName` may change. |
| Leave | A member who is not the owner (`!O(uid)`) deletes their own member doc. The client also deletes that member's invites (allowed: the creator may delete their own invites) and sets `sharedWith = null` on the lists they created (allowed: creator), so those lists go with them (OQ-5). |
| Remove member | `O(uid)`, and the target isn't the owner before **or after** the batch (`target != getAfter(household).data.ownerUid`), so a batch can't hand ownership to someone and remove them at the same time. The same batch deletes the removed member's open invites and creates a marker `households/{hid}/removed/{uid}` (create: only `O(uid)`, only when `M(target)` before and `!existsAfter(members/target)`; read and delete: only the owner; deny tests for a non-owner create and a create while the target stays a member). The owner's client then sets `sharedWith = null` on the removed member's lists shared with this household, in pages (query `sharedWith == hid && createdBy == target`; allowed to the owner only when `!existsAfter(members/createdBy)`; OQ-5), and deletes the marker last; an unfinished marker is resumed at the owner's next app start. If an unshare is denied because the person is a member again (rejoined through another invite) or the household was deleted meanwhile, the client deletes the marker instead of retrying; cleanup deletes any markers left. The removed member's own app also unshares them at its next start (creator path). Until one of them finishes, the remaining members can still read those lists, which they could already read; the removed member loses access to everyone else's lists at once. A list query on `sharedWith` cannot also check that the creator is a member, because rules are not filters: the condition would depend on each document's `createdBy`. Even if that cleanup is skipped, the `M(invite.createdBy)` check makes those invites unusable while the person is not a member. Accepted residual risk: if they rejoin through someone else's link, any of their old invites that haven't expired (7 days at most) start working again. |
| Transfer ownership (one batch) | Updates `household.ownerUid` and the `role` of both member docs. Household update: `O(uid)`, only `ownerUid` changes, and the new owner is a member both before and after the batch (`M(new)` and `existsAfter(members/new)`). Each member-doc update: only `role` changes, `O(uid)` before the batch, and the new role equals `getAfter(household).ownerUid == thisDoc ? owner : member`. `ownerUid` is the single source of truth, so there is always exactly one owner. `role` is a cached copy for display, and rules use `O(x)`. |
| Create list | `createdBy == uid`, `sharedWith == null`, `kind` in `PLAIN`, `COLLECTION`, plus field validation (below). |
| Update list | The creator, or a member of `sharedWith` while `LIVE` (OQ-3). `kind`, `createdBy` and `createdAt` never change. `sharedWith` changes only: by the creator, `null` → their own household (`M(uid)`, `LIVE`) or back to `null` (VIS-02, VIS-04, and the self-heal after leaving, removal or deletion); by the owner in Remove member (above), to `null` only. |
| Items: create, update | Same people as Update list. On create `createdBy == uid` and `createdAt <= request.time` (OQ-37, decided: Undo keeps the original value); on update `createdBy` and `createdAt` never change. Years only in `COLLECTION` lists. Deny tests: changing `createdBy` or `createdAt` on update, a future `createdAt`, years in a `PLAIN` list. |
| Delete list, items | Same people as Update list; the client deletes the items first, in pages, then the list. |
| Delete household | `O(uid)`. **Soft delete**: first one update sets `deleted: true`. This update may change only `deleted` (false → true) and `name` (→ empty); `ownerUid`, `createdBy` and `createdAt` stay as they are. From that moment `LIVE` is false, so every read and write under the household is denied to everyone except the owner's cleanup. Then the client deletes invites → `removed` markers → members in pages. Lists shared with the household go back to their creators (OQ-17) without any owner write: from the moment `LIVE` is false only creators pass the list read rule. Each creator's app sees the tombstone at its next start (the tombstone read above), shows the HH-06 dialog, clears `sharedWith` on its own lists and its `householdId`. This follows the stories planner note (`docs/product/stories.md` section 11): creators, not the owner, make their lists private again. **Cleanup rule**: while `deleted == true`, the owner (`O(uid)`) may read, list (including the invites query on `householdId`) and delete everything under the household; nobody else may do anything. The household doc itself stays as a tombstone (`{ createdBy, createdAt, ownerUid, deleted: true, name: "" }`; field validation accepts the empty name only on tombstones), so its id can never be reused. A crash mid-cleanup leaves data no one can access, and the next app start resumes the cleanup. |

Rules can't count members, so "the owner can't leave while others remain" is
enforced by the rule shapes above: the owner can't use Leave, so they must transfer
ownership or delete the household.

**Spike first (M1, PR 1)**: prove in the emulator that (a) the invite `list` rule,
filtered on `householdId` with a membership `exists()`, is accepted, (b) the join
batch with `existsAfter`/`getAfter` works, (c) the transfer batch works, (d) the list query
`sharedWith == hid` with `M(hid)` and `LIVE` is accepted, and (e) every batch stays within the
rules limits of 10 `get`/`exists` calls per single-document request or query and 20 per batch[^calls]
(Remove member and cleanup batches are paged to fit). If (a)
fails, the fallback is to nest invites under the household, with a top-level
`inviteCodes/{code} → hid` index used only for `get`.

[^calls]: https://firebase.google.com/docs/firestore/security/rules-conditions#access_call_limits

**Field validation** on every write:
* types, string lengths and allowed enum values;
* years: whole numbers from 1900 to `request.time.year() + 50`, both optional, no rule between them (OQ-6, OQ-19);
* `updatedBy == request.auth.uid` and `updatedAt == request.time`;
* `createdAt` and `createdBy` can't change on update; on create `createdBy == request.auth.uid` and
  `createdAt == request.time`, except items, where `createdAt <= request.time` (OQ-37, decided 2026-11-17).

**Account deletion** (required by Google Play): in-app "Delete my account" (AUTH-04). A member
leaves; an owner with other members must transfer ownership first, and the UI
guides them; a last member deletes the household. Then the app deletes the lists the user created
(items first), `users/{uid}` and the Auth user. Deletion needs a recent sign-in[^reauth]
(`FirebaseAuthRecentLoginRequiredException`): the app asks for Google, or the password plus a TOTP code when
two-step verification is on, before it starts, so nothing is left half-done. What happens to items the user added
to other people's lists is OQ-18 (M2 planning).
Play also requires a **web** way to request deletion, besides the in-app path[^playdel]. The owner deferred
this decision (2026-11-17): it must be settled before the first external tester and must exist before a Play
release. Options on file: a static page with a mailto link on the owner's domain next to the invite page
(recommended), GitHub Pages, or a Google Form.

[^reauth]: https://firebase.google.com/docs/auth/android/manage-users#re-authenticate_a_user
[^playdel]: https://support.google.com/googleplay/android-developer/answer/13327111 (cited by the 2026-11-17 best-practices investigation, issue #15)

**Expired invites**: a member's app queries its household's invites when the household
screen opens and deletes the expired ones. TTL policies are not relied on.

**App Check** (Play Integrity, free) as decided in section 1: device integrity only, debug provider
in CI and the emulator[^acdebug], metrics watched for about two weeks before enforcing[^acmon]; set up
before the first external tester. It is extra protection against scripted abuse, also of sign-up (email
enumeration protection still returns `EMAIL_EXISTS` on sign-up[^enum]).

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
  written at once, so other members see it at once.
* **OQ-37 (decided 2026-11-17, C5 of the investigation):** Undo keeps the original `createdAt`, so the item
  keeps its place in the "oldest added first" tie-break (ITEM-05). Rules cannot tell an Undo from any other
  create, so every item create accepts any `createdAt` not later than `request.time` (a forged older value
  only changes a tie-break order). `createdBy` is the caller, so an Undo by another member records them as the
  adder (acceptable while OQ-18 is open; revisit then).
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
  (enforced by the UI and documented).
* Estimate (redone for C4): 10 users, each opening a 300-item list 10 times a day, more than 30 minutes
  apart, is about 30k item reads, plus about 10 reads per overview open (two queries and rules reads)
  at 10 overview opens per user a day, 1k reads: about 31k reads a day, under the 50k limit but not with a large margin. The data-layer PR for M2 must
  include a read-cost estimate per screen, with re-reads and rules reads, and an emulator test that counts
  reads where the emulator can.
* GitHub Actions: the repo is public, so minutes are unlimited.
* No backups on Spark (scheduled backups and point-in-time recovery need Blaze[^backup]), and any member can
  delete a shared list: the backup/export choice was deferred to M1 planning (OQ-38, asked in the M1 plan, task M1-01).

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

**Parked until after v1 (OQ-36).** The packing design below is kept for later; v1 domain code is
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
   and pre-push runs the guards, the hook tests and the unit tests (it skips the Gradle unit tests for pushes that only touch
   docs, scripts, hooks, CI, agents or firebase files; unknown paths still build).
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
     → `tsc --noEmit` (strict), ESLint `strictTypeChecked` and Prettier over the TypeScript rules tests, then
     Jest rules tests + Kotlin data-layer integration tests
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
   trusted on their own; the owner's merge is the review.
6. **Branch protection** on `main`: PR required, all 8 checks green (`wrapper`, `static`, `unit`, `firebase`, `ui`,
   `guards`, `secrets`, `tasks`; source: GitHub Actions),
   **squash merge only**, no force-push, no deletion, branch up to date. **0 required
   approvals and Code Owners review off**: agents act as the owner's GitHub identity and
   GitHub does not let an author approve their own PR, so a required approval could never
   be met; the owner's merge is the review. **Empty bypass list**: a standing owner bypass
   would also bypass for agents. The owner adds themselves for an emergency merge only,
   then removes themselves. A separate machine account for agent PRs is a possible later
   improvement (it would allow 1 approval plus Code Owners review). You set this in GitHub
   settings (step-by-step guide: `docs/BRANCH-PROTECTION.md`).
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
   and a status (`open | fixed | disputed | withdrawn | deferred`). This makes the round-over-round
   metrics in section 9.4 possible.
4. The author fixes everything above nit, or marks it `disputed` with a reason, and pushes. Once no blocker or major is
   open, minor and nit findings may be `deferred` to follow-up issues instead of another round.
5. Each later round runs in a **new** reviewer session that sees only the commits since the
   last round, the open findings, and `REVIEW.md`. It re-checks open findings and reviews
   the new code. It doesn't re-review unchanged code, so the loop converges.
6. When only nits or deferred minors remain, the reviewer posts "ready (nits only)" and you squash-merge.
   If round 4 of a batch still has open findings above nit (deferred minors do not count), the loop stops and you decide.

## 7. Milestones (each one is one or more PRs, each reviewed)

| # | Scope | Done when |
|---|---|---|
| M0 | **Foundation**: agent setup (section 9: role prompts, `.claude/` settings, status line, handoff template, metrics script) + Gradle multi-module skeleton, version catalog, spotless/detekt/lint/Kover, `verify.sh`, hooks, CI workflows, Firebase emulator config + an empty rules test, REVIEW.md, CLAUDE.md, PR template, branch-protection guide | All CI jobs run green on a hello-world app plus a trivial test, and a test that's deliberately broken makes CI fail |
| M0.5 | **Product design** (no code): user stories with acceptance criteria (`docs/product/stories.md`), app-flow diagram (`docs/product/flow.md`, Mermaid), screen wireframes and design tokens (colors, type, spacing, dark mode) published as an artifact for review | You approve stories, flow and design (owner-only sign-off; the collaborator comments and reviews, `docs/COLLABORATING.md`). Each later milestone's acceptance tests are traced to story IDs |
| M1 | Accounts + households: Google and email + password sign-in (verification, reset, change password, optional TOTP), the non-Gmail collision message, create household, single-use invite link, join, leave, remove member, transfer ownership, delete account; rules requiring a verified email + tests; `LocaleConfig`; Crashlytics opt-in; App Check (monitoring); privacy text draft (OQ-30). The list parts of leaving, removal, household deletion and account deletion wait for M2. Plan: the M1 milestone doc (task M1-01) | Two verified emulator users (one Google, one password) join one household; an unverified user and an outsider are denied (rules allow and deny tests) |
| M2 | Lists and items (v1): private lists, plain and collection types, items with "I have it" and years, sorting per type, "show only missing", progress, share and stop sharing, real-time sync, offline banner, en/da; plus the list parts of HH-05, HH-06 and AUTH-04 (unsharing on leave, the `removed` marker unsharing, the creators' self-heal after deletion, deleting a deleted account's lists) with their rules tests | A UI test shows an edit on client A appearing on client B through the emulator; rules tests deny reading another user's private list and allow and deny each list part of HH-05, HH-06 and AUTH-04 |
| M3 | *Parked after v1 (OQ-36, decided).* Packing domain: scaling, per-person templates and merging in `core/domain`, with property tests and PIT | Coverage and mutation floors met, and all invariants are property-tested |
| M4 | *Parked after v1 (OQ-36, decided).* Packing UI + trips | End-to-end UI test from templates to a trip with the expected amounts |
| M5 | *Parked after v1 (OQ-36, decided).* Barcode: CameraX + ML Kit scanning, UPCitemdb lookup | Scanner logic tested with an injected fake decoder, and lookup failure falls back to manual entry |
| M6 | Release: signed APK on tag → GitHub Release (owner-held GitHub key); App Check enforcement after the monitoring period; Play workflow prepared but off (Play account deferred) | Tag `v0.1.0` produces an installable signed APK |

**Before the first external tester** (anyone but the owner installs the app): the privacy text is approved
(OQ-30, names Google as processor, Auth in the US and Firestore in `eur3`, Crashlytics); Crashlytics opt-in and
App Check monitoring are in; the web account-deletion page and the backup/export choice (OQ-38) are decided;
the owner has the developer-verification account if it is required by then (issue #120).

**OQ-36 (decided 2026-11-17): packing, trips and barcodes are parked until after v1.** M3, M4 and M5 keep
their ids, so `docs/tasks.toml` needs no renumbering; v1 is M1, M2 and M6. Their future (keep, reshape or
drop) is decided when post-v1 work is planned.

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
  after about two weeks of metrics.
* Register a limited-distribution developer account when it is available in Denmark (issue #120).
* Approve the privacy text (OQ-30) before anyone else installs the app.
* Make the repository public (decided: unlimited free Actions minutes).
* Add yourself as CODEOWNER (the M0 PR adds the file; you confirm the handle).
* Turn on branch protection using the guide from M0.
* Collaborator: check the Actions settings, invite them, ask for 2FA, create the labels `feedback`, `idea`, `decision`, `needs-collaborator`, `needs-owner`, send them `docs/COLLABORATING.md`, run the live test (tasks M0.5-O3, M0.5-O4).
* Deferred decisions (2026-11-17): the web account-deletion page (before the first external tester), the Play
  account type and the 12-tester closed test (when Play release is planned), the palette (T1), the undo
  snackbar timing and backups/export (M1 planning).

## 9. Agents, effort levels and token budget

### 9.1 Roles

| Role | Model / effort | Runs as | Gets | Produces |
|---|---|---|---|---|
| **Orchestrator** | Sonnet / low | One long-lived session | `PLAN.md`, `docs/ORCHESTRATION.md`, the state issue, `WORKER-RESULT` blocks | Spawns sessions, updates the state issue, asks the owner for merges and decisions (autonomy rules: `docs/ORCHESTRATION.md` §1.1); never commits |
| **Planner** | Opus / high | Fresh session, once per milestone | `PLAN.md`, the milestone, the relevant code | `docs/milestones/Mx.md`: PR breakdown, acceptance tests per PR; the PR-sized tasks with dependencies in `docs/tasks.toml` |
| **Implementer** | Sonnet / medium | Fresh session per PR | Its PR's section of `Mx.md`, `CLAUDE.md` | Branch + PR; tests written first; `verify.sh` green |
| **Reviewer** | Opus / high | Fresh session per review round | Diff, PR description, `REVIEW.md`, previous findings | Findings labeled `blocker / major / minor / nit`, with the file and line; never edits or pushes to the PR branch (`docs/ORCHESTRATION.md` §7.2) |
| **Design reviewer** | Opus / high | Fresh session per design-PR round, max 2 rounds | Design PR, review sheet, `design/tokens.json`, wireframes, rubric (`docs/reviews/README.md` §4) | Rubric scores and findings (`D<round>-<nn>`); one joint hand-off comment to the owner and the collaborator; never edits or pushes to the PR branch |
| **Explorer** (subagent) | Haiku / low | Subagent inside an implementer or reviewer | A narrow question | File paths and short excerpts, no dumps |
| **CI triage** (subagent) | Haiku / low | Subagent inside an implementer | Failing job log | The failing test or rule and the minimal error |

Escalation rules (written down so agents don't decide on their own):
* An implementer that fails `verify.sh` 3 times on the same error, or gets blockers in 2
  consecutive review rounds, hands off to a fresh implementer at **high** effort.
* Security rules, sync and merge logic, and the release workflow are tagged `risk:high`
  in `Mx.md`. Their implementers run at high effort, and their review runs at max effort.
* De-escalation (lower effort or a cheaper model for a role) happens only through the
  metrics retro (section 9.4), never ad hoc.

Role definitions are checked in, so they get reviewed and versioned like code:
* `.claude/agents/explorer.md` and `.claude/agents/ci-triage.md`: subagent definitions,
  with model and effort in their frontmatter.
* `agents/prompts/{orchestrator,planner,implementer,reviewer,design-reviewer}.md`: opening prompts for the sessions.
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
