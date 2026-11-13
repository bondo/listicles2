# Status picture (renderer and fetch)

Task M0.5-27 builds a picture of the project status for the README front page: milestone progress, the current task
chain, the owner queue (open PRs that are not drafts) and a BLOCKERS panel. It is delivered in two PRs. This one holds
the renderer and the fetcher with their tests; the second (publisher, workflow, README embed) is stacked on it and
completes this page.

## How it works
1. `scripts/status_fetch.py` reads the GitHub REST API with `GITHUB_TOKEN` (open PRs with draft, behind-main and CI
   state; issues labelled `owner-todo`, `needs-owner`, `blocked`, `follow-up`) into one JSON file. PRs from forks are
   dropped unless their author has Write-or-better, and so are issues by anyone without Write (OWNER, MEMBER or
   COLLABORATOR only): the question issue form (`.github/ISSUE_TEMPLATE/question.yml`) puts `needs-owner` on every issue
   an outsider opens, so a label alone proves nothing. Outsiders' open `needs-owner` questions are shown as a count
   ("Outside questions: N"), never with a title, and never feed task states. The workflow's own
   `publish` check run is ignored when judging CI, and an unknown merge state is retried once and then never shown as
   ready to merge.
2. `scripts/status_visual.py render` turns that JSON plus `docs/tasks.toml` into `status.svg` and a tiny `status.json`.
   It is offline and deterministic. Every title is stripped of control characters, clipped and XML-escaped.

Dark mode: the SVG follows the viewer's operating-system or browser colour scheme (`prefers-color-scheme` inside an
`<img>` cannot see GitHub's own theme setting). It has an opaque background in both schemes, so it stays readable on
a light or a dark GitHub page, but it may not match the page's theme.

## What counts as a blocker
- Tasks of the current milestone whose `depends_on` are not done.
- Open issues labelled `owner-todo` (with their age in days), `blocked` or `needs-owner`.
- Open, non-draft PRs whose CI passes and that are not behind `main` (waiting for the owner to merge).
