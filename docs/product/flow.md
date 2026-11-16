# Tally app flow (v1)

Task M0.5-02. Status: **draft for the owner's sign-off** (M0.5-O1; the collaborator comments, the owner decides).
Source: the [v1 user stories](stories.md) and the owner decisions they record (Q1-Q5, OQ-1 to OQ-6, OQ-17, OQ-19;
state issue #15). This document adds no product decision: every step names the story it comes from, and anything still
open is marked **OQ-n** as in [stories section 11](stories.md#11-open-questions). New questions this flow raised are in
[section 10](#10-new-open-questions).

## How to read this

* Each box or arrow names the story ids it comes from (`AUTH`, `HH`, `LIST`, `ITEM`, `VIS`, `SYNC`, `LANG`), so
  wireframes (M0.5-03) and later acceptance tests can trace back to [stories.md](stories.md).
* Words are the ones of [stories "How to read this"](stories.md#how-to-read-this): *user*, *household*,
  *household owner*, *list creator*, *private list*, *shared list*, *item*, "I have it".
* Screen names are working names for M0.5-03: **Sign-in**, **Lists** (all lists I can see, LIST-01), **Open list**
  (one list and its items, ITEM-05), **Household** (HH-04), **Join** (HH-03), **Account** (sign out, delete account,
  language if in the app: OQ-12).
* A dotted arrow is something that happens later, not a tap. A step marked OQ-n is not decided: the diagram shows
  where the answer plugs in, not the answer. A step marked **proposed** is the planner's recommended answer to an open
  question, drawn so the flow is complete; it changes if the owner decides otherwise.
* Every confirmation can be cancelled, and then nothing changes.
* "Needs a connection" means the step stops with a message when there is no network and leaves nothing half done
  (SYNC-03).

## 1. Screen map

```mermaid
flowchart TD
    start(["App opens"]) --> signed{"Signed in?<br>AUTH-02"}
    signed -- "no" --> signin["Sign-in<br>AUTH-01"]
    signed -- "yes, also offline" --> lists["Lists<br>LIST-01<br>most recently used first,<br>progress 12 of 30: OQ-8, OQ-9"]
    signin -- "Google account picked" --> lists
    link(["Invite link opened<br>HH-03"]) --> signed2{"Signed in?"}
    signed2 -- "no" --> signin2["Sign-in, then Join<br>AUTH-01, HH-03"]
    signed2 -- "yes" --> join["Join<br>HH-03"]
    signin2 --> join
    join --> lists
    lists -- "tap a list" --> open["Open list<br>ITEM-05, VIS-03"]
    lists -- "Create list" --> open
    lists --> household["Household<br>HH-01..06"]
    lists --> account["Account<br>AUTH-03, AUTH-04, LANG-02"]
    open -- "back" --> lists
    account -- "sign out or account deleted" --> signin
```

## 2. Sign-in, first use and account

There is no separate sign-up: the first Google sign-in creates the account (AUTH-01). A new user can make private lists
at once and needs no household (OQ-1, VIS-01).

```mermaid
flowchart TD
    open(["First start on this phone"]) --> si["Sign-in screen only<br>AUTH-01"]
    si -- "Sign in with Google" --> net{"Network?"}
    net -- "no" --> nonet["Message: first sign-in needs a connection<br>AUTH-01, SYNC-03"] --> si
    net -- "yes" --> picker["System account picker<br>AUTH-01"]
    picker -- "cancel" --> si
    picker -- "account picked" --> known{"Account already<br>has lists?"}
    known -- "no, new account" --> home["Lists, empty state with Create list<br>LIST-01"]
    known -- "yes, for example a new phone" --> mine["Lists with my lists<br>AUTH-01, LIST-01"]
    home -. "later starts, also offline" .-> home2["Lists without signing in again<br>AUTH-02"]
    acc["Account"] -- "Sign out" --> wipe["Local copy removed (assumed, OQ-13)<br>AUTH-03"] --> si
    acc -- "Delete account" --> owner{"Household owner<br>with other members?"}
    owner -- "yes" --> transfer["Guide: transfer ownership first, nothing deleted<br>AUTH-04, HH-06"]
    owner -- "no" --> confirm["Confirm: my lists, private and shared, are deleted<br>AUTH-04, OQ-5"]
    confirm -- "cancel" --> acc
    confirm -- "confirm" --> reauth{"Google wants a<br>recent sign-in?"}
    reauth -- "yes" --> again["Sign in again, then continue<br>AUTH-04"] --> gone
    reauth -- "no" --> gone["Account and my lists deleted; if I was the last member,<br>the household too (OQ-17)<br>AUTH-04"] --> si
```

## 3. Household

A household is needed only to share a list (OQ-1). One household per user (HH-01).

```mermaid
flowchart TD
    hh["Household screen"] --> inhh{"In a household?"}
    inhh -- "no" --> offer["Create household or wait for an invite link<br>HH-01, HH-03"]
    offer -- "name, confirm" --> valid{"Name empty<br>or only spaces?"}
    valid -- "yes" --> nameerr["Field error, nothing created<br>HH-01"] --> offer
    valid -- "no" --> created["Household exists; I am household owner and only member<br>HH-01"]
    inhh -- "yes" --> members["Members with display names, household owner marked<br>HH-04"]
    created --> members
    members -- "Invite" --> inv{"Network?"}
    inv -- "no" --> invnet["Message: needs a connection<br>SYNC-03"]
    inv -- "yes" --> share["Single-use link, valid 7 days; Android share sheet<br>HH-02"]
    members -- "Revoke invite (its creator or household owner)" --> revoked["Link no longer works<br>HH-02"]
    members -- "Leave (not household owner)" --> leave["Confirm: lists I created go with me, private;<br>members lose those I shared<br>HH-05, OQ-5"]
    leave -- "cancel" --> members
    leave -- "confirm" --> left["Not in a household; I no longer see others' shared lists;<br>my invites deleted<br>HH-05"]
    members -- "Remove member (household owner)" --> removed["Member loses others' shared lists, their open invites stop working;<br>their lists go with them<br>HH-06, OQ-5"]
    members -- "Transfer ownership (household owner)" --> moved["Other member is household owner; I am a plain member<br>HH-06"]
    members -- "Delete household (household owner)" --> delc["Confirm: shared lists go back to their creators;<br>cannot be restored<br>HH-06"]
    delc -- "cancel" --> members
    delc -- "confirm" --> deleted["No members; every shared list private to its creator again<br>HH-06, OQ-17"]
    deleted -. "creator's next app start" .-> notice["Notice: household deleted, my shared lists are private again<br>HH-06"]
```

Creating, inviting, joining, leaving, removing a member, transferring ownership and deleting the household need a
connection and show "This needs a connection" (OQ-22, decided 2026-11-16).

### Joining with an invite link

```mermaid
flowchart TD
    tap(["Invite link opened"]) --> installed{"App installed?"}
    installed -- "no" --> store["Web page: install the app, then tap the link again<br>OQ-21, host not decided"]
    installed -- "yes" --> auth{"Signed in?"}
    auth -- "no" --> si["Sign-in<br>AUTH-01"] --> net
    auth -- "yes" --> net{"Network?"}
    net -- "no" --> onet["Message: this needs a connection<br>OQ-22<br>HH-03, SYNC-03"]
    net -- "yes" --> check{"Link valid?"}
    check -- "expired, used or revoked" --> bad["Message saying so; joins nothing<br>HH-03"]
    check -- "valid" --> other{"Already in<br>another household?"}
    other -- "yes" --> leavefirst["Message: leave that household first<br>HH-03"]
    other -- "no" --> joinscr["Join screen shows the household name<br>HH-03"]
    joinscr -- "confirm, no network" --> jnet["Message: joining needs a connection<br>HH-03, SYNC-03"]
    joinscr -- "cancel" --> nojoin["Joins nothing"]
    joinscr -- "confirm" --> member["Member; Lists shows the household's shared lists<br>HH-03, VIS-02, OQ-16"]
```

## 4. Lists and private or shared

```mermaid
flowchart TD
    lists["Lists<br>LIST-01"] -- "Create list" --> name["Enter name"]
    name -- "confirm" --> nvalid{"Empty or<br>only spaces?"}
    nvalid -- "yes" --> nerr["Field error, no list<br>LIST-02"] --> name
    nvalid -- "no" --> newlist["Name trimmed; list is private and opens empty<br>LIST-02, VIS-01"]
    open["Open list"] -- "Rename (creator or shared with me)" --> rn{"New name empty?"}
    rn -- "yes" --> rnerr["Old name kept, field error<br>LIST-03"]
    rn -- "no" --> renamed["New name shown everywhere, also to members<br>LIST-03, OQ-3"]
    open -- "Delete (creator or shared with me)" --> del["Confirm first, naming the list and its number of items<br>LIST-04, OQ-10"]
    del -- "cancel" --> open
    del -- "confirm" --> dgone["List and items gone, also for members<br>LIST-04"] --> lists
    open -- "Share with household (creator, private list)" --> inhh{"In a household?"}
    inhh -- "no" --> hstep["Share is disabled with the message: you need a household to share<br>(household step after v1)<br>VIS-02, OQ-1, OQ-20"]
    inhh -- "yes" --> sconfirm["Confirm sharing this one list<br>VIS-02"]
    sconfirm -- "confirm" --> shared["Shared: every member sees it in Lists<br>VIS-02, VIS-03"]
    shared -- "Stop sharing (creator only)" --> stop["Confirm<br>VIS-04"]
    stop -- "cancel" --> shared
    stop -- "confirm" --> private["Private to the creator with all items; members lose it<br>VIS-04, OQ-2, OQ-4"]
```

What each person sees and may do on one list (VIS-01 to VIS-04; the server enforces the same, rules allow and deny
tests):

| Who | Private list | Shared list |
|---|---|---|
| List creator | everything | everything, including Stop sharing |
| Other member of the creator's household | not shown, server refuses | everything except Stop sharing and changing creator or household (OQ-2, OQ-3, VIS-04) |
| Anyone else | not shown, server refuses | not shown, server refuses |

## 5. Items

```mermaid
flowchart TD
    open["Open list<br>ITEM-05"] -- "Add item" --> input["Name, optional release year,<br>optional re-release year"]
    input -- "confirm" --> iname{"Name empty?"}
    iname -- "yes" --> noadd["No item added<br>ITEM-01"] --> input
    iname -- "no" --> years{"Each year set is a whole number<br>1900 to current year + 50?"}
    years -- "no" --> yerr["Year field error<br>ITEM-01, OQ-6"] --> input
    years -- "yes" --> added["Item added, not checked; input stays open<br>ITEM-01, OQ-19"]
    added --> input
    open -- "Edit item" --> edit["Change name or years, same rules<br>ITEM-02"]
    edit -- "name cleared" --> keep["Old name kept, error<br>ITEM-02"]
    edit -- "year cleared" --> noyear["Item has no such year<br>ITEM-02"]
    edit -- "valid" --> saved["Saved, shown to members too<br>ITEM-02"]
    open -- "Remove item" --> rem["Removed at once, Undo in a snackbar, no confirmation<br>ITEM-03, OQ-10"]
    rem -- "undo" --> open
    rem -- "not undone" --> rgone["Item gone<br>ITEM-03"]
    open -- "Tap checkbox" --> toggle["I have it: checked or unchecked, kept offline too<br>ITEM-04, OQ-7"]
```

Duplicate item names are still OQ-11. Decided 2026-11-16: items are sorted by release year, then name, and lists by
most recently used; a "show only missing" filter is in v1; no search and no manual order in v1 (OQ-8). Progress
("12 of 30") is small text under the list name in Lists and at the top of Open list (OQ-9).

## 6. Offline and sync

The user does nothing to sync (SYNC-01). While offline the app shows a small bar, "Offline: changes are sent when you are
online again", with the number of waiting changes (OQ-14, decided 2026-11-16).

```mermaid
stateDiagram-v2
    [*] --> Online
    Online --> Offline: network lost
    Offline --> Offline: create list, add, edit, remove, check (shown at once, SYNC-01)
    Offline --> Sending: network back
    Sending --> Online: changes saved, members get them (SYNC-01)
    Online --> Online: change from a member appears by itself (SYNC-02)
    Sending --> ItemGone: edited item was deleted meanwhile
    ItemGone --> Online: item stays deleted, short message (SYNC-02)
    Sending --> AccessLost: list deleted, unshared, left with its creator, household deleted, or I was removed
    Online --> AccessLost: same while the list is open
    AccessLost --> Online: leave the list, unsent edits dropped, short message (SYNC-02)
    note right of Offline
        Needs a connection, SYNC-03:
        first sign-in, join, create invite.
        Also every household and invite
        action (OQ-22). Offline bar: OQ-14.
    end note
```

Two members editing the same field: last write wins; different fields are both kept (SYNC-02).

```mermaid
sequenceDiagram
    participant A as Member A
    participant S as Firestore
    participant B as Member B
    A->>S: check item (SYNC-02)
    S-->>B: item checked, no refresh needed (SYNC-02)
    A->>S: rename item to X
    B->>S: rename same item to Y, a moment later
    S-->>A: Y, last write wins (SYNC-02)
    S-->>B: Y
```

## 7. Language

```mermaid
flowchart TD
    start(["App starts"]) --> picked{"Language picked for this app?<br>LANG-02"}
    picked -- "yes" --> use["Use it: English or Danish"]
    picked -- "no" --> phone{"Phone set to Danish?<br>LANG-01"}
    phone -- "yes" --> da["Danish, also plurals"]
    phone -- "no" --> en["English"]
    switch["Switch language: in the app or Android per-app setting, OQ-12"] --> back["Back in the app: every screen in the new language,<br>lists unchanged, no reinstall<br>LANG-02"]
    use --> names["List and item names shown as typed, never translated<br>LANG-01"]
    da --> names
    en --> names
```

## 8. Empty and error states

```mermaid
flowchart LR
    subgraph empty ["Empty states"]
        e1["Lists: explains lists, offers Create list<br>LIST-01"]
        e2["Open list: offers Add item<br>ITEM-05"]
        e3["Household, none yet: create one or use an invite link<br>HH-01, HH-03"]
    end
    subgraph field ["Field errors, nothing saved"]
        f1["Household name empty<br>HH-01"]
        f2["List name empty<br>LIST-02, LIST-03"]
        f3["Item name empty<br>ITEM-01, ITEM-02"]
        f4["Year outside 1900 to current year + 50<br>ITEM-01, OQ-6"]
    end
    subgraph msg ["Messages"]
        m1["Needs a connection<br>AUTH-01, HH-03, SYNC-03"]
        m2["Invite expired, used or revoked<br>HH-03"]
        m3["Leave your household first<br>HH-03"]
        m4["Item was removed by someone else<br>SYNC-02"]
        m5["List no longer available<br>SYNC-02"]
        m6["Household deleted, your lists are private again<br>HH-06"]
    end
```

No error is shown when the account picker is cancelled (AUTH-01). Danish text must fit on every screen (LANG-01) and
30 or more items must scroll with nothing cut off (ITEM-05).

## 9. Story coverage

Every v1 story appears in at least one diagram above. Each row lists every story id its section cites.

| Section | Stories |
|---|---|
| 1. Screen map | AUTH-01, AUTH-02, AUTH-03, AUTH-04, HH-01, HH-02, HH-03, HH-04, HH-05, HH-06, LIST-01, ITEM-05, VIS-03, LANG-02 |
| 2. Sign-in and account | AUTH-01, AUTH-02, AUTH-03, AUTH-04, HH-06, LIST-01, VIS-01, SYNC-03 |
| 3. Household | AUTH-01, HH-01, HH-02, HH-03, HH-04, HH-05, HH-06, VIS-02, SYNC-03 |
| 4. Lists and sharing | LIST-01, LIST-02, LIST-03, LIST-04, VIS-01, VIS-02, VIS-03, VIS-04 |
| 5. Items | ITEM-01, ITEM-02, ITEM-03, ITEM-04, ITEM-05 |
| 6. Offline and sync | SYNC-01, SYNC-02, SYNC-03 |
| 7. Language | LANG-01, LANG-02 |
| 8. Empty and error states | AUTH-01, HH-01, HH-03, HH-06, LIST-01, LIST-02, LIST-03, ITEM-01, ITEM-02, ITEM-05, SYNC-02, SYNC-03, LANG-01 |

OQ-8, OQ-9, OQ-10, OQ-14, OQ-20, OQ-21 and OQ-22 were decided by the owner on 2026-11-16 (issue #15) and are drawn
as decided; the wireframes (M0.5-03, [wireframes/](wireframes/wireframes.html)) follow them.

## 10. New open questions

All three were decided by the owner on 2026-11-16 (issue #15): OQ-20 differently from the recommendation (Share is
disabled with a message for a user without a household; the household step comes after v1), OQ-21 and OQ-22 as
recommended, with "This needs a connection" for household and invite actions and list and item changes still offline.
The table keeps the original questions as history.

Found while drawing the flow; for the owner to decide (the collaborator may advise). Ids continue the numbering of
[stories section 11](stories.md#11-open-questions).

| Id | Question | Recommendation (planner; the owner decides) | Stories | Blocks |
|---|---|---|---|---|
| OQ-20 | A user who is not in a household taps "Share with household": does the app show a household step (create one with a name, or join with a link) and then share, or create a household for them behind the scenes (OQ-1 leaves this to M1/M2)? | The household step, drawn in section 4 as *proposed*: HH-01 needs a name, a household made behind the scenes would need a made-up one, and the step tells the user who will see the list. | VIS-02, HH-01 | M0.5-03 (whether the household step is a screen), M1/M2 planning |
| OQ-21 | An invite link opened on a phone without the app: open the Play Store page and ask the person to open the link again after installing? (Firebase Dynamic Links is shut down and there are no Cloud Functions, so the link may not survive the install.) | Yes: the link's web page says "install Tally, then tap this link again" and links to the Play Store; no deferred link in v1. | HH-02, HH-03 | M1/M2 planning |
| OQ-22 | Besides first sign-in, joining and creating an invite (SYNC-03): do opening an invite link, leaving, removing a member, transferring ownership, deleting the household, sharing, stopping sharing and deleting the account also need a connection, or may some wait offline and be sent later? | All need a connection in v1, with the SYNC-03 message: they change who can see what, the invite and the household name are only on the server, and deleting the account may need a recent sign-in. Drawn as *proposed* for opening an invite link (section 3). | SYNC-03, HH-03, HH-05, HH-06, VIS-02, VIS-04, AUTH-04 | M1/M2 planning |
