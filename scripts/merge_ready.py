#!/usr/bin/env python3
"""Deterministic pre-merge checks for the merge agent (issue 136), then a sha-pinned squash merge.

Usage: python3 -I scripts/merge_ready.py <N> <sha> <kind>
  kind: working-draft-docs | tasks-sync | dependabot   (the owner-authorized merge-agent kinds)

Refuses (exit 1, one reason per line, nothing merged) unless ALL hold:
  * the PR head is exactly <sha>;
  * mergeable_state is `clean` (so the branch is up to date and nothing blocks it);
  * every check the base branch's ruleset requires has a latest run with conclusion `success`
    (no required checks configured, or one missing or pending, is a refusal);
  * no closing keyword (close/closes/closed, fix/fixes/fixed, resolve/resolves/resolved) sits directly before an
    issue number or issue URL in the PR title, body or commit messages;
  * every changed file (a rename's old name too) is inside the kind's allowed paths. For dependabot, workflow files
    may change only `uses: owner/repo@<40-hex sha>` lines.
Otherwise it squash-merges with the REST API, passing <sha> so GitHub refuses if the head moved meanwhile.
Exit status: 0 merged, 1 refused or API error, 2 bad usage. REST only (`gh api`), never GraphQL.
"""

import json
import os
import re
import subprocess
import sys
import time

REPO = os.environ.get("GITHUB_REPOSITORY", "bondo/listicles2")
RETRIES = 5

DOC_PREFIXES = ("docs/product/", "docs/milestones/", "docs/reviews/", "design/")
DOC_FILES = ("docs/PLAN.md",)
TASKS_FILES = ("docs/tasks.toml",)
DEPENDABOT_FILES = (
    "firebase/package.json",
    "firebase/package-lock.json",
    "gradle/libs.versions.toml",
    "gradle/wrapper/gradle-wrapper.properties",
    "gradle/wrapper/gradle-wrapper.jar",
    "scripts/requirements-lint.txt",
)
WORKFLOW_RE = re.compile(r"^\.github/workflows/[\w.-]+\.ya?ml$")
PIN_LINE_RE = re.compile(r"^\s*(?:-\s+)?uses:\s*[\w.-]+/[\w./-]+@[0-9a-f]{40}\s*(?:#.*)?$")
CLOSING_RE = re.compile(
    r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\b[:\s]+(?:[\w.-]+/[\w.-]+#\d+|#\d+|https://github\.com/[\w.-]+/[\w.-]+/issues/\d+)",
    re.I,
)
SHA_RE = re.compile(r"[0-9a-f]{40}")


class ApiError(Exception):
    pass


class GhApi:
    """REST calls through `gh api` (retries 429/5xx flakes)."""

    def _gh(self, args):
        last = ""
        for attempt in range(RETRIES):
            res = subprocess.run(["gh", "api", *args], capture_output=True, text=True)
            if res.returncode == 0:
                return res.stdout
            last = (res.stderr or res.stdout).strip()
            if not re.search(r"\b(429|50[0-4])\b", last) or attempt == RETRIES - 1:
                break
            time.sleep(2**attempt)
        raise ApiError(f"gh api {args[-1]}: {last[:200] or 'failed'}")

    def get(self, path):
        return json.loads(self._gh(["-X", "GET", path]))

    def pages(self, path, key=None):
        out = []
        for page in json.loads(self._gh(["--paginate", "--slurp", "-X", "GET", f"{path}?per_page=100"])):
            out.extend(page[key] if key else page)
        return out

    def put(self, path, fields):
        args = ["-X", "PUT"]
        for k, v in fields.items():
            args += ["-f", f"{k}={v}"]
        return json.loads(self._gh([*args, path]))


def allowed(kind, name):
    """Whether a changed path belongs to the kind (workflow pins are judged on their patch, see pin_only)."""
    if ".." in name.split("/"):
        return False
    if kind == "working-draft-docs":
        return name in DOC_FILES or name.startswith(DOC_PREFIXES)
    if kind == "tasks-sync":
        return name in TASKS_FILES
    return name in DEPENDABOT_FILES or bool(WORKFLOW_RE.match(name))


def pin_only(patch):
    """True if every added or removed line of a diff is a `uses: owner/repo@<sha>` line."""
    changed = [ln for ln in patch.splitlines() if ln[:1] in "+-" and not ln.startswith(("+++", "---"))]
    return bool(changed) and all(PIN_LINE_RE.match(ln[1:]) for ln in changed)


def file_problems(kind, files):
    if not files:
        return ["no changed files"]
    problems = []
    for f in files:
        for name in (f["filename"], f.get("previous_filename")):
            if name and not allowed(kind, name):
                problems.append(f"path outside kind {kind}: {name}")
        name = f["filename"]
        if kind == "dependabot" and WORKFLOW_RE.match(name):
            patch = f.get("patch")
            if patch is None:
                problems.append(f"{name}: no patch from the API, cannot verify a version pin only")
            elif not pin_only(patch):
                problems.append(f"{name}: changes beyond `uses:` version pins")
    return problems


def check_problems(api, repo, base, sha):
    """Required checks (from the base branch ruleset) that lack a latest successful run on <sha>."""
    required = sorted(
        {
            c["context"]
            for rule in api.pages(f"repos/{repo}/rules/branches/{base}")
            if rule.get("type") == "required_status_checks"
            for c in rule.get("parameters", {}).get("required_status_checks", [])
        }
    )
    if not required:
        return [f"no required status checks found for branch {base}: cannot tell what must pass"]
    latest = {}
    for r in api.pages(f"repos/{repo}/commits/{sha}/check-runs", key="check_runs"):
        if r["name"] not in latest or (r.get("started_at") or "") >= (latest[r["name"]].get("started_at") or ""):
            latest[r["name"]] = r
    problems = []
    for name in required:
        r = latest.get(name)
        if r is None:
            problems.append(f"required check {name}: missing (no check run on {sha[:7]})")
        elif r.get("status") != "completed":
            problems.append(f"required check {name}: pending ({r.get('status')})")
        elif r.get("conclusion") != "success":
            problems.append(f"required check {name}: {r.get('conclusion')}")
    return problems


def evaluate(api, repo, n, sha, kind):
    """All reasons the PR must not be merged (empty means ready)."""
    pr = api.get(f"repos/{repo}/pulls/{n}")
    problems = []
    if pr["head"]["sha"] != sha:
        problems.append(f"head is {pr['head']['sha'][:7]}, not {sha[:7]}: the PR changed since it was reviewed")
    if pr.get("mergeable_state") != "clean":
        problems.append(f"mergeable_state is {pr.get('mergeable_state')}, not clean (behind, conflicting, blocked or checks not green)")
    texts = {"title": pr.get("title") or "", "body": pr.get("body") or ""}
    for i, c in enumerate(api.pages(f"repos/{repo}/pulls/{n}/commits")):
        texts[f"commit {i + 1}"] = c["commit"]["message"]
    for where, text in texts.items():
        m = CLOSING_RE.search(text)
        if m:
            problems.append(f"closing keyword in {where}: {m.group(0)!r} (rephrase, e.g. 'see issue N')")
    problems += file_problems(kind, api.pages(f"repos/{repo}/pulls/{n}/files"))
    problems += check_problems(api, repo, pr["base"]["ref"], sha)
    return problems


KINDS = {"working-draft-docs", "tasks-sync", "dependabot"}


def main(argv, api=None, out=sys.stdout, err=sys.stderr):
    if len(argv) != 3 or not argv[0].isdigit() or not SHA_RE.fullmatch(argv[1]):
        print("usage: merge_ready.py <N> <40-hex head sha> <kind>", file=err)
        return 2
    n, sha, kind = int(argv[0]), argv[1], argv[2]
    if kind not in KINDS:
        print(f"merge_ready: unknown kind {kind!r}; expected one of {', '.join(sorted(KINDS))}", file=err)
        return 2
    api = api or GhApi()
    try:
        problems = evaluate(api, REPO, n, sha, kind)
        if problems:
            for p in problems:
                print(f"merge_ready: refused PR {n}: {p}", file=err)
            return 1
        api.put(f"repos/{REPO}/pulls/{n}/merge", {"merge_method": "squash", "sha": sha})
    except ApiError as e:
        print(f"merge_ready: {e}", file=err)
        return 1
    print(f"merge_ready: squash-merged PR {n} at {sha[:7]} ({kind})", file=out)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
