# Tally

Shared household lists for Android. See docs/PLAN.md for the plan. Run `scripts/verify.sh` to check your changes.

## Status

![Project status: milestone progress, current tasks, owner queue and blockers](https://raw.githubusercontent.com/bondo/tally/status/status.svg)

![Open tasks and their dependencies: one band per milestone, an arrow from each dependency to the task that waits on it, coloured by state](https://raw.githubusercontent.com/bondo/tally/status/status-graph.svg)

Each milestone is a card with its name (like "M0.5 Product design and guardrails"), a progress bar and its open tasks,
with what each one waits on; blockers and the owner queue are at the bottom. The full detail (every task with its
dependencies, owner and PR, plus a dependency graph per milestone) is on [the status detail page](https://github.com/bondo/tally/blob/status/status.md). Updated by a workflow every 30 minutes and
when issues change or `main` is pushed; how it works and what the markers mean: docs/STATUS.md.

The second picture is the dependency graph of the tasks that are not done: arrows run from a dependency to the task
that waits on it, transitive arrows are left out, and each milestone band says how many of its tasks are done.

## Debug APK

Pushes to `main` (a newer push can cancel an older run) upload the debug APK that CI builds as an Actions artifact named `tally-debug-<short sha>`, kept for 30 days:
open the CI run for the commit on the Actions tab and download it under Artifacts (the file is a zip with one `.apk`).
The newest one: [successful CI runs of pushes to `main`](https://github.com/bondo/tally/actions/workflows/ci.yml?query=branch%3Amain+event%3Apush+is%3Asuccess), newest on top; open the top run and download `tally-debug-<short sha>` under Artifacts (a GitHub login is needed).
It carries the `demo-tally` stand-in Firebase config (M1-30), so it installs and shows the UI but cannot reach the real Firebase project.
Install it on your own device only: installs by anyone else wait for M1-O5 (#291). Pull requests do not publish an APK.
