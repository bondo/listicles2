# Tally user stories (v1)

Status: owner-approved 2026-11-18 (issue #15 comment 6991804241); T2 text size decided (owner, 2026-11-18, issue #15 comment 6991847257) and screen 32a closed (comment 6992107414); recorded in docs/milestones/M1.md section 6.

Task M0.5-01. Status: **owner-approved 2026-11-18** (M0.5-O1, issue #15 comment 6991804241).
Sources: the owner's design-chain decisions Q1-Q5, the answers to OQ-1 to OQ-6 of 2026-11-15 and to OQ-17, OQ-19 and
OQ-23 to OQ-27 and the other answers of 2026-11-16 in section 10 (state issue #15; OQ-23 to OQ-27 follow the sign-in
security review, comment 6927207374), and [the plan](../PLAN.md). Decided questions are in [section 10](#10-decided-questions); anything still unsettled is marked
**OQ-n** and listed in [section 11](#11-open-questions), and nothing here decides it. Later milestones trace their acceptance tests to the story ids below (PLAN section 7).

## How to read this

* **Story ids** are stable and never reused: `START` app start, `AUTH` sign-in and account, `HH` household, `LIST` lists, `ITEM` items,
  `VIS` private and shared, `SYNC` offline and sync, `LANG` language, `THEME` app theme (parked after v1).
* Each story has a "so that" value and acceptance criteria written as **Given / When / Then**, so a test can check them.
* **Accessibility lines for every START, AUTH and HH screen** (owner decision on #15, comment 7058176190): every
  icon-only button has its own English and Danish label; screen titles are headings; at 200 % font scale in Danish
  nothing is cut off (one light golden per screen). The item-row checkbox label is
  decided with ITEM-04 in M2 planning.
* **Words used:** *user* = a signed-in person. *Household* = a group of users (PLAN section 1). *Household owner* = the
  one member who manages the household. *List creator* = the user who created a list (not the same as household owner).
  *Private list* = only its creator can see it. *Shared list* = every member of the creator's household can see it and
  has the same rights as the creator, except that only the creator can stop sharing it (OQ-2, OQ-3, OQ-4).
  *Leaving and household deletion:* when a member leaves, is removed or deletes their account, the lists they created go
  with them (OQ-5); when the household is deleted, each shared list goes back to its creator as a private list (OQ-17).
  *List type* = chosen when a list is created and not changed in v1 (OQ-32): a *plain list* (the default) or a
  *collection list*. *Item* = one line in a list: in a plain list a name and an "I have it" checkbox; in a collection
  list also an optional release year and an optional re-release year (Q2, OQ-6, list types decided 2026-11-16).
* The first use case (Q1): a user keeps a collection checklist, for example which Georg Jensen Christmas mobiles they
  own. They make a collection list, type in the items themselves (name, years) and tick the ones they have. A shopping list is just a shared
  list (Q4).

## 1. App start, sign-in and account

Two sign-in methods in v1: Google (the main one) and email with password (OQ-23). No email-link ("magic link") sign-in
(OQ-27). **Server access:** every Firestore read and write, except a user's own account record, needs a signed-in user whose email is verified
(`email_verified`; Google accounts are verified by Google, password accounts after AUTH-06), invites included. No
security rule may rely on a two-step (MFA) claim: two-step verification (AUTH-09) protects the sign-in, not the rules.
Rules allow and deny tests cover both. Before anyone but the owner installs the app, a privacy text in English and
Danish names Google as processor of email addresses and passwords (OQ-30).

**START-01 Update gate at app start.** As the owner, I want a version that is too old to be told to update, so that
nobody uses a version the data no longer fits (M1-27).
* Given the app starts and its version is below the minimum in the app config document, then it shows a full-screen
  "Update the app" / "Opdater appen" with a button to the releases page on GitHub, before sign-in, with no way past it
  (wireframe 41).
* Given the version equals or is above the minimum, then the app starts as before (AUTH-02).
* Given I am offline and a minimum was read before, then the app uses that last value.
* Given the minimum cannot be read (offline with no cached value), then the app starts normally: the gate never blocks
  a first offline start.

**AUTH-01 Sign in.** As a new user, I want to sign in with my Google account, or with an email and password if I
prefer, so that my lists follow me to a new phone.
*v1 note (OQ-23 amended 2026-11-23, #15 comment 7110878938): Google sign-in is off in v1 (a build-time switch in :app, M1-86). While it is off, the sign-in screen shows only email and password and the Google button and the Google hint below are hidden; the Google bullets apply once the switch is on, after v1.*
* Given the app is opened for the first time, when it starts, then it shows the sign-in screen and nothing else.
* Given the sign-in screen, then "Continue with Google" ("Fortsæt med Google") is the first and main button and "Use email and password" is
  the second (OQ-23).
* Given the sign-in screen, when I pick a Google account in the system account picker, then I am signed in and see my
  lists (LIST-01).
* Given I tap "Use email and password", then I can sign in (AUTH-07), create an account (AUTH-05) or reset my password
  (AUTH-08).
* Given I sign in with Google for the first time (no account yet), then I am asked for my name, filled in from my
  Google account, before I see my lists (AUTH-12).
* Given the account picker is open, when I cancel it, then I stay on the sign-in screen and no error is shown.
* Given there is no network, when I try to sign in, then I see a message that the first sign-in needs a connection.

**AUTH-02 Stay signed in.** As a user, I want to stay signed in when I close the app, so that I can open a list at
once.
* Given I am signed in, when I restart the app (also with no network), then I see my lists without signing in again.

**AUTH-03 Sign out.** As a user, I want to sign out, so that someone else can use this phone without seeing my lists.
* Given I am signed in and the wait for my pending changes finishes (online, everything sent), when I sign out, then I
  see the sign-in screen with no question asked.
* Given the wait for my pending changes does not finish (the app is offline, or it times out), when I choose "Sign
  out", then I am always asked to confirm that changes not yet sent will be lost; "Cancel" keeps me signed in and "Sign
  out anyway" signs me out (M1-14).
* Given that confirmation and an unsent change is known, then it says "Some changes have not been sent yet. If you sign
  out now, they will be lost." / "Nogle ændringer er ikke sendt endnu. Hvis du logger ud nu, går de tabt." (wireframe 39).
* Given that confirmation and no unsent change is known (a write can wait with no screen listening), then it says
  "Changes you made may not have been sent yet. If you sign out now, they may be lost." / "Ændringer, du har lavet, er
  måske ikke sendt endnu. Hvis du logger ud nu, kan de gå tabt." (wireframe 45).
* Given I signed out, when another person signs in on the same phone, then none of my private lists or the lists
  shared with me are shown to them, online or offline (the local copy is removed at sign-out, OQ-13).

**AUTH-04 Delete my account.** As a user, I want to delete my account and my data, so that nothing of mine is kept
(required by Google Play, PLAN section 3.1).
* Given I ask to delete my account, when I confirm, then every list I created (private and shared) with its items and my
  account are deleted, and I see the sign-in screen (OQ-5); members lose the shared lists I created.
* Given I am the household owner and other members remain, when I ask to delete my account, then the app first guides me
  to transfer ownership (HH-06) and deletes nothing until that is done (wireframe 38: "Transfer ownership first",
  with "OK" and "Go to household").
* Given I am the last member, when I delete my account, then the household is deleted too (my lists are deleted with
  my account, so nothing returns to anyone, OQ-17).
* Given the server demands a recent sign-in, when I confirm, then the app asks me to sign in again with the method I
  used (Google, or my password plus a code if two-step verification is on, AUTH-09) and then continues.
* Items I added to lists other people created stay in those lists; items others added to my shared lists go with those lists; my name on remaining items is removed (OQ-18).

**AUTH-05 Create an account with email and password.** As a new user without (or not wanting to use) a Google account,
I want to create an account with my email and a password, so that I can use Tally too.
* Given the create-account screen, then it asks for "Your name", my email and a password, and a note says that the
  household sees the name and never the email (AUTH-12).
* Given I leave "Your name" empty or only spaces, when I confirm, then nothing is created and the field shows an error.
* Given I enter a name, a valid email that has no account and a password of at least 12 characters, when I confirm, then the
  account is created, a verification email is sent, and I see the "check your email" screen (AUTH-06).
* Given a password shorter than 12 characters, when I confirm, then nothing is created and the field shows an error;
  there are no other password rules (no required digits, symbols or capitals, OQ-26).
* Given the email is not a valid address, when I confirm, then nothing is created and the field shows an error.
* Given the email already has an account (either method), when I confirm, then no second account is created, no email
  is sent, and I see the same "check your email" screen as for a new account (AUTH-10).
* Given there is no network, when I confirm, then I see a message that this needs a connection.

**AUTH-06 Verify my email.** As a user who created a password account, I want to confirm my email, so that only the
owner of the address can use the account.
* Given I created an account (AUTH-05), then I see a screen saying a link was sent to my email, with the line "If you
  already have an account with this email, no new email is sent: sign in the way you created it", and the buttons
  "Continue", "Send again" and "Sign out" (wireframe 27). The line is shown to everyone, whether or not the email
  already has an account (AUTH-10).
* Given I opened the link in the email, when I tap "Continue", then I see my lists (or the join screen, HH-03).
* Given the email and the page its link opens, then they are Firebase's defaults, with the email text in English and
  Danish (OQ-29; the same for AUTH-08).
* Given I have not opened the link yet, when I tap "Continue", then I see a message that the email is not verified yet
  and stay on the screen.
* Given I tap "Send again" many times, then I see "Try again later" instead of a new email.
* Given my email is not verified, when I sign in again later, then I see this screen again at every start, and the
  server refuses to read or change any data of mine except my own account record (rules allow and deny tests).

**AUTH-07 Sign in with email and password.** As a user with a password account, I want to sign in with my email and
password, so that I reach my lists on any phone.
* Given the right email and password, when I confirm, then I see my lists (or the code step if AUTH-09 is on, or the
  verify screen if AUTH-06 is not done).
* Given a wrong email or a wrong password, when I confirm, then I see one message that does not say which one was
  wrong or whether the account exists (OQ-34(c)): "Wrong email or password. If you signed up with Google, use Continue
  with Google." / "Forkert e-mail eller adgangskode. Hvis du oprettede dig med Google, så brug Fortsæt med Google."
  It is the same for every failed sign-in, also for an email that only has a Google account.
* Given many failed attempts, when I try again, then I see "Too many attempts, try again later".
* Given there is no network, when I confirm, then I see a message that the first sign-in needs a connection.

**AUTH-08 Reset my password.** As a user who forgot my password, I want a reset email, so that I can get back in.
* Given I enter an email and confirm, then I always see "If an account exists for this email, we sent an email with a
  link", whether or not an account exists.
* Given I open the link and set a new password of at least 12 characters (OQ-26), then I can sign in with it and the
  old password no longer works.
* Given the link is expired or already used, when I open it, then I see a message saying so and can ask again.
* Given two-step verification is on (AUTH-09), then after a reset I still need a code to sign in.

**AUTH-09 Two-step verification (optional).** Depends on the owner's check that the Identity Platform upgrade needs no
billing (OQ-25 verification). As a password user, I want to add a code from an authenticator app, so that a stolen
password alone is not enough.
* Given I start turning it on, then a warning first says that if I lose the authenticator app I may lose access to
  my account; it does not mention an administrator. There are no backup codes in v1 (OQ-28).
* Given a verified password account, when I turn on two-step verification in Account, then (after a recent sign-in) I
  see a QR code and a key for an authenticator app, and it is on only after I enter a correct code.
* Given it is on, when I sign in with my password (AUTH-07) or sign in again (AUTH-04), then I must also enter a
  6-digit code; a wrong code shows an error, many wrong codes show "try again later".
* Given it is on, when I turn it off (after a recent sign-in with a code), then sign-in needs only my password again.
* Given a Google account, then this is not offered (OQ-24: optional, for password accounts).
* Given I lost the authenticator app, then the second step can only be removed by hand in the Firebase console (OQ-28).

**AUTH-10 Same email, another method.** As a user who signed up one way, I want a clear way back when I use the other
way, so that I never get two accounts or lose my lists.
* Email-enumeration protection is on, so the app cannot tell which method an email used, and no screen or message of
  the app reveals whether an account exists for an email. Whether Firebase's own sign-up service still reports an
  existing email to someone who calls it directly, outside the app, is checked in M1 (OQ-34); if it does, sign-up
  reveals that an account exists to such a caller; the owner accepted that for v1 (OQ-34(d), section 10; App Check,
  M1-26, makes scripted calls harder).
* Given one email with an account (either method) and one without, when I create a password account with each, then
  both end on the same "check your email" screen (AUTH-05, AUTH-06) with the same text and buttons, and tapping
  "Continue" (link not opened: "not verified yet") or "Send again" shows the same messages for both; only the email
  without an account gets an account and an email.
* Given I sign in with a password (AUTH-07) or ask for a reset (AUTH-08) for an email, then the messages are the same
  whether or not an account exists and whichever method it uses (what a Google-only email gets: OQ-34(b)).
* Given I sign in with Google and the email already has a password account, then Firebase trusts Google only for
  `@gmail.com` addresses (M1.md, docs-check note 3). For another address the sign-in fails and the sign-in screen shows
  "This email already has an account. Sign in with your email and password." / "Der findes allerede en konto med
  denne e-mail. Log ind med din e-mail og adgangskode." (wireframe 44). What Firebase does for a Gmail address is
  checked in M1 (OQ-34(a)). In every case no lists are lost and no second account is created.
* Given I signed in the way I created the account, then I see my lists as before; adding a second method or changing
  the email comes after v1 (OQ-31).

**AUTH-11 Change my password.** As a password user, I want to change my password, so that I can replace a weak or
leaked one (OQ-31).
* Given a password account, when I choose "Change password" in Account, then I first sign in again (with a code if
  AUTH-09 is on), then enter a new password of at least 12 characters (OQ-26); after that the old one no longer works.
* Given there is no network, then I see "This needs a connection".

**AUTH-12 My name.** As a user, I want the household to see my name and not my email, so that I stay private
(owner decision on #191, 2026-11-19).
* Given I create a password account, then "Your name" is required (AUTH-05).
* Given I sign in with Google for the first time, then I am asked for my name, filled in from my Google account, and I
  must confirm a non-empty name before I see my lists (wireframe 42); an empty name shows the error "Enter your name".
* Given I am signed in with no name saved, when the app starts, then it shows the name step (wireframe 42) before my
  lists; it has no back arrow, and the system Back button leaves the app and saves nothing.
* Given I am signed in, when I choose "Your name" in Account, then I can change it (wireframe 43); the household sees
  the new name. This needs a connection (SYNC-03).
* Given I am in a household, then members see my name and never my email (HH-04); the app never falls back to the
  email.

## 2. Household

**HH-01 Create a household.** As a user, I want to create a household with a name, so that I can share lists with the
people I live with.
* Given I am not in a household, when I enter a name and confirm, then the household exists and I am its household
  owner and only member.
* Given the name is empty or only spaces, when I confirm, then nothing is created and the name field shows an error.
* Given I am already in a household, then creating another one is not offered (one household per user, PLAN section 3).
* A household is not needed to make lists; I need one only to share a list (OQ-1). The app never creates one for me
  (OQ-20).

**HH-02 Invite someone.** As a household member, I want to send an invite link, so that a person can join my household.
* Given I am a member, when I tap "Invite", then the app makes a single-use link and opens the Android share sheet.
* Given an invite link, then it stops working after 7 days, after one use, or when it is revoked (PLAN section 3.1).
* Given I created an invite (or I am the household owner), when I revoke it, then the link no longer works.

**HH-03 Join a household.** As an invited person, I want to open the link and join, so that I see the household's shared
lists.
* Given the app is not installed, when I open the link, then a web page tells me to install Tally and then tap the
  link again (OQ-21).
* Given I open a valid link and I am not signed in, when the app opens, then I sign in first (AUTH-01), or create an
  account and verify my email (AUTH-05, AUTH-06), and then see the join screen.
* Given my email is not verified, then the server refuses to read the invite (rules allow and deny tests).
* Given the join screen shows the household's name, when I confirm, then I am a member and see its shared lists.
* Given the link is expired, used or revoked, when I open it, then I see a message saying so and join nothing.
* Given I am already in another household, when I open a link, then the app tells me to leave that household first.
* Given there is no network, when I confirm, then I see a message that joining needs a connection.

**HH-04 See who is in my household.** As a member, I want to see the members, so that I know who can see my shared lists.
* Given I am a member, when I open the household screen, then I see each member's display name and who is the household owner, and never an email address (AUTH-12).

**HH-05 Leave a household.** As a member who is not the household owner, I want to leave, so that I stop sharing.
* Given I confirm leaving, then I no longer see lists other members shared, and my open invites are deleted.
* Given I confirm leaving, then every list I created goes with me: it stays mine and is private to me, and the other
  members lose the lists I had shared (OQ-5). The confirmation says so and offers "Cancel" and "Leave" (wireframe 34).
  (Household deletion works differently: HH-06.)
* Given I added items to lists other members created, then those items stay in those lists, shown as added by a former
  member (OQ-18).

**HH-06 Manage the household (household owner).** As the household owner, I want to remove a member, hand over
ownership or delete the household, so that the household stays under control.
* Given I remove a member, then they lose access to the lists others shared, their open invites stop working, and the
  lists they created go with them as in HH-05, so the other members lose the lists they had shared (OQ-5); items they
  added to other members' lists stay, as in HH-05 (OQ-18).
* Given I choose "Remove from household" for a member, then I am asked to confirm, and the confirmation says that
  the lists they created go with them (wireframe 35).
* Given I transfer ownership to another member, then I am asked to confirm (wireframe 36), and then that member is the
  household owner and I am a plain member.
* Given I choose to delete the household, then I am asked to confirm, and the confirmation says that shared lists go
  back to their creators and that the household cannot be restored (wireframe 37).
* Given I confirm, then no one is a member any more and the household cannot be restored (PLAN section 3.1, soft delete
  then cleanup).
* Given the household is deleted, then every list that was shared with it goes back to being private to its creator,
  with all its items, and every private list stays as it was: nothing is lost (OQ-17).
* Given a list I created went back to private because the household was deleted, when I next open the app, then I see
  a dialog I must acknowledge saying that the household was deleted and my shared lists are private again; I can share them again once I am in a
  household (VIS-02). The owner who deleted the household sees no such dialog (owner decision, #15 comment 7021901747).
* Given the household owner removed me, when I next open the app, then I see a dialog I must acknowledge: "You were
  removed from the household" / "Du er fjernet fra husstanden", saying that the lists I created will stay with me and
  stay private, and that I will no longer see lists others shared (wireframe 40, M1-21).
* Given the household is deleted, then a former member cannot read or change a list that someone else created and had
  shared with it, and the creator still can (rules allow and deny tests).

## 3. Lists

**LIST-01 See my lists.** As a user, I want one screen with all lists I can see, so that I find a list quickly.
* Given I am signed in, when I open the app, then I see my private lists and the lists shared with my household.
* Given a list in that screen, then it shows its name and whether it is private or shared; a shared list created by
  someone else also shows the creator's display name.
* Given I have no lists, then I see an empty state that explains lists and offers "Create list".
* Given my lists, then the most recently used is first ("used" = last opened by me, kept on the device only; lists never opened on this device follow their last change: OQ-35), and each shows its progress as
  small text under its name, for example "12 of 30" (OQ-8, OQ-9). There is no search in v1.

**LIST-02 Create a list.** As a user, I want to create a list with a name and a type, so that I can start collecting
items.
* Given I enter a name and confirm, then the list exists, is **private** (Q3), is a plain list unless I chose
  "Collection", and opens empty.
* Given I created a list, then its type cannot be changed afterwards (OQ-32).
* Given the name is empty or only spaces, when I confirm, then no list is created and the field shows an error.
* Given a name with spaces at the start or end, when I confirm, then they are removed.

**LIST-03 Rename a list.** As a user who can see a list, I want to rename it, so that the name stays right.
* Given I created the list, or it is shared with me (OQ-2, OQ-3), when I change the name and confirm, then the new name
  is shown everywhere, also to members if the list is shared.
* Given the new name is empty, when I confirm, then the old name is kept and the field shows an error.

**LIST-04 Delete a list.** As a user who can see a list, I want to delete it when it is no longer needed, so that my
lists stay tidy.
* Given I created the list or it is shared with me (OQ-2, OQ-3), when I delete it, then I am first asked to confirm, with
  the list's name and its number of items (OQ-10); when I confirm, the list and all its items are gone, also for
  members if it was shared.
* Given I cancel, then nothing changes.

## 4. Items

**ITEM-01 Add an item.** As a user, I want to add an item with a name (and its years in a collection list), so that
my list holds what I collect.
* Given an open list I can see (mine, or shared with me: OQ-3), when I enter a name and confirm, then the item is in
  the list and not checked.
* Given a plain list, then the input asks only for a name; there are no year fields.
* Given a collection list, then the release year and the re-release year are optional (OQ-6), with the rules below.
* Given the name is empty, when I confirm, then no item is added.
* Given a release year or a re-release year, then it is a whole number from 1900 to the current year plus 50; any other
  value is refused with an error (OQ-6).
* Given only a re-release year, or only a release year, when I confirm, then the item is saved with just that year.
* Given a re-release year earlier than the release year, when I confirm, then the item is saved: the two years have no
  rule between them, each only has to be in the valid range (OQ-19).
* Given I add several items in a row, then the input stays open for the next item.
* Given an item with that name is already in the list, when I add another with the same name, then it is saved; a quiet hint ("Already in this list") shows while typing (OQ-11).

**ITEM-02 Edit an item.** As a user, I want to fix an item's name (or years), so that a typo doesn't stay.
* Given an item, when I change its name, or in a collection list its release year or re-release year (same rules as
  ITEM-01), and confirm, then the change is saved and shown (also to members).
* Given I clear the name, when I confirm, then the old name is kept and an error is shown.
* Given an item in a collection list, when I clear a year and confirm, then the item has no such year.

**ITEM-03 Remove an item.** As a user, I want to remove an item, so that the list only holds what I want.
* Given an item, when I remove it, then it is gone at once with no confirmation, and "Undo" shows in a snackbar that stays until I act, dismiss it or leave the list
  (OQ-10, OQ-39); when I tap "Undo", the item is back as it was.

**ITEM-04 Check off what I have.** As a collector, I want to tick "I have it" on an item, so that I can see what I own
and what I still miss.
* Given an unchecked item, when I tap its checkbox, then it is checked; tapping again unchecks it.
* Given I check an item, when I reopen the app (also offline), then it is still checked.
* Given an item is checked, then it stays in its place in the order.
* Given any list, then the checkbox is called "I have it" (Danish "Jeg har den") in v1 (OQ-7).

**ITEM-05 See what a list contains.** As a user, I want to see every item of a list with its check state (and years),
so that I know at a glance what I have.
* Given an open plain list, then each item shows its name and whether it is checked, sorted by name, ignoring case,
  with æ, ø and å after z, in that order (OQ-33). Items whose names are equal under this rule keep the order they
  were added in, oldest first.
* Given an open collection list, then each item also shows its release year and re-release year (each only if set),
  sorted by release year, oldest year first, with items without a release year last (OQ-33); items with the same
  release year (or both without one) are sorted by name with the same rule as plain lists, and then oldest added
  first. The re-release year does not change the order.
* Given an open list, then its progress shows at the top, for example "12 of 30" (OQ-9).
* Given a list with 30 or more items, then all can be reached by scrolling, and no name or year is cut off at the
  default font size in English or Danish.
* Given an empty list, then I see an empty state that offers "Add item".
* Given I turn on "Show only missing", then only unchecked items are shown (OQ-8). No search or manual order in v1.

## 5. Private and shared lists

**VIS-01 Private by default.** As a user, I want new lists to be private, so that I decide what others see (Q3).
* Given I create a list, then only I can see it, even when I am in a household; I need no household to create it (OQ-1).
* Given a private list of any other user (in my household or not), then I cannot see it in the app, and the server
  refuses to read or change it (to be covered by rules allow and deny tests, PLAN section 3.1).
* Given a list shared with a household I am not in, then I cannot see it, and the server refuses to read or change it.

**VIS-02 Share a list with my household.** As a list creator, I want to share one list with my household, so that we can
use it together (for example a shopping list).
* Given I created a private list and I am in a household, when I choose "Share with household" and confirm, then every current
  member sees the list in LIST-01.
* Given a list is shared, when a new member joins, then they see it too (OQ-16).
* Given I am not in a household, then "Share with household" is disabled, with a message that I need a household to
  share (OQ-20); a household step that leads there comes after v1.
* Sharing is per list: sharing one list never shares another.

**VIS-03 Use a shared list.** As a household member, I want to open a list someone shared, so that I see what it
contains and help keep it up to date.
* Given a shared list, when I open it, then I see all its items, years and check states, and who created the list.
* Given a list is shared with me, then I can do everything its creator can: add, edit, check and remove items, rename
  the list and delete it (OQ-3); the only exception is stopping the share (VIS-04).
* Given a member changes the list, then I see the change (SYNC-02).

**VIS-04 Stop sharing.** As a list creator, I want to make a shared list private again, so that I can undo a share.
* Given I created a shared list, when I stop sharing and confirm, then it is private to me again with all its items,
  and the other members no longer see it (OQ-2, OQ-4).
* Given a list someone else created is shared with me, then "Stop sharing" is not offered to me, and the server refuses
  the change (to be covered by rules allow and deny tests).
* Given a list someone else created is shared with me, when I rename it or change its items, then I cannot change who
  created it or which household it is shared with, and the server refuses such a change (rules allow and deny tests).

## 6. Offline and sync

**SYNC-01 Use lists offline.** As a user, I want my lists to work without network (in a shop or a basement), so that a
bad connection never stops me.
* Given I opened my lists before, when there is no network, then I can open them and see their last known items.
* Given there is no network, when I create a list, add, edit, remove or check items, then the change shows at once.
* Given I made changes offline, when the network returns, then the changes are saved and other members get them, with
  nothing for me to do.
* Given there is no network, then a small banner says "Offline: changes are sent when you are online again" (OQ-14).

**SYNC-02 See changes from others.** As a member of a shared list, I want changes from others to appear by themselves,
so that we never work on an old copy.
* Given two members have the same shared list open online, when one checks an item, then the other sees it checked
  without refreshing (PLAN section 7, M2 done-when); time limit for the test: set in M2 planning.
* Given two people change the same field of the same item at about the same time, then the last write wins (PLAN
  section 1, Sync); changes to different fields are both kept (PLAN section 3.2).
* Given I edited an item offline and another member deleted it meanwhile, when the network returns, then the item stays
  deleted and I see a short message that it was removed (PLAN section 3.2).
* Given a list I have open is deleted, stops being shared, or leaves the household with its creator (HH-05, HH-06),
  then I leave it and see a short message.
* Given I edited a list offline and lost access to it meanwhile (the cases above, or I was removed), when the network
  returns, then my unsent edits to that list are dropped and I see the same short message.

**SYNC-03 Actions that need the network.** As a user, I want a clear message when something needs a connection, so that
I don't wait for nothing.
* Given there is no network, when I sign in the first time, create an account, verify my email, reset or change my
  password, open an invite link, join, create, leave or manage a household, create an invite, share a list or stop
  sharing it, delete my account, or turn two-step verification on or off, then I see "This needs a connection" and
  nothing half-done is left behind (OQ-22). Deleting the account and turning two-step verification on or off need a
  recent sign-in with the server (AUTH-04, AUTH-09), so they cannot wait offline.

## 7. Language

**LANG-01 English or Danish.** As a user, I want the app in my language, so that it is easy to use.
* Given my phone is set to Danish, then every screen, message and plural is in Danish; for any other language it is in
  English.
* Given Danish text is longer, then no screen cuts it off.
* Given list and item names, then they are shown as typed and never translated.

**LANG-02 Switch language.** As a user, I want to pick English or Danish for this app only, so that it does not have to
follow my phone.
* Given I pick the other language in Android's per-app language setting (no switch inside the app in v1, OQ-12), when I
  return to the app, then every screen uses it without a reinstall and my lists
  are unchanged.

## 8. Not in v1

Decided as not in v1 (Q1, Q2, Q4); the ones marked *later* are planned for a later milestone:
* A pre-filled catalogue of every release to tick off (*later*, Q1); its data source and licensing are open.
* Per-item status (own / wishlist), quantity and photo (*later*, Q2): not built and not shown.
* Special shopping-list features: aisles or categories, units, merging duplicates, history of bought items (*later*, Q4).
* Recipes, and weekly meal planning (*later*, Q4).
* Sharing a list with one person, with guests, or with people outside the household (Q3 shares with the household).
* More than one household per user (PLAN section 3: a user record holds one household id).
* Sign-in with an email link ("magic link", OQ-27); reconsidered only if the project moves to the paid Blaze plan.
* Choosing an app theme (THEME-01, parked until after v1); v1 has one palette, Petrol (T1).
* Notes and tags on items, barcode scanning and title lookup, packing templates and trips: in [the plan](../PLAN.md)
  (sections 1 and 7, M2-M5), but not in the v1 item of Q2 (OQ-15). Search and manual order are
  not in v1; sorting and the "show only missing" filter are (OQ-8).

**THEME-01 Choose an app theme** (parked until after v1, like the packing and barcode items of OQ-36; not built, not tested
and not shown in v1). As a user, I want to pick the app's colour theme, so that the app looks the way I like.
* Given the app has more than one theme, when I open the theme setting and pick one, then every screen uses it at once,
  in light and in dark, and it is still in use after I restart the app.
* Given I have never picked a theme, then the app uses Petrol, the v1 palette (T1).
* Given any theme, then every text and control pair keeps the WCAG AA contrast (4.5 for text, 3 for the outline), in light
  and in dark; a theme that fails the check in `design/tokens.json` is not offered.
* Given the setting, then its name, the theme names and any message are in English and Danish (LANG-01).
* Which themes are offered, whether the choice follows me to another phone, and whether "follow the phone's colours" is one of them
  are open and decided when this story is planned.
**Constraint for v1:** design tokens stay theme-swappable. Colors are Material roles only (`design/tokens.json`), `Theme.kt`
builds the `ColorScheme` from one color set per theme, and no screen or page hard-codes a palette value, so a theme is a
new light and dark set with nothing else to change. Enforced today by `scripts/design_tokens.py` (both themes have the same
roles, every required contrast pair passes) and by the tests against the retired teal values; that `Theme.kt` is built from
the tokens, and that no screen hard-codes a color, is checked with M1-04 and the M1 screens, not yet.

## 9. Leave room for

These are constraints for the data model and screens; v1 builds none of them (M2 planning decides how):
* **Item status, quantity and photo** (Q2): the v1 item is a name and "I have it", plus in a collection list an
  optional release year and re-release year (OQ-6); it gets more fields later without breaking items saved by v1, and the v1 "I have it" check can
  become "own" in a later status without losing data.
* **Per-list permissions** (OQ-3): later the creator may choose per list who can edit and who can only view; v1 gives
  everyone the list is shared with the creator's rights (except stopping the share).
* **Keeping shared lists on leaving** (OQ-5): later a person who leaves chooses, per shared list they created, whether
  it stays with the household; in v1 it always goes with them.
* **Who added an item** (OQ-18): each item records who added it, so OQ-18 (decided) can show added-by, or "former member".
* **Catalogue** (Q1): a list can later be filled from a catalogue, and an item can point at a catalogue entry while
  keeping the user's own check state and edits.
* **List types** (Q4): a list carries a type (PLAN section 3 has a `kind` field; v1 has plain and collection), so a shopping list or a recipe-linked
  list can get its own features later without moving data; turning a plain list into a collection list may come later
  (OQ-32).
* **Recipes and meal planning** (Q4): other features must be able to add items to a shared list (a recipe's ingredients
  to the shopping list; a week's meal plan to the shopping list).
* **Infinite undo/redo per list** (owner, 2026-11-18, #15 comment 6991020343): "After v1, we need to have infinite global
  undo/redo internally for each list. This should include conflict handling, so an undo after a conflict shows the other
  side of the conflict." v1 builds none of it: it keeps no history and stays last write wins per field (SYNC-02, PLAN
  section 3.2). The constraint is only that the v1 design must not rule out adding, later, a per-list history of changes
  across all members that undo and redo can replay in order, and keeping the side that lost a conflict so an undo can
  show it.
* **Photos**: storing images likely needs Cloud Storage, which may require the paid Firebase plan (PLAN section 1 says
  free Spark); to check when photos are planned.

## 10. Decided questions

Answered by the owner on 2026-11-15 to 2026-11-19 (state issue #15); the stories above follow them.

**Labels for the M1 strings** (decided): the re-release year is "re-release year" in English and "Genudgivelsesår" in Danish
(OQ-19); an item is "ting" in Danish; the checkbox is "I have it", Danish "Jeg har den" (OQ-7).

| Id | Decision (owner, 2026-11-15 unless marked) | Stories |
|---|---|---|
| OQ-1 | **Decided:** no household is needed to create lists. After sign-in a user can create private lists at once; creating or joining a household is needed only to share a list. Whether the household is created behind the scenes is left to M1/M2 planning. | HH-01, LIST-02, VIS-01, VIS-02 |
| OQ-2 | **Decided:** only the creator of a list can stop sharing it; everything else is equal for everyone the list is shared with (OQ-3). | LIST-03, LIST-04, VIS-04 |
| OQ-3 | **Decided:** in v1 everyone a list is shared with has the same rights as its creator: add, edit, check and remove items, rename the list, delete the list. Per-list permissions come later (section 9). | VIS-03, LIST-03, LIST-04, ITEM-01..04 |
| OQ-4 | **Decided:** stopping sharing is in v1; the list becomes private to its creator again and the other members lose access. | VIS-04 |
| OQ-5 | **Decided:** in v1 every list a person created goes with them when they leave the household, are removed, or delete their account, including the shared lists they created (the other members lose those lists); items they added to other people's lists stay (OQ-18). Later the leaver chooses per shared list whether it stays (section 9). | AUTH-04, HH-05, HH-06 |
| OQ-6 | **Decided:** the year is optional, valid from 1900 to the current year plus 50. An item can have two years: the original release year and, optionally, a re-release year (rules between them: OQ-19). | ITEM-01, ITEM-02, ITEM-05 |
| OQ-7 | **Decided (2026-11-16):** the checkbox is always "I have it" ("Jeg har den") in v1; it may depend on the list type later. | ITEM-04 |
| OQ-8 | **Decided (2026-11-16):** items sorted per list type (ITEM-05); lists by most recently used; a "show only missing" filter in v1; no search and no manual order. Checked items stay in place. | LIST-01, ITEM-05 |
| OQ-9 | **Decided (2026-11-16):** progress ("12 of 30") as small text under the list name and at the top of the list. | LIST-01, ITEM-05 |
| OQ-10 | **Decided (2026-11-16):** deleting an item has no confirmation and an undo (timing: OQ-39); deleting a list asks to confirm first. | LIST-04, ITEM-03 |
| OQ-11 | **Decided (2026-11-18, issue #15 comment 6991876940):** two items in one list may have the same name; the app shows a quiet hint ("Already in this list") while typing but does not block; in collection lists the years tell them apart. | ITEM-01 |
| OQ-12 | **Decided (2026-11-16):** only Android's per-app language setting in v1, no switch inside the app. | LANG-02 |
| OQ-13 | **Decided (2026-11-17, see M1-14 in [M1](../milestones/M1.md)):** signing out removes the local copy of the user's data from the phone. | AUTH-03 |
| OQ-14 | **Decided (2026-11-16):** a small banner shows the offline state and that changes wait to be sent. | SYNC-01 |
| OQ-16 | **Confirmed (2026-11-18, issue #15 comment 6991888410):** a member who joins later sees all lists already shared with the household (sharing is per household, not per person). | VIS-02 |
| OQ-17 | **Decided (2026-11-16):** when a household is deleted, its shared lists go back to being private to their creators; nothing is lost, creators are notified and may share again later. This is the one exception to the OQ-5 rule: a member who leaves, is removed or deletes their account still takes the lists they created with them. | AUTH-04, HH-05, HH-06 |
| OQ-18 | **Decided (2026-11-18, issue #15 comment 6992089109):** an item belongs to the list it is in. (a) Items a person added to other people's lists stay there (shown as added by a former member); (b) items others added to that person's shared lists go with those lists. On account deletion the person's name on remaining items is removed (anonymised). **Added (2026-11-19, #15 comment 7000527780):** when another member removes an item and taps Undo, the item keeps its original adder, not the member who pressed Undo. Open, deferred to M2 planning (#15 comment 7000513565): anonymising at leave, removal, stop sharing or household deletion. | AUTH-04, HH-05, HH-06 |
| OQ-19 | **Decided (2026-11-16):** no rule between the two years: each is optional, either may be set alone and in any order; each only has to be from 1900 to the current year plus 50. Labels: English "re-release year", Danish "Genudgivelsesår". | ITEM-01, ITEM-02, ITEM-05 |
| OQ-20..22 | **Decided (2026-11-16):** see [flow section 10](flow.md#10-new-open-questions): sharing without a household is disabled; an invite page "install, then tap the link again"; household, invite and sharing actions need a connection. | VIS-02, HH-03, SYNC-03 |
| OQ-23 | **Decided (2026-11-16):** email and password sign-in is built together with Google in v1 (M1), not later. Google stays the main button. **Amended (2026-11-23, owner decision, #15 comment 7110878938):** Google sign-in does not block v1. v1 ships with email and password only; Google stays in the code behind a build-time switch in :app (M1-86), off in v1, and is turned on after v1 once Tally has a public support email (M3-O1, then M3-O2 and M3-O3, then an app update). While the switch is off, "Continue with Google" is not shown. | AUTH-01, AUTH-05..08, AUTH-10 |
| OQ-24 | **Decided (2026-11-16):** two-step verification with an authenticator app (TOTP) is optional, for password accounts. | AUTH-09 |
| OQ-25 | **Decided (2026-11-16):** accept the Identity Platform upgrade for TOTP if it needs no billing; the owner verifies this first, so AUTH-09 depends on it. | AUTH-09 |
| OQ-26 | **Decided (2026-11-16):** passwords have at least 12 characters and no other rules; the Firebase password policy in Require mode plus a check in the app. | AUTH-05, AUTH-08 |
| OQ-27 | **Decided (2026-11-16):** no email-link ("magic link") sign-in in v1; reconsider only on the Blaze plan. | section 8 |
| OQ-28 | **Decided (2026-11-16):** a lost authenticator app is reset by hand in the Firebase console; no backup codes in v1; the warning never mentions an administrator. | AUTH-09 |
| OQ-29 | **Decided (2026-11-16):** Firebase's default pages and email templates, translated to English and Danish in the console (template languages to check in M1); own pages may come later. | AUTH-06, AUTH-08 |
| OQ-30 | **Decided (2026-11-16):** a planner drafts the privacy text in Danish and English during M1, naming Google as processor; the owner approves it; ready before anyone but the owner installs the app. | AUTH-05 |
| OQ-31 | **Decided (2026-11-16):** changing the password is in v1 (AUTH-11); changing the email and linking a second method come after v1. | AUTH-10, AUTH-11 |
| OQ-32 | **Decided (2026-11-16):** a list's type cannot be changed in v1. Turning a plain list into a collection list may come later (section 9). | LIST-02 |
| OQ-33 | **Decided (2026-11-16):** collection lists put items without a release year last; plain lists sort by name ignoring case, with æ, ø, å after z. | ITEM-05 |
| OQ-34(b) | **Decided (2026-11-17, M1.md):** a password reset may add a password to a Google-only account (same account, no lists lost); M1-99 records what Firebase does. | AUTH-08, AUTH-10 |
| OQ-34(c) | **Decided (2026-11-17, texts 2026-11-19, issue #192):** every failed password sign-in shows "Wrong email or password. If you signed up with Google, use Continue with Google." / "Forkert e-mail eller adgangskode. Hvis du oprettede dig med Google, så brug Fortsæt med Google." The Google button is "Continue with Google" / "Fortsæt med Google". **Note (2026-11-23, #15 comment 7110878938):** while the Google switch is off (v1), the "If you signed up with Google, use Continue with Google." sentence is hidden and only "Wrong email or password." / "Forkert e-mail eller adgangskode." is shown. | AUTH-01, AUTH-07 |
| OQ-34(a), non-Gmail | **Decided (2026-11-17, texts 2026-11-19):** Google is trusted only for `@gmail.com`. A non-Gmail Google account whose email has a password account fails with "This email already has an account. Sign in with your email and password." / "Der findes allerede en konto med denne e-mail. Log ind med din e-mail og adgangskode." | AUTH-10 |
| Name | **Decided (2026-11-19, issue #191):** a required "Your name" at create account, and on the first Google sign-in (filled in from Google); editable in Account; members never see emails. | AUTH-05, AUTH-12, HH-04 |
| OQ-34(d) | **Decided (2026-11-18, issue #15 comment 6991970000):** accept for v1 that Firebase sign-up reveals an existing email to direct API callers; the app shows the same screen either way (AUTH-10); App Check (M1-26) makes scripted calls harder. Parts (a) to (c) are in M1. | AUTH-10 |
| OQ-35 | **Decided (2026-11-18, issue #15 comment 6991995012):** "most recently used" (LIST-01) = last opened by me, kept on the device only (no Firestore writes or reads); lists never opened on this device follow `updatedAt`. | LIST-01 |
| OQ-38 | **Decided (2026-11-18, issue #15 comment 6992014550):** no Blaze backups; an in-app export of every list I can see (my own lists and lists shared with me; scope decided 2026-11-19, #15 comment 7000534815) to a JSON or CSV file through the system file picker, in M2, before the first external tester (also covers data portability). | none yet (M2) |
| OQ-39 | **Decided (2026-11-18, issue #15 comment 6992067725):** follow Material 3: the Undo snackbar stays until the user acts, dismisses it or leaves the list (the delete is already written); the 10 s in the wireframes is dropped. Replaces the 10 seconds in OQ-10. | ITEM-03 |
| T1 | **Decided (2026-11-17, issue #15 comment 6956773225):** the app palette is Petrol (a teal leaning blue, with an amber offline bar), light and dark, in `design/tokens.json`. After v1 users may pick a theme themselves (THEME-01); tokens stay theme-swappable. | THEME-01 |
| Types | **Decided (2026-11-16, issue #15 comment 6927705004):** two list types, chosen at creation: plain (default; name and "I have it", sorted by name) and collection (also the two optional years under OQ-6 and OQ-19; sorted by release year, then name). | LIST-02, ITEM-01, ITEM-02, ITEM-05 |

## 11. Open questions

For the owner to decide (the collaborator may advise). Nothing above depends on a guess about these. **Blocks** says
which next step needs the answer first; *later* means it blocks no design step. No open question blocks the app-flow
diagram (M0.5-02) any more.

| Id | Question | Stories | Blocks |
|---|---|---|---|
| OQ-15 | **Decided 2026-11-18 (issue #15 comment 6991933333), PLAN update in progress** (packing, trips and barcodes come after v1, M3 or later; a planner agent updates `docs/PLAN.md`). Earlier question: the plan (sections 1, 3, 3.1 and 7) still describes inventory items with notes, tags and barcodes, packing lists, trips, and lists that every member can read. Who updates the plan to match Q1-Q4 and private lists, and in which milestone do the packing and barcode features now belong? | all | waiting for the PLAN update PR |
| OQ-34 | Still open from the M1 test-project check: (a) for a `@gmail.com` address that already has a password account, does Firebase link Google to it, replace the password sign-in, or refuse? (b), (c), the non-Gmail case of (a) and (d) are decided: see section 10. In every case the app must not lose lists or create a second account, and its screens must not reveal whether an account exists (AUTH-10). | AUTH-01, AUTH-10 | M1 planning |

**Plan gaps for the next planner** (not decisions): the user's name (AUTH-12) is asked before a household exists, but
PLAN section 3 stores `displayName` only on the member document; the planner must say where the name lives without a
household, that the create and join batches copy it to the member document, and that an edit (wireframe 43) updates
both. Lists can exist without a household (OQ-1) and move with their
creator (OQ-5), but PLAN section 3 stores every list under a household. Lists need a creator and a sharing state, and new
security rules: the creator can do everything; members of the household a list is shared with can do everything except
stop the share or change the list's creator or household (OQ-2, OQ-3, OQ-4); today members can read everything under the household (PLAN section 3.1). These need
allow and deny tests and the `risk:high` tag, and change the M1 and M2 scope in PLAN section 7. PLAN section 3.1 deletes
everything under a deleted household, but shared lists must go back to their creators (OQ-17). There are no Cloud
Functions, so the planner must say who returns them: the security rules and each creator's own client (the creator makes
their own lists private again, the same way as VIS-04), not the household owner's client. The PLAN section 3 item
has no year fields; the v1 item needs a name, the check, and in a collection list two optional years (1900 to the
current year plus 50); the list's `kind` holds its type.
Sign-in (OQ-23 to OQ-27) adds to M1: the rules need an `email_verified` check (also for reading an invite) with allow
and deny tests, and the password, verification, reset and same-email flows are `risk:high`, in PRs split by concern.
