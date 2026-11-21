# Privacy in Tally

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
- if you sign in with Google: your Google account's identifier and the name Google shares at sign-in;
- if you turn on two-step verification: what is needed to check your authenticator app's codes;
- technical data that Google logs when you sign in, such as your IP address and the type of device or browser.

**Your data in the app** (Cloud Firestore, run by Google):

- the name you choose for yourself ("Your name"). Your household sees this name, never your email address;
- your household: its name, its members' names and roles, and invite links that have not been used or have
  not expired yet (an invite expires after 7 days);
- your lists and their items: names, "I have it", the years on collection lists, and who added or last changed
  an item and when.

**On your phone:** a copy of your lists so the app also works offline, and the name of your household. Both are
removed when you sign out or delete your account.

Tally has no ads and **no analytics**: the app does not measure how you use it.

## 3. Who sees your data

- **You** see your own lists. A list is private until you share it with your household.
- **Your household** sees the lists you share with it, your name and whether you are the owner. It never sees your
  email address.
- **Google** runs the services above on behalf of Tally (as a "processor"): it stores and processes email
  addresses, passwords and list data so the app can work. Tally sends your data to no other service.

## 4. Where your data is

- **Sign-in (Firebase Authentication)** is processed **in the USA**: Google runs this service only from data
  centres there.
- **Your lists and household (Cloud Firestore)** are stored **in the EU**, in Google's `eur3` location
  (Belgium and the Netherlands).

## 5. Crash reports (only if you turn them on)

Crash reports are **off** until you turn on "Send crash reports" in Account. You can turn them off again at any time.

When it is on and the app crashes, a report goes to Google's Firebase Crashlytics. It holds what went wrong in the
app's code (the crash trace), the app version, the phone model and Android version, and random identifiers for the
app installation so that crashes from the same phone can be grouped. `[To confirm (M1-25): the report holds no name,
email address or list contents.]` Google keeps crash reports for 90 days.

## 6. Checking that the app is genuine (App Check)

To protect your data against fake apps and scripts, the app checks with Google's **Play Integrity** that it runs
unchanged on a genuine Android device. On each check, the app sends signals about the device's integrity to Google,
and Google answers with a token, valid for a limited time, that the app shows to Firebase. Tally uses the result only for this
check.

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

**Without the app:** you can also ask for your account to be deleted on a web page at
`tally.bjarkebjarke.dk` `[address of the page, once decided]`.

Google deletes the remaining sign-in data on its side within 180 days and logged IP addresses after a few weeks.

## 8. Changes

If this text changes in a way that matters to you, the new version will say so at the top, with its date.

## 9. Contact

Questions about your data or this text: `[contact]`.

_Draft of `[date]`._
