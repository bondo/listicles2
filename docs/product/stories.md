# Tally user stories (v1)

Task M0.5-01. Status: **draft for the owner's sign-off** (M0.5-O1; the collaborator comments, the owner decides).
Sources: the owner's design-chain decisions Q1-Q5 of 2026-11-15 (state issue #15) and [the plan](../PLAN.md).
Anything those sources do not settle is marked **OQ-n** and listed in [section 10](#10-open-questions); nothing here
decides it. Later milestones trace their acceptance tests to the story ids below (PLAN section 7).

## How to read this

* **Story ids** are stable and never reused: `AUTH` sign-in and account, `HH` household, `LIST` lists, `ITEM` items,
  `VIS` private and shared, `SYNC` offline and sync, `LANG` language.
* Each story has a "so that" value and acceptance criteria written as **Given / When / Then**, so a test can check them.
* **Words used:** *user* = a signed-in person. *Household* = a group of users (PLAN section 1). *Household owner* = the
  one member who manages the household. *List owner* = the user who created a list (not the same as household owner).
  *Private list* = only its list owner can see it. *Shared list* = every member of the list owner's household can see it.
  *Item* = one line in a list: a name, a year and an "I have it" checkbox (Q2).
* The first use case (Q1): a user keeps a collection checklist, for example which Georg Jensen Christmas mobiles they
  own. They type in the items themselves (name, year) and tick the ones they have. A shopping list is just a shared
  list (Q4).

## 1. Sign-in and account

**AUTH-01 Sign in with Google.** As a new user, I want to sign in with my Google account, so that I don't need a new
password and my lists follow me to a new phone.
* Given the app is opened for the first time, when it starts, then it shows the sign-in screen and nothing else.
* Given the sign-in screen, when I pick a Google account in the system account picker, then I am signed in and see my
  lists (LIST-01).
* Given the account picker is open, when I cancel it, then I stay on the sign-in screen and no error is shown.
* Given there is no network, when I try to sign in, then I see a message that the first sign-in needs a connection.

**AUTH-02 Stay signed in.** As a user, I want to stay signed in when I close the app, so that I can open a list at
once.
* Given I am signed in, when I restart the app (also with no network), then I see my lists without signing in again.

**AUTH-03 Sign out.** As a user, I want to sign out, so that someone else can use this phone without seeing my lists.
* Given I am signed in, when I sign out, then I see the sign-in screen.
* Given I signed out, when another person signs in on the same phone, then none of my private lists or my household's
  lists are shown to them, online or offline (assumed: the local copy is removed at sign-out, OQ-13).

**AUTH-04 Delete my account.** As a user, I want to delete my account and my data, so that nothing of mine is kept
(required by Google Play, PLAN section 3.1).
* Given I ask to delete my account, when I confirm, then my private lists, my items and my account are deleted and I see
  the sign-in screen.
* Given I am the household owner and other members remain, when I ask to delete my account, then the app first guides me
  to transfer ownership (HH-06) and deletes nothing until that is done.
* Given I am the last member, when I delete my account, then the household and all its lists are deleted too.
* Given Google demands a recent sign-in, when I confirm, then the app asks me to sign in again and then continues.
* What happens to the shared lists I own when I delete my account or leave: OQ-5.

## 2. Household

**HH-01 Create a household.** As a user, I want to create a household with a name, so that I can share lists with the
people I live with.
* Given I am not in a household, when I enter a name and confirm, then the household exists and I am its household
  owner and only member.
* Given the name is empty or only spaces, when I confirm, then nothing is created and the name field shows an error.
* Given I am already in a household, then creating another one is not offered (one household per user, PLAN section 3).
* Whether a household is needed before I can make lists at all: OQ-1.

**HH-02 Invite someone.** As a household member, I want to send an invite link, so that a person can join my household.
* Given I am a member, when I tap "Invite", then the app makes a single-use link and opens the Android share sheet.
* Given an invite link, then it stops working after 7 days, after one use, or when it is revoked (PLAN section 3.1).
* Given I created an invite (or I am the household owner), when I revoke it, then the link no longer works.

**HH-03 Join a household.** As an invited person, I want to open the link and join, so that I see the household's shared
lists.
* Given I open a valid link and I am not signed in, when the app opens, then I sign in first (AUTH-01) and then see
  the join screen.
* Given the join screen shows the household's name, when I confirm, then I am a member and see its shared lists.
* Given the link is expired, used or revoked, when I open it, then I see a message saying so and join nothing.
* Given I am already in another household, when I open a link, then the app tells me to leave that household first.
* Given there is no network, when I confirm, then I see a message that joining needs a connection.

**HH-04 See who is in my household.** As a member, I want to see the members, so that I know who can see my shared lists.
* Given I am a member, when I open the household screen, then I see each member's display name and who is the owner.

**HH-05 Leave a household.** As a member who is not the household owner, I want to leave, so that I stop sharing.
* Given I confirm leaving, then I no longer see the household's shared lists and my open invites are deleted.
* What happens to my private lists and to the shared lists I own when I leave: OQ-5.

**HH-06 Manage the household (household owner).** As the household owner, I want to remove a member, hand over
ownership or delete the household, so that the household stays under control.
* Given I remove a member, then they lose access to the household's shared lists and their open invites stop working.
* Given I transfer ownership to another member, then that member is the household owner and I am a plain member.
* Given I delete the household and confirm, then every member loses access to its shared lists and the household
  cannot be restored (PLAN section 3.1, soft delete then cleanup).

## 3. Lists

**LIST-01 See my lists.** As a user, I want one screen with all lists I can see, so that I find a list quickly.
* Given I am signed in, when I open the app, then I see my private lists and the lists shared with my household.
* Given a list in that screen, then it shows its name and whether it is private or shared; a shared list owned by
  someone else also shows the list owner's display name.
* Given I have no lists, then I see an empty state that explains lists and offers "Create list".
* Whether each list also shows progress (for example "12 of 30") and the order of lists: OQ-8, OQ-9.

**LIST-02 Create a list.** As a user, I want to create a list with a name, so that I can start collecting items.
* Given I enter a name and confirm, then the list exists, is **private** (Q3) and opens empty.
* Given the name is empty or only spaces, when I confirm, then no list is created and the field shows an error.
* Given a name with spaces at the start or end, when I confirm, then they are removed.

**LIST-03 Rename a list.** As the list owner, I want to rename my list, so that the name stays right.
* Given I am the list owner, when I change the name and confirm, then the new name is shown everywhere, also to members
  if the list is shared.
* Given the new name is empty, when I confirm, then the old name is kept and the field shows an error.
* Whether other members may rename a shared list: OQ-2.

**LIST-04 Delete a list.** As the list owner, I want to delete a list I no longer need, so that my lists stay tidy.
* Given I ask to delete a list, then a confirmation names the list and its number of items.
* Given I confirm, then the list and all its items are gone, also for members if it was shared.
* Given I cancel, then nothing changes.
* Whether other members may delete a shared list, and confirmation versus undo: OQ-2, OQ-10.

## 4. Items

**ITEM-01 Add an item.** As a user, I want to add an item with a name and a year, so that my list holds what I collect.
* Given an open list, when I enter a name (and optionally a year) and confirm, then the item is in the list and not
  checked.
* Given the name is empty, when I confirm, then no item is added.
* Given a year, then it is a whole number; a value that is not a valid year is refused with an error (range: OQ-6).
* Given I add several items in a row, then the input stays open for the next item.
* Whether year is required, and whether two items may have the same name: OQ-6, OQ-11.

**ITEM-02 Edit an item.** As a user, I want to fix an item's name or year, so that a typo doesn't stay.
* Given an item, when I change its name or year and confirm, then the change is saved and shown (also to members).
* Given I clear the name, when I confirm, then the old name is kept and an error is shown.

**ITEM-03 Remove an item.** As a user, I want to remove an item, so that the list only holds what I want.
* Given an item, when I remove it, then it is gone from the list (confirmation or undo: OQ-10).

**ITEM-04 Check off what I have.** As a collector, I want to tick "I have it" on an item, so that I can see what I own
and what I still miss.
* Given an unchecked item, when I tap its checkbox, then it is checked; tapping again unchecks it.
* Given I check an item, when I reopen the app (also offline), then it is still checked.
* Whether the checkbox is always called "I have it", or the word depends on the list (a shopping list): OQ-7.

**ITEM-05 See what a list contains.** As a user, I want to see every item of a list with its year and check state, so
that I know at a glance what I have.
* Given an open list, then each item shows its name, its year (if any) and whether it is checked.
* Given a list with 30 or more items, then all can be reached by scrolling and the list stays readable.
* Given an empty list, then I see an empty state that offers "Add item".
* Item order and a "show only missing" filter: OQ-8.

## 5. Private and shared lists

**VIS-01 Private by default.** As a user, I want new lists to be private, so that I decide what others see (Q3).
* Given I create a list, then only I can see it, even when I am in a household.
* Given a private list of another member, then I cannot see it in the app, and the server refuses to read or change it
  (to be covered by rules allow and deny tests, PLAN section 3.1).

**VIS-02 Share a list with my household.** As a list owner, I want to share one list with my household, so that we can
use it together (for example a shopping list).
* Given I am the list owner and in a household, when I choose "Share with household" and confirm, then every current
  member sees the list in LIST-01.
* Given a list is shared, when a new member joins, then they see it too (assumed; OQ-16).
* Given I am not in a household, when I choose to share, then the app explains that I first need to create or join one.
* Sharing is per list: sharing one list never shares another.

**VIS-03 Use a shared list.** As a household member, I want to open a list someone shared, so that I see what it
contains and help keep it up to date.
* Given a shared list, when I open it, then I see all its items, years and check states, and who owns the list.
* Given a member changes the list, then I see the change (SYNC-02).
* Whether members can add, edit, remove and check items, or only view: OQ-3.

**VIS-04 Stop sharing (proposed, OQ-4).** As a list owner, I want to make a shared list private again, so that I can
undo a share.
* Given the owner decides this is allowed: when I stop sharing and confirm, then members no longer see the list.
* What members keep or lose, and whether this is in v1 at all: OQ-4.

## 6. Offline and sync

**SYNC-01 Use lists offline.** As a user, I want my lists to work without network (in a shop or a basement), so that a
bad connection never stops me.
* Given I opened my lists before, when there is no network, then I can open them and see their last known items.
* Given there is no network, when I create a list, add, edit, remove or check items, then the change shows at once.
* Given I made changes offline, when the network returns, then the changes are saved and other members get them, with
  nothing for me to do.
* Whether the app shows that it is offline: OQ-14.

**SYNC-02 See changes from others.** As a member of a shared list, I want changes from others to appear by themselves,
so that we never work on an old copy.
* Given two members have the same shared list open online, when one checks an item, then the other sees it checked
  within a few seconds without refreshing (PLAN section 7, M2 done-when).
* Given two people change the same field of the same item at about the same time, then the last write wins; changes to
  different fields are both kept (PLAN section 3.2).
* Given a list I have open is deleted or stops being shared, then I leave it and see a short message.

**SYNC-03 Actions that need the network.** As a user, I want a clear message when something needs a connection, so that
I don't wait for nothing.
* Given there is no network, when I sign in the first time, join a household or create an invite, then I see a message
  that this needs a connection, and nothing half-done is left behind.

## 7. Language

**LANG-01 English or Danish.** As a user, I want the app in my language, so that it is easy to use.
* Given my phone is set to Danish, then every screen, message and plural is in Danish; for any other language it is in
  English.
* Given Danish text is longer, then no screen cuts it off.
* Given list and item names, then they are shown as typed and never translated.

**LANG-02 Switch language.** As a user, I want to pick English or Danish for this app only, so that it does not have to
follow my phone.
* Given I pick the other language, when I return to the app, then every screen uses it without a reinstall and my lists
  are unchanged.
* Whether the switch is inside the app or only in Android's per-app language setting: OQ-12.

## 8. Not in v1

Decided as not in v1 (Q1, Q2, Q4); the ones marked *later* are planned for a later milestone:
* A pre-filled catalogue of every release to tick off (*later*, Q1); its data source and licensing are open.
* Per-item status (own / wishlist), quantity and photo (*later*, Q2): not built and not shown.
* Special shopping-list features: aisles or categories, units, merging duplicates, history of bought items (*later*, Q4).
* Recipes, and weekly meal planning (*later*, Q4).
* Sharing a list with one person, with guests, or with people outside the household.
* More than one household per user.
* Notes and tags on items, barcode scanning and title lookup, packing templates and trips: in [the plan](../PLAN.md)
  (sections 1 and 7, M2-M5), but not in the v1 item of Q2 (OQ-15).

## 9. Leave room for

These are constraints for the data model and screens; v1 builds none of them (M2 planning decides how):
* **Item status, quantity and photo** (Q2): an item gets more fields later without breaking items saved by v1, and the
  v1 "I have it" check can become "own" in a later status without losing data.
* **Catalogue** (Q1): a list can later be filled from a catalogue, and an item can point at a catalogue entry while
  keeping the user's own check state and edits.
* **List types** (Q4): a list carries a type (PLAN section 3 has a `kind` field), so a shopping list or a recipe-linked
  list can get its own features later without moving data.
* **Recipes and meal planning** (Q4): other features must be able to add items to a shared list (a recipe's ingredients
  to the shopping list; a week's meal plan to the shopping list).
* **Photos**: storing images likely needs Cloud Storage, which may require the paid Firebase plan (PLAN section 1 says
  free Spark); to check when photos are planned.

## 10. Open questions

For the owner to decide (the collaborator may advise). Nothing above depends on a guess about these.

| Id | Question | Stories |
|---|---|---|
| OQ-1 | Must a user be in a household to make lists? The plan puts every list in a household; with private lists, a user alone could use the app without one. | HH-01, LIST-02, VIS-02 |
| OQ-2 | Who may rename or delete a shared list and change its sharing: only the list owner, or any member? | LIST-03, LIST-04, VIS-04 |
| OQ-3 | In a shared list, may members add, edit, remove and check items, or only view? | VIS-03, ITEM-01..04 |
| OQ-4 | Can a shared list be made private again? If so, in v1, and what do members keep? | VIS-04 |
| OQ-5 | When a list owner leaves the household or deletes the account: are their shared lists deleted, kept for the household, or handed to someone? Are their private lists kept on leaving? | AUTH-04, HH-05, HH-06 |
| OQ-6 | Is the year optional (a shopping item has none) or required? Which years are valid? | ITEM-01, ITEM-02 |
| OQ-7 | Is the checkbox always "I have it", or does the word depend on the list (for example "bought")? | ITEM-04 |
| OQ-8 | Order of items (by year, by name, as added, or by hand) and of lists; is a "show only missing" filter in v1? | LIST-01, ITEM-05 |
| OQ-9 | Should lists and the list screen show progress, such as "12 of 30"? | LIST-01, ITEM-05 |
| OQ-10 | Deleting a list or an item: confirm first, offer undo afterwards, or both? | LIST-04, ITEM-03 |
| OQ-11 | May two items in one list have the same name (for example two mobiles from different years)? | ITEM-01 |
| OQ-12 | Language switch inside the app, or only Android's per-app language setting? | LANG-02 |
| OQ-13 | Assumed: signing out removes the local copy of the user's data from the phone. Confirm. | AUTH-03 |
| OQ-14 | Should the app show when it is offline and when changes are waiting to be sent? | SYNC-01 |
| OQ-15 | The plan (sections 1, 3, 3.1 and 7) still describes inventory items with notes, tags and barcodes, packing lists, trips, and lists that every member can read. Who updates the plan to match Q1-Q4 and private lists, and in which milestone do the packing and barcode features now belong? | all |
| OQ-16 | Assumed: a member who joins later sees the lists already shared with the household. Confirm. | VIS-02 |

**Plan gaps for the next planner** (not decisions): private lists need a list owner and a visibility field and new
security rules (today members can read everything under the household, PLAN section 3.1), with allow and deny tests and
the `risk:high` tag; this changes the M1 and M2 scope in PLAN section 7.
