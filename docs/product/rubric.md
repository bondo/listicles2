# Tally visual-quality rubric (draft)

Status: working draft, merged as the baseline for M1; not owner-approved (open owner questions T1 palette, T2 text size, R1 reference apps; see issue #15).

Task M0.5-03. Status: **draft for the owner** (D-3.3): the owner edits and agrees it at D5 (M0.5-O1); the collaborator
comments, the owner decides. After that, changes go through R6. This file is the detailed form of
[docs/reviews/README.md section 4](../reviews/README.md#4-visual-quality-rubric), which stays the short summary and
keeps the pass bar.

## How to score

* Score each criterion **1 to 5 with a one-line reason**, per screen or per flow. Name the screen by its wireframe number
  (`01` to `33` in the M0.5-03 wireframes, docs/product/wireframes/wireframes.html, PR #113) or by its M1+ screen name.
* Look at **light and dark**, **English and Danish** (Roborazzi PNGs from M1, P14), and at least one list with **30 or more
  items**. Where a check needs font scale 200 %, say so in the reason.
* **Pass bar (D-3.4):** no criterion below 3 in the **owner's** scores. An agent score below 3 is a **minor** finding,
  never a blocker. Agent scores are advisory; taste stays with the owner. When an agent score disagrees with the owner's,
  record it as a calibration note for this rubric, not as a finding.
* Reference apps: the owner may name 2 or 3 at D5 ("feels like X"); they are compared with, never copied.
  *Not named yet.*

## Criteria

Each criterion has what a 5, a 3 and a 1 look like, and the Tally-specific checks an agent can make from screenshots.

### 1. Hierarchy

| 5 | 3 | 1 |
|---|---|---|
| The list name, the items and the one main action (Create list, Add item) stand out at once; secondary facts (progress, years, who shared it) are clearly quieter | The main action is findable but competes with other elements | No clear starting point; several things shout |

Checks: one filled or FAB action per screen at most; progress ("12 of 30") is small text under the name (OQ-9), not a
headline; destructive actions are text in the error colour, never the main button except in their own confirmation.

### 2. Spacing and alignment

| 5 | 3 | 1 |
|---|---|---|
| Only `spacing` tokens, a 16 dp side gutter, text columns line up across rows | Mostly tokens, one or two odd gaps | Random gaps, things floating or cramped |

Checks: every gap is a token value from [design/tokens.json](../../design/tokens.json); item text starts at the same x
in every row; touch targets at least `size.minTouchTarget` (48 dp), also the checkbox.

### 3. Colour

| 5 | 3 | 1 |
|---|---|---|
| Only token roles, each used for its meaning (primary = act, tertiary = offline, error = destroy or wrong); light and dark look like the same app | Tokens used, but a role is used for the wrong meaning or dark looks unfinished | Raw colours, poor contrast, dark mode broken |

Checks: every text/background pair is in `contrastPairs` and passes WCAG AA (the M1-04 test backs this); nothing relies
on colour alone (private/shared also has an icon and a word; checked has a tick).

### 4. Density

| 5 | 3 | 1 |
|---|---|---|
| A 30-item list scrolls calmly; about 8 to 10 items fit on a normal phone; nothing wasted, nothing crowded | Fits, but either sparse (few items per screen) or tight | Either 4 items per screen or rows touching |

Checks: item rows are at least `size.listRowMin` and grow for long names instead of cutting them; the FAB does not hide
the last item (bottom padding); the offline bar takes one or two lines, not more.

### 5. Typography

| 5 | 3 | 1 |
|---|---|---|
| Only the token type scale; easy to read; English and Danish both fit with no truncation, also at 200 % font scale | Readable, one truncation or one off-scale size | Several sizes off scale, text cut off |

Checks: no ellipsis on item names, years, list names or buttons in either language (LANG-01, ITEM-05); Danish compounds
("Genudgivelsesår", "Husstandens ejer") fit in labels and menus.

### 6. Consistency

| 5 | 3 | 1 |
|---|---|---|
| The same thing looks and behaves the same everywhere | One pattern differs between screens | Each screen invents its own |

Checks: one snackbar pattern for undo and short messages (09, SYNC-02); one dialog pattern for confirmations (11, 12,
19, 20); one message for "This needs a connection" (01, 16, 24, 33); private/shared shown the same in Lists and Open list.

### 7. Polish and delight

| 5 | 3 | 1 |
|---|---|---|
| Empty states explain and offer the next step; undo and transitions feel cared for; small details (plurals, quotes, dates) are right in both languages | Empty states exist but are bare | Blank screens, raw errors, wrong plurals |

Checks: empty states for Lists, Open list and Household (02, 13, 14); Danish quotes »…« and English "…"; plurals from
`<plurals>`. Motion and touch feel cannot be judged from screenshots: owner only (R10).

## What an agent can and cannot judge

From [docs/reviews/README.md section 4](../reviews/README.md#4-visual-quality-rubric): agents can judge alignment and
spacing against the tokens, hierarchy and contrast, truncation and overflow, light/dark parity, consistency across
screens, differences from the wireframes, unfinished states. They cannot judge motion, touch feel, real-device size and
density, felt speed, or taste.

## Score sheet template

| Screen | Hierarchy | Spacing | Colour | Density | Typography | Consistency | Polish | Notes |
|---|---|---|---|---|---|---|---|---|
| 05 Open list | 4: ... | | | | | | | |
