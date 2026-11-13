# Status picture (README front page)

The README shows `status.svg`, a picture of the milestone progress, the current task chain, the owner queue (open PRs
that are not drafts) and a BLOCKERS panel. It is not stored on `main`: the workflow `.github/workflows/status.yml`
renders it and pushes it to the `status` branch (task M0.5-27). The README embeds the raw file from that branch.

## How it works
1. `scripts/status_fetch.py` reads the GitHub REST API with `GITHUB_TOKEN` (open PRs with draft, behind-main and CI
   state; issues labelled `owner-todo`, `needs-owner`, `blocked`, `follow-up`) into one JSON file.
2. `scripts/status_visual.py render` turns that JSON plus `docs/tasks.toml` into `status.svg` and a tiny `status.json`.
   It is offline and deterministic. Every title is stripped of control characters, clipped and XML-escaped.
3. `scripts/status_publish.py` pushes both files to the `status` branch with a plain push (creates the orphan branch
   if missing, never force-pushes). It makes no commit when the SVG is unchanged apart from the "updated" stamp, so the
   stamp shows the time of the last change, not of the last check.

Runs: every 30 minutes, on `workflow_dispatch`, on `pull_request` and `issues` events from this repository, and on push to
`main`. The job has `contents: write` and nothing else; fork and Dependabot pull requests are skipped.

## What counts as a blocker
- Tasks of the current milestone whose `depends_on` are not done.
- Open issues labelled `owner-todo` (with their age in days), `blocked` or `needs-owner`.
- Open, non-draft PRs whose CI passes and that are not behind `main` (waiting for the owner to merge).

## Live test (only possible after the merge)
Actions > status > Run workflow (branch `main`). The run should end with `created` (first time) or `updated`/`unchanged`.
Then open `https://raw.githubusercontent.com/bondo/listicles2/status/status.svg` and the repository front page.
The README image is served through GitHub's image proxy, so it can lag a few minutes behind the branch.
