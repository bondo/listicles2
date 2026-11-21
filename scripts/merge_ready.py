#!/usr/bin/env python3
"""Deterministic pre-merge checks for the merge agent (issue 136), then a sha-pinned squash merge.

Usage: python3 -I scripts/merge_ready.py <N> <sha> <kind>
  kind: working-draft-docs | tasks-sync | dependabot   (the owner-authorized merge-agent kinds)
        general      a PR whose every path is on the allowlist (GENERAL_ALLOW), under the owner's standing authorization (#15 comment 7005366747);
                     fail-closed since #15 comment 7058755858: any other path is owner-only

Refuses (exit 1, one reason per line, nothing merged) unless ALL hold:
  * the PR head is exactly <sha>;
  * mergeable_state is `clean` (so the branch is up to date and nothing blocks it);
  * every check the base ruleset requires has a latest run with conclusion `success` (none configured, missing or pending: refused);
  * no closing keyword (close/fix/resolve and their -s/-d forms) sits directly before an issue number or URL in the title, body or commits;
  * the base is `main` and the API's file and commit lists are complete (it caps them at 3000 and 250);
  * every changed file (a rename's old name too) is inside the kind's allowed paths (general: only the allowlist, see owner_only).
    For dependabot, a workflow may only
    re-pin the same actions (nothing added or removed) and gradle-wrapper.properties only a services.gradle.org version;
  * for dependabot, every new `uses: owner/repo@<sha> # <tag>` pin has a tag comment and its sha equals the commit that tag points to
    in owner/repo (`git ls-remote`, annotated tags dereferenced; R2-06, an imposter or fork commit is refused). A failed lookup refuses (fail closed).
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

# An explicit list of working drafts (R3-01): naming, docs/reviews/ and other owner-decided or gate docs are owner-only. A new draft needs an owner merge here.
DOC_PREFIXES = ("docs/milestones/", "docs/product/wireframes/")
DOC_FILES = ("docs/PLAN.md", "docs/product/stories.md", "docs/product/flow.md", "docs/product/rubric.md", "design/tokens.json")
DRAFT_STATUS = "not owner-approved"
TASKS_FILES = ("docs/tasks.toml",)
# Kind `general` is fail-closed (owner decision #15 7058755858, replacing ruling 1 of 7019683156): only GENERAL_ALLOW paths may merge as general, and
# these explicit lists, compared casefolded, stay as a second layer inside it: the protected process files (the list of
# scripts/hooks/pretooluse_guard.py PROTECTED, which a test keeps in sync), the wrappers by name anywhere, gate docs and approved product and design docs,
# dependency manifests, licence acceptances, canonical process docs and gradlew.
OWNER_ONLY_FILES = {f.casefold() for f in (
    "CLAUDE.md", "REVIEW.md", "scripts/guards.sh", "scripts/install-hooks.sh", "scripts/install_linters.sh", "scripts/linters.pins", "scripts/merge_ready.py",
    "scripts/test_merge_ready.py", "scripts/mark-ready.sh", "docs/ORCHESTRATION.md", "docs/BRANCH-PROTECTION.md", "docs/ANDROID-BEST-PRACTICES.md",
    "docs/FOLLOW-UPS.md", "docs/SECURITY.md", "docs/orchestrator-state.md", "gradle/verification-metadata.xml", "gradlew", "gradlew.bat",
    "scripts/test_warnings_gate.py", "scripts/test_jdk_release_gate.py")}  # the last two run through `ci_scope.py selftests` (a test keeps them in sync)
OWNER_ONLY_PREFIXES = tuple(p.casefold() for p in (".claude/", ".github/", ".githooks/", ".tools/", "agents/", "scripts/hooks/", "docs/reviews/",
                                                   "docs/product/", "design/", "gradle/wrapper/", "config/licensee/"))
OWNER_ONLY_BASENAMES = {n.casefold() for n in ("CODEOWNERS", "package.json", "package-lock.json", "libs.versions.toml", "mark-ready.sh", "update-branch.sh",
                                                          "CLAUDE.md", "CLAUDE.local.md",  # Claude Code loads these as agent instructions in any directory
                                                          ".gitattributes", ".mcp.json", ".gitleaks.toml", ".gitleaksignore")}  # R5
REQUIREMENTS_RE = re.compile(r"^requirements[\w.-]*\.txt$")
GENERAL_DRAFT_FILES, GENERAL_DRAFT_PREFIXES = ("docs/plan.md",), ("docs/milestones/",)  # drafts without a sign-off (not design/tokens.json, R3-01)
_SEG = r"[A-Za-z0-9_][A-Za-z0-9_.-]*"  # one path component: no dot-prefix, no "..", no space, no odd characters; matched case-sensitively
GENERAL_ALLOW = tuple(re.compile(p) for p in (
    rf"app/src/(?:main|test|androidTest)/kotlin(?:/{_SEG})+\.kt", rf"app/src/main/res(?:/{_SEG})+\.(?:xml|png|webp)",  # app sources, tests, resources
    rf"core/(?!testing/)[a-z][a-z0-9_-]*/src/(?:main|test)/kotlin(?:/{_SEG})+\.kt",  # core module sources and tests (core/testing is gate infrastructure)
    rf"docs(?:/{_SEG})+\.(?:md|csv|png|txt)", r"README\.md"))  # docs (the owner-only ones are refused by the lists above)
GENERAL_GATE_RE = re.compile(r"/architecture/|nonetwork|robolectric|junit4engine|jdkapilevel")  # tests that are gates, wherever they sit (casefolded)
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
NEW_PIN_RE = re.compile(r"^\s*(?:-\s+)?uses:\s*(?P<repo>[\w.-]+/[\w.-]+)(?:/[\w./-]+)?@(?P<sha>[0-9a-f]{40})\s*(?:#(?P<comment>.*))?$")
REPO_RE = re.compile(r"[A-Za-z0-9][\w.-]*/[\w.-]+")  # owner/repo, no leading dash or further path
TAG_RE = re.compile(r"[\w][\w.+-]*")
LS_REMOTE_TIMEOUT = 30


class ApiError(Exception):
    pass


class PinError(Exception):
    """A re-pinned action could not be tied to its tag (lookup failed, tag unknown or sha mismatch)."""


def ls_remote_resolver(run=subprocess.run):
    """A resolver (owner/repo, tag) -> the commit sha that tag points to, via `git ls-remote` (an annotated tag is dereferenced).
    Raises PinError on any failure, so a network problem refuses the merge. `run` is injectable for tests."""

    def resolve(repo, tag):
        if not REPO_RE.fullmatch(repo) or ".." in repo or not TAG_RE.fullmatch(tag):
            raise PinError(f"refusing to look up {repo!r} tag {tag!r}")
        ref = f"refs/tags/{tag}"
        try:
            res = run(["git", "ls-remote", f"https://github.com/{repo}", ref, f"{ref}^{{}}"], capture_output=True, text=True,
                      timeout=LS_REMOTE_TIMEOUT, env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})
        except (OSError, subprocess.SubprocessError) as e:
            raise PinError(f"git ls-remote {repo} failed: {type(e).__name__}") from e
        if res.returncode != 0:
            raise PinError(f"git ls-remote {repo} failed: {(res.stderr or '').strip()[:120] or res.returncode}")
        found = {}
        for line in res.stdout.splitlines():
            sha, _, name = line.partition("\t")
            if name in (ref, f"{ref}^{{}}"):
                if not SHA_RE.fullmatch(sha):
                    raise PinError(f"git ls-remote {repo}: unreadable line for tag {tag}")
                found[name] = sha
        commit = found.get(f"{ref}^{{}}") or found.get(ref)  # the peeled line is the commit of an annotated tag
        if not commit:
            raise PinError(f"tag {tag} not found in {repo}")
        return commit

    return resolve


def new_pins(patch):
    """(owner/repo, sha, tag or None) for each `uses:` line a diff adds; the tag is the first word of the trailing comment."""
    pins = []
    for _, added in _changed_lines(patch):
        for ln in added:
            m = NEW_PIN_RE.match(ln)
            if m:
                words = (m.group("comment") or "").split()
                pins.append((m.group("repo"), m.group("sha"), words[0] if words else None))
    return pins


def pin_tag_problems(name, patch, resolve):
    """Reasons a re-pinned action is not tied to its tag: no tag comment, a failed lookup, or a sha other than the tag's commit."""
    problems = []
    added = [ln for _, block in _changed_lines(patch) for ln in block]
    for ln in added:  # pin_only accepted this line, so the tag check must be able to read it too (one gate, no seam between two regexes)
        if PIN_LINE_RE.match(ln) and not NEW_PIN_RE.match(ln):
            problems.append(f"{name}: unparsed pin {ln.strip()[:80]!r}, cannot tie it to a tag")
    for repo, sha, tag in new_pins(patch):
        if not tag:
            problems.append(f"{name}: {repo}@{sha[:7]} has no tag comment (# <tag>), cannot tie the sha to a release")
            continue
        try:
            want = resolve(repo, tag)
        except PinError as e:
            problems.append(f"{name}: {repo} tag {tag}: {e}")
            continue
        except Exception as e:  # noqa: BLE001  # justified: any lookup crash must refuse the merge, never allow it
            problems.append(f"{name}: {repo} tag {tag}: lookup crashed ({type(e).__name__})")
            continue
        if want != sha:
            problems.append(f"{name}: {repo} tag {tag} is commit {want[:7]}, but the pin is {sha[:7]} (not the tagged release)")
    return problems


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


def owner_only(name):
    """Whether a path needs the owner's approval first (kind `general` refuses it): fail-closed, so everything but a GENERAL_ALLOW path is."""
    n = name.casefold()
    base = n.rsplit("/", 1)[-1]
    if base in OWNER_ONLY_BASENAMES or REQUIREMENTS_RE.match(base) or n in OWNER_ONLY_FILES or n.startswith(OWNER_ONLY_PREFIXES) or GENERAL_GATE_RE.search(n):
        return True
    return not any(p.fullmatch(name) for p in GENERAL_ALLOW)


def allowed(kind, name):
    """Whether a changed path belongs to the kind (workflow pins are judged on their patch, see pin_only)."""
    if ".." in name.split("/"):
        return False
    if kind == "general":
        return not owner_only(name)
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


def drops_draft_status(patch):
    """True if the diff removes more 'not owner-approved' status lines than it adds: a sign-off, which is the owner's."""
    count = lambda i: sum(DRAFT_STATUS in ln for block in _changed_lines(patch) for ln in block[i])  # noqa: E731  # justified: two-use local helper
    return count(0) > count(1)


def file_problems(kind, files, resolve):
    if not files:
        return ["no changed files"]
    problems = []
    for f in files:
        for name in (f["filename"], f.get("previous_filename")):
            if name and not allowed(kind, name):
                problems.append(f"path outside kind {kind}: {name}")
        name, patch = f["filename"], f.get("patch")
        draft = any(x.casefold() in GENERAL_DRAFT_FILES or x.casefold().startswith(GENERAL_DRAFT_PREFIXES) for x in (name, f.get("previous_filename") or name))
        if kind == "general" and draft and (f.get("status") in ("removed", "renamed") or patch is None or drops_draft_status(patch)):
            problems.append(f"{name}: removes or renames a working draft, has no patch to check, or removes a '{DRAFT_STATUS}' status line "
                            "(a sign-off is the owner's)")
        if kind == "dependabot" and f.get("status") != "modified":
            problems.append(f"{name}: status {f.get('status')}; a dependency bump only modifies files")
        if kind == "working-draft-docs" and (drops_draft_status(patch or "") or patch is None and not (name.endswith(".png") and f["status"] != "renamed")):
            problems.append(f"{name}: no patch to check, or removes a '{DRAFT_STATUS}' status line (a sign-off is the owner's)")
        check = pin_only if WORKFLOW_RE.match(name) else wrapper_only if name == WRAPPER_PROPS else None
        if kind == "dependabot" and check:
            if patch is None:
                problems.append(f"{name}: no patch from the API, cannot verify a version bump only")
            elif not check(patch):
                problems.append(f"{name}: changes beyond a version bump (re-pinned `uses:` lines, services.gradle.org distribution)")
            elif check is pin_only:
                problems += pin_tag_problems(name, patch, resolve)
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


def evaluate(api, repo, n, sha, kind, resolve):
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
    problems += file_problems(kind, files, resolve)
    problems += check_problems(api, repo, pr["base"]["ref"], sha)
    return pr, problems


KINDS = {"working-draft-docs", "tasks-sync", "dependabot", "general"}


def main(argv, api=None, out=sys.stdout, err=sys.stderr, resolver=None):
    if len(argv) != 3 or not argv[0].isdigit() or not SHA_RE.fullmatch(argv[1]):
        print("usage: merge_ready.py <N> <40-hex head sha> <kind>", file=err)
        return 2
    n, sha, kind = int(argv[0]), argv[1], argv[2]
    if kind not in KINDS:
        print(f"merge_ready: unknown kind {kind!r}; expected one of {', '.join(sorted(KINDS))}", file=err)
        return 2
    api = api or GhApi()
    try:
        pr, problems = evaluate(api, REPO, n, sha, kind, resolver or ls_remote_resolver())
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
