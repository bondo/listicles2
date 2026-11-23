# Status picture (README front page)

The README shows two pictures: `status.svg` (below) and, under it, `status-graph.svg`, the dependency graph of the open
tasks (section "Dependency graph" below).

The first picture is `status.svg`: one card per milestone with its human-friendly name (the id stays as a prefix, like
"M0.5 Product design and guardrails"), purpose, progress bar and done/total, then the milestone's open tasks, the owner
queue (open PRs that are not drafts) and a BLOCKERS panel. It is not stored on `main`: the workflow `.github/workflows/status.yml`
renders it and pushes it to the `status` branch (task M0.5-27). The README embeds the raw file from that branch.

## How it works
1. `scripts/status_fetch.py` reads the GitHub REST API with `GITHUB_TOKEN` (open PRs with draft, behind-main and CI
   state; issues labelled `owner-todo`, `needs-owner`, `blocked`, `follow-up`) into one JSON file. PRs from forks are
   dropped unless their author has Write-or-better, and so are issues by anyone without Write (OWNER, MEMBER or
   COLLABORATOR only): the question issue form (`.github/ISSUE_TEMPLATE/question.yml`) puts `needs-owner` on every issue
   an outsider opens, so a label alone proves nothing. Outsiders' open `needs-owner` questions are shown as a count
   ("Outside questions: N"), never with a title, and never feed task states. The workflow's own
   `publish` check run is ignored when judging CI, and an unknown merge state is retried once and then never shown as
   ready to merge.
2. `scripts/status_visual.py render` turns that JSON plus `docs/tasks.toml` into `status.svg`, a tiny `status.json`, the detail page `status.md` and the graph `status-graph.svg`.
   It is offline and deterministic. Every title is stripped of control characters, clipped and XML-escaped.
3. `scripts/status_publish.py` pushes the files to the `status` branch with a plain push (creates the orphan branch
   if missing, never force-pushes). It makes no commit when the SVG is unchanged apart from the "updated" stamp and the page and the graph are unchanged, so the
   stamp shows the time of the last change, not of the last check.

Runs: every 30 minutes, on `workflow_dispatch`, on `issues` events and on push to `main`. There is no `pull_request`
trigger (it would put a status check on every PR and give fork PRs a read-only token), so PR changes show up within
30 minutes. The job has `contents: write` plus read on pull requests, issues and checks, and nothing else.

Dark mode: the SVG follows the viewer's operating-system or browser colour scheme (`prefers-color-scheme` inside an
`<img>` cannot see GitHub's own theme setting). It has an opaque background in both schemes, so it stays readable on
a light or a dark GitHub page, but it may not match the page's theme.

## Dependency graph (`status-graph.svg`)
A directed graph of every task that is not done, from the same model as `status.svg` (`scripts/status_graph.py`, task M1-70).
It is written next to the SVG by `status_visual.py render` (`--graph` overrides the path) and published to the `status` branch by
`status_publish.py` next to `status.svg`, so the workflow needs no change. The README embeds it under the status picture.
- **Nodes** are open tasks only; done and dropped tasks are not drawn. A node shows the task id (the full title is a tooltip when the SVG is
  opened on its own, not inside the README, and the detail page has every title). Nodes sit in one band per milestone that has open tasks; the band label says how many of that
  milestone's tasks are done, like "M1 Accounts and households: 35/78 done, 43 open". Milestones that are all done, or not planned
  yet, have no band and are named in a line under the title.
- **Colour and shape** are the derived state, the same markers as the status picture: green circle = ready, blue triangle = in
  progress (an open PR names the task), yellow square = blocked (unmet dependencies or a `blocked` label), red diamond = owner to-do.
  There is no separate "claimed" state: no data source tells the renderer about a claim, so a claimed task shows as ready.
- **Arrows** go from a dependency to the task that depends on it, between open tasks only. Transitive arrows are removed (the
  transitive reduction): A to C is not drawn when A to B to C exists, so what you see is the shortest set of arrows with the same
  meaning. The legend says so and counts what is hidden.
- **Not drawn**: a dependency on a done or dropped task (no node to point from), and a `milestone:Mx` dependency ("all of Mx", which
  has no single node). The legend counts both (like "80 dependencies on done or dropped tasks, 2 on whole milestones").
- **Layout** is a deterministic layered layout in plain Python (no layout tool, no network): a task's column is the length of its
  longest chain of open dependencies, so arrows run left to right. Inside a column the boxes are ordered by a few barycentre
  sweeps (task M1-75), so connected tasks sit near each other; the order with the fewest crossings (counted as straight lines between the boxes' column and row, not on the routed arrows)
  wins, and it is never worse than the order in `docs/tasks.toml`. A task sits level with its dependencies where it can, so a chain is one straight line.
- **Arrow routing** (task M1-75): arrows are straight horizontal and vertical pieces that run in the gaps between columns and the
  channels between rows, never through a box. A short arrow (to the next column) leaves its source, runs along a track in the gap and
  arrives; a long one also runs along a track in the channel beside its source row. Arrows that share a gap or channel get tracks 4 px
  apart, and the gaps grow to hold them; arrows on one side of a box leave and arrive at different heights (up to 8 bent arrows per side; with more, heights repeat and arrows run along one line). The same input gives
  the same bytes, and there is no clock in the picture, so the publisher compares it byte for byte and commits only when the graph
  really changed.
- **Colours and the critical path** (task M1-76): the arrows of one source task share one colour, and so does their arrowhead. The colours are
  the Okabe-Ito palette (Okabe and Ito, "Color Universal Design", 2008) without black and yellow: orange, sky blue, bluish green, blue,
  vermillion, reddish purple. A test simulates protan, deutan and tritan vision and requires every pair to stay apart. Sources whose arrows
  run within 6 px of each other (side by side or crossing) get different colours where six colours allow it; far-apart sources may share one.
  The critical path, the longest chain of open tasks to M1-FU (smallest ids from the start on a tie), is drawn 3 px wide with a bigger
  arrowhead, the other arrows 1.2 px; the legend says so. Limit: orange and sky blue are only about 2:1 against the light band (the
  palette keeps its published values, because darker shades merge for deutan viewers); the colour is a second signal, the arrows are always drawn.
- **Size**: the picture grows with the longest chain of open tasks (one column each) and with the arrow tracks in the gaps. GitHub
  scales it to the README column (about 830 px), so the text is drawn large enough (14 px) to stay at 9 px or more after scaling:
  the width is held to 1290 px by squeezing the tracks in the gaps (4 px apart down to 1 px) and is tested for a 13-column chain and
  for 12 columns of 4 tasks with 3 arrows each, with 6-character ids. A chain of more than about 14 columns is wider than that and its text
  falls below 9 px; click the image to open it at full size.
- Light and dark mode and contrast follow the status picture (theme classes only, text contrast at least 4.5:1 on every node fill,
  checked by `scripts/test_status_graph.py`).

## Milestone names and what a card shows
Names and one-line purposes are data: one `[[milestone]]` table per milestone in `docs/tasks.toml` (`id`, `title` up to
40 characters, `purpose` up to 110). `scripts/tasks.py validate` fails when a milestone has no table, a table names an
unknown milestone, or a title or purpose is missing, empty or too long. The first names were derived from `docs/PLAN.md`
section 7; edit them in `docs/tasks.toml` (a normal PR). A milestone with no tasks yet shows its planned name and
"not planned yet".

Inside a card, finished tasks (done or dropped) collapse into "N done". Open tasks are listed in `tasks.toml` order, at
most 12 per card ("+N more open tasks" after that), each with a marker shape and a status word, so colour is never the
only signal. Markers: circle = ready (all dependencies met), triangle = in progress (an open PR, draft or not, is titled
`<task id>: ...`), square = blocked (unmet dependencies, or an open `blocked`-labelled issue or PR titled the same way),
diamond = owner to-do (it may also wait on other tasks), tick = N done.

Under an open task a line says what it waits on: unmet `depends_on` ids, `(owner)` after an owner-only task, "all of Mx"
for a `milestone:Mx` dependency, and "blocked by #N" for a labelled issue or PR. Lines about owner-only or labelled
blockers are red; ordinary waits are grey. The images use theme classes only (light and dark, contrast at least 4.5:1,
checked by a test).

## Detail page (`status.md`)
The same render also writes `status.md` next to the SVG, and the publisher pushes it to the `status` branch with the SVG
(the workflow needs no change: `status_visual.py render` writes it beside `--svg`, and `status_publish.py` picks up a
`status.md` beside `--svg`; `--md` overrides both). The README links it. Per milestone it has the name and purpose, a table
of every task (id, title, status, depends on, who, PR), a Mermaid graph of the open tasks with an arrow from what a task
waits on to the task (GitHub renders it; dashed grey boxes are outside the milestone), and at the end every blocker, not
only the first 14 of the picture. It carries no clock or ages, so it is rewritten only when something changes. All titles
are clipped, stripped of control characters and escaped for table cells and quoted Mermaid labels. Links to PRs and issues
use `$GITHUB_REPOSITORY` (or `--repo OWNER/NAME`); without a valid value the numbers are plain text.

## What counts as a blocker
- Tasks of the current milestone whose `depends_on` are not done.
- Open issues labelled `owner-todo` (with their age in days), `blocked` or `needs-owner`.
- Open, non-draft PRs whose CI passes and that are not behind `main` (waiting for the owner to merge).

## Live test (only possible after the merge)
Actions > status > Run workflow (branch `main`). The run should end with `created` (first time) or `updated`/`unchanged`.
Then open `https://raw.githubusercontent.com/bondo/listicles2/status/status.svg` and the repository front page.
The README image is served through GitHub's image proxy, so it can lag a few minutes behind the branch.
