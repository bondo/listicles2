#!/usr/bin/env python3
"""Deterministic pre-merge checks for the merge agent (issue 136), then a sha-pinned squash merge.

Usage: python3 -I scripts/merge_ready.py <N> <sha> <kind>
  kind: working-draft-docs | tasks-sync | dependabot   (the owner-authorized merge-agent kinds)

Refuses (exit 1, one reason per line, nothing merged) unless ALL hold:
  * the PR head is exactly <sha>;
  * mergeable_state is `clean` (so the branch is up to date and nothing blocks it);
  * every check the base ruleset requires has a latest run with conclusion `success` (none configured, missing or pending: refused);
  * no closing keyword (close/fix/resolve and their -s/-d forms) sits directly before an issue number or URL in the title, body or commits;
  * the base is `main` and the API's file and commit lists are complete (it caps them at 3000 and 250);
  * every changed file (a rename's old name too) is inside the kind's allowed paths. For dependabot, a workflow may only
    re-pin the same actions (nothing added or removed) and gradle-wrapper.properties only a services.gradle.org version.
Otherwise it squash-merges via REST with <sha> pinned (GitHub refuses if the head moved) and the checked title and body as commit text.
Exit status: 0 merged, 1 refused or API error, 2 bad usage. REST only (`gh api`), never GraphQL.
"""

import json
import os
import re
import subprocess
import sys
import time

REPO = os.environ.get("GITHUB_REPOSITORY", "bondo/listicles2")
BASE = "main"
RETRIES = 5

DOC_PREFIXES = ("docs/product/", "docs/milestones/", "docs/reviews/", "design/")
DOC_FILES = ("docs/PLAN.md",)
TASKS_FILES = ("docs/tasks.toml",)
# Only files whose content this script checks (workflow pins, wrapper properties) or CI validates (the wrapper jar). npm, gradle catalog and
# pip manifests carry runnable or fetchable content (scripts, URLs), so those Dependabot PRs go to the owner (R2-01).
DEPENDABOT_FILES = ("gradle/wrapper/gradle-wrapper.properties", "gradle/wrapper/gradle-wrapper.jar")
WORKFLOW_RE = re.compile(r"^\.github/workflows/[\w.-]+\.ya?ml$")
WRAPPER_PROPS = "gradle/wrapper/gradle-wrapper.properties"
PIN_LINE_RE = re.compile(r"^(\s*(?:-\s+)?uses:\s*[\w.-]+/[\w./-]+)@[0-9a-f]{40}\s*(?:#.*)?$")
WRAPPER_LINE_RE = re.compile(
    r"^(?:distributionUrl=https\\://services\.gradle\.org/distributions/gradle-[\w.-]+-(?:bin|all)\.zip|distributionSha256Sum=[0-9a-f]{64})$"
)
CLOSING_RE = re.compile(
    r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\b[:\s]+(?:[\w.-]+/[\w.-]+#\d+|#\d+|https?://(?:www\.)?github\.com/[\w.-]+/[\w.-]+/issues/\d+)",
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


def _changed_lines(patch):
    """The (removed, added) lines of each change block of a diff, without the +/- marker."""
    hunks, removed, added = [], [], []
    for ln in patch.splitlines():
        if ln.startswith("@@") or ln[:1] == " ":  # a hunk header or a context line ends a change block
            hunks.append((removed, added))
            removed, added = [], []
        elif ln[:1] == "-":
            removed.append(ln[1:])
        elif ln[:1] == "+":
            added.append(ln[1:])
    return [*hunks, (removed, added)]


def pin_only(patch):
    """True if the diff only re-pins actions: in each change block the removed and added `uses:` lines pair up one to one with the same
    indentation and owner/repo[/path]; only the sha and trailing comment may differ. An added or removed step fails."""
    hunks = _changed_lines(patch)
    for removed, added in hunks:
        pairs = [(PIN_LINE_RE.match(a), PIN_LINE_RE.match(b)) for a, b in zip(removed, added, strict=False)]
        if len(removed) != len(added) or any(not (a and b and a.group(1) == b.group(1)) for a, b in pairs):
            return False
    return any(removed for removed, _ in hunks)


def wrapper_only(patch):
    """True if every changed line is a services.gradle.org distributionUrl or a distributionSha256Sum."""
    lines = [ln for removed, added in _changed_lines(patch) for ln in (*removed, *added)]
    return bool(lines) and all(WRAPPER_LINE_RE.match(ln) for ln in lines)


def file_problems(kind, files):
    if not files:
        return ["no changed files"]
    problems = []
    for f in files:
        for name in (f["filename"], f.get("previous_filename")):
            if name and not allowed(kind, name):
                problems.append(f"path outside kind {kind}: {name}")
        name = f["filename"]
        check = pin_only if WORKFLOW_RE.match(name) else wrapper_only if name == WRAPPER_PROPS else None
        if kind == "dependabot" and check:
            patch = f.get("patch")
            if patch is None:
                problems.append(f"{name}: no patch from the API, cannot verify a version bump only")
            elif not check(patch):
                problems.append(f"{name}: changes beyond a version bump (re-pinned `uses:` lines, services.gradle.org distribution)")
    return problems


def check_problems(api, repo, base, sha):
    """Required checks (from the base branch ruleset) that lack a latest successful run on <sha>."""
    required = sorted(
        {
            (c["context"], c.get("integration_id"))
            for rule in api.pages(f"repos/{repo}/rules/branches/{base}")
            if rule.get("type") == "required_status_checks"
            for c in rule.get("parameters", {}).get("required_status_checks", [])
        },
        key=str,
    )
    if not required:
        return [f"no required status checks found for branch {base}: cannot tell what must pass"]
    runs = api.pages(f"repos/{repo}/commits/{sha}/check-runs", key="check_runs")
    problems = []
    for name, app_id in required:
        # the latest run (highest id, so a queued re-run counts) from the app the ruleset names, if it names one
        r = max((r for r in runs if r["name"] == name and app_id in (None, r.get("app", {}).get("id"))), key=lambda r: r["id"], default=None)
        if r is None:
            problems.append(f"required check {name}: missing (no check run on {sha[:7]})")
        elif r.get("status") != "completed":
            problems.append(f"required check {name}: pending ({r.get('status')})")
        elif r.get("conclusion") != "success":
            problems.append(f"required check {name}: {r.get('conclusion')}")
    return problems


def evaluate(api, repo, n, sha, kind):
    """(the PR, all reasons it must not be merged); no reasons means ready."""
    pr = api.get(f"repos/{repo}/pulls/{n}")
    problems = []
    if pr["base"]["ref"] != BASE:
        problems.append(f"base is {pr['base']['ref']}, not {BASE}")
    if pr["head"]["sha"] != sha:
        problems.append(f"head is {pr['head']['sha'][:7]}, not {sha[:7]}: the PR changed since it was reviewed")
    if pr.get("mergeable_state") != "clean":
        problems.append(f"mergeable_state is {pr.get('mergeable_state')}, not clean (behind, conflicting, blocked or checks not green)")
    texts = {"title": pr.get("title") or "", "body": pr.get("body") or ""}
    commits, files = api.pages(f"repos/{repo}/pulls/{n}/commits"), api.pages(f"repos/{repo}/pulls/{n}/files")
    for what, got, field in (("commits", commits, "commits"), ("files", files, "changed_files")):
        if len(got) != pr.get(field):
            problems.append(f"the API listed {len(got)} {what} but the PR has {pr.get(field)}: list truncated, cannot check them all")
    for i, c in enumerate(commits):
        texts[f"commit {i + 1}"] = c["commit"]["message"]
    for where, text in texts.items():
        m = CLOSING_RE.search(text)
        if m:
            problems.append(f"closing keyword in {where}: {m.group(0)!r} (rephrase, e.g. 'see issue N')")
    problems += file_problems(kind, files)
    problems += check_problems(api, repo, pr["base"]["ref"], sha)
    return pr, problems


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
        pr, problems = evaluate(api, REPO, n, sha, kind)
        if problems:
            for p in problems:
                print(f"merge_ready: refused PR {n}: {p}", file=err)
            return 1
        text = {"commit_title": f"{pr['title']} (#{n})", "commit_message": pr.get("body") or ""}  # the text checked above
        api.put(f"repos/{REPO}/pulls/{n}/merge", {"merge_method": "squash", "sha": sha, **text})
    except ApiError as e:
        print(f"merge_ready: {e}", file=err)
        return 1
    print(f"merge_ready: squash-merged PR {n} at {sha[:7]} ({kind})", file=out)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
