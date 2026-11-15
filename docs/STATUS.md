# Status picture (README front page)

The README shows `status.svg`: one card per milestone with its human-friendly name (the id stays as a prefix, like
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
2. `scripts/status_visual.py render` turns that JSON plus `docs/tasks.toml` into `status.svg`, a tiny `status.json` and the detail page `status.md`.
   It is offline and deterministic. Every title is stripped of control characters, clipped and XML-escaped.
3. `scripts/status_publish.py` pushes the files to the `status` branch with a plain push (creates the orphan branch
   if missing, never force-pushes). It makes no commit when the SVG is unchanged apart from the "updated" stamp and the page is unchanged, so the
   stamp shows the time of the last change, not of the last check.

Runs: every 30 minutes, on `workflow_dispatch`, on `issues` events and on push to `main`. There is no `pull_request`
trigger (it would put a status check on every PR and give fork PRs a read-only token), so PR changes show up within
30 minutes. The job has `contents: write` plus read on pull requests, issues and checks, and nothing else.

Dark mode: the SVG follows the viewer's operating-system or browser colour scheme (`prefers-color-scheme` inside an
`<img>` cannot see GitHub's own theme setting). It has an opaque background in both schemes, so it stays readable on
a light or a dark GitHub page, but it may not match the page's theme.

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
