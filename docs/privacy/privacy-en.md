# Privacy in Tally

Status: working draft 2026-11-21; not owner-approved (see issue #15)

> **Draft for the owner to approve (task M1-O5, OQ-30).** Not approved, not legal advice, and not a claim that the
> app meets any law. Text in `[square brackets]` is a placeholder the owner fills in. The Danish text is
> `privacy-da.md`; both have the same sections.

## 1. Who is responsible

Tally is a small app for shared household lists, made by `[name of the person responsible]`. That person decides
what data the app collects and is responsible for it. Questions go to the contact in section 9.

## 2. What Tally stores about you

**Your account** (Firebase Authentication, run by Google):

- your email address;
- your password, if you sign up with email and password (only Google stores it; Tally's own database never holds
  it);
- if you sign in with Google: your Google account's identifier and the profile data Google shares at sign-in: your
  name, your email address and a link to your profile photo. The app does not show or use the photo.
  `[To confirm (M3-O3) with a real Google sign-in: on the Firebase Auth emulator (M1-67) the sign-in record keeps all
  of these and, for every sign-in method, also when the account was created, when you last signed in and when your
  sign-in was last renewed; M1-O5 decides whether this text names those times.]`
- if you turn on two-step verification: what is needed to check your authenticator app's codes;
- technical data that Google logs when you sign in, such as your IP address and the type of device or browser.

**Your data in the app** (Cloud Firestore, run by Google):

- the name you choose for yourself ("Your name"). Your household sees this name, never your email address;
- your household: its name, its members' names and roles, and invite links (each holds the household's name) until
  they are used or revoked, or cleaned up after they expire (an invite expires after 7 days);
- your lists and their items: names, "I have it", the years on collection lists, and who added or last changed
  an item and when.

**On your phone:** a copy of your lists so the app also works offline, and the name of your household. Both are
removed when you sign out or delete your account. The phone also keeps when you last opened each list on it, to
sort your lists; this never leaves the phone and is removed too when you sign out (signing out clears all of
Tally's data on the phone for your account). This also happens when Firebase signs you out by itself, which it does
the next time Tally is online on this phone after the account was deleted or its password changed on another phone.

Tally has no ads and **no analytics**: the app does not measure how you use it.

## 3. Who sees your data

- **You** see your own lists. A list is private until you share it with your household.
- **Your household** sees the lists you share with it, your name and whether you are the owner. It never sees your
  email address.
- **Google** runs the services above on behalf of Tally (as a "processor"): it stores and processes email
  addresses, passwords and list data so the app can work. The app sends your data to no other service.
- **The web host of `tally.bjarkebjarke.dk`** (`[host, once decided]`): invite links and the deletion page (section
  7) are web pages there. When you open one in a browser, the host sees the page address (for an invite, that
  includes the invite code) and your IP address.
- **The person responsible** (section 1): if you write to the contact (section 9) or ask for deletion without the
  app (section 7), they receive your email address and what you write. `[To confirm when the deletion page is
  decided.]`

## 4. Where your data is

- **Sign-in (Firebase Authentication)** is processed **in the USA**: Google runs this service only from data
  centres there.
- **Your lists and household (Cloud Firestore)** are stored **in the EU**, in Google's `eur3` location
  (Belgium and the Netherlands). Google may process the data outside the EU under its own terms.

## 5. Crash reports (only if you turn them on)

Crash reports are **off** until you turn on "Send crash reports" in Account. You can turn them off again at any time.

When they are on and the app crashes, a report goes to Google's Firebase Crashlytics. It holds, for example, what
went wrong in the app's code (the crash trace), the app version, the phone model and Android version, technical
details such as free memory and disk space and whether the phone is rooted, and random identifiers for the app
installation so that crashes from the same phone can be grouped. The app never sets a user id or custom keys in
the report, so it holds no name, email address or list contents. Google keeps crash reports for 90 days.

## 6. Checking the device (App Check)

To protect your data against scripts and tampered devices, the app checks with Google's **Play Integrity** that it
runs on a genuine Android device. It does not check the app itself. On each check, the app sends signals about the
device's integrity to Google, and Google answers with a token, valid for a limited time, that the app shows to
Firebase. Tally uses the result only for this check.

## 7. Deleting your account

**In the app:** open **Account** and choose **Delete account**. You may be asked to sign in again first.

- Your account, your name and every list you created (private and shared, with all their items) are deleted.
  Members of your household lose the lists you shared with them.
- If you are the owner of a household with other members, the app first asks you to hand over ownership. Nothing is
  deleted before that.
- If you are the last member, the household is deleted too.
- Items you added to other people's lists stay in those lists, and your name is removed from them.
  `[To confirm (M2, OQ-18): what happens to such items if you had already left the household before deleting
  your account.]`
- `[To confirm (M2, #205): a deleted household is kept as an empty record that still holds the random account ids of
  its creator and owner, and a random account id may also remain on other people's lists you last changed. Your own
  name and email address are not kept with these ids.]`
- `[To confirm (M1, #281): invites left under a deleted household may keep your random account id and the
  household's name.]`

**Without the app:** you can also ask for your account to be deleted on a web page at
`tally.bjarkebjarke.dk` `[address of the page, once decided]`.

Google deletes the remaining sign-in data on its side within 180 days and logged IP addresses after a few weeks.

## 8. Changes

This text may change. The current version is the one on this page.

## 9. Your rights and contact

*Not legal advice.* You can ask the person responsible for:

- **access**: to see what Tally holds about you;
- **correction**: to fix what is wrong (your name you can change yourself in Account);
- **deletion**: in the app or without it (section 7);
- and you can **complain** to the Danish data protection authority, Datatilsynet.

Why Tally handles your data: to provide the app you asked for (a contract), and, for crash reports, your consent
(the switch in Account, section 5).

Questions about your data or this text: `[contact]`.

_Draft of `[date]`._
