"""Checks the Gradle repository setup that keeps cold dependency downloads from failing on HTTP 429.

Maven Central (repo.maven.apache.org, behind Cloudflare) answers a share of requests from shared cloud
egress IPs with 429. Gradle disables a repository for the rest of the build once its retries for one
request run out, so a single unlucky burst fails the whole build. The setup this checks:
  * Google's Maven Central mirror is listed before mavenCentral() (mavenCentral() stays as fallback),
  * google() only gets the groups it hosts, so other artifacts are not looked up there first,
  * Gradle retries repository requests often enough, with backoff, to ride out a 429 burst.
Run: python3 -I scripts/check_gradle_repos.py  (exit 1 and one line per problem when the setup is off).
"""

import re
import sys
from pathlib import Path

MIRROR = "https://maven-central.storage-download.googleapis.com/maven2"
BLOCKS = ("pluginManagement", "dependencyResolutionManagement")
MIN_TENTATIVES = 6
MIN_BACKOFF_MS = 1000
TENTATIVES = "systemProp.org.gradle.internal.repository.max.tentatives"
BACKOFF = "systemProp.org.gradle.internal.repository.initial.backoff"


def _strip(text, blank_strings=False):
    """Kotlin source without // and /* */ comments; string contents become spaces if blank_strings."""
    out, i, n = [], 0, len(text)
    while i < n:
        if text.startswith("//", i):
            while i < n and text[i] != "\n":
                i += 1
        elif text.startswith("/*", i):
            end = text.find("*/", i + 2)
            i = n if end < 0 else end + 2
        elif text[i] == '"':
            out.append('"')
            i += 1
            while i < n and text[i] != '"':
                step = 2 if text[i] == "\\" else 1
                out.append(" " * step if blank_strings else text[i : i + step])
                i += step
            if i < n:
                out.append('"')
                i += 1
        else:
            out.append(text[i])
            i += 1
    return "".join(out)


def _body(text, open_brace):
    """Body of the block whose `{` is at open_brace, or None if unbalanced."""
    depth, i = 1, open_brace + 1
    while i < len(text) and depth:
        depth += {"{": 1, "}": -1}.get(text[i], 0)
        i += 1
    return text[open_brace + 1 : i - 1] if depth == 0 else None


def _block(text, name):
    """Body of the first `name { ... }` block, or None."""
    m = re.search(r"\b" + re.escape(name) + r"(\(\))?\s*\{", text)
    return _body(text, m.end() - 1) if m else None


def _filtered(repos, call):
    """True if the google() call at match `call` has a content { include...(...) } filter."""
    brace = re.compile(r"\s*\{").match(repos, call.end())
    body = _body(repos, brace.end() - 1) if brace else None
    content = _block(body, "content") if body is not None else None
    return content is not None and re.search(r"\binclude\w*\s*\(", content) is not None


def check_settings(text):
    problems = []
    for name in BLOCKS:
        outer = _block(_strip(text, blank_strings=True), name)
        outer_text = _block(_strip(text), name)
        repos = _block(outer, "repositories") if outer is not None else None
        if repos is None:
            problems.append(f"{name}: no repositories block")
            continue
        repos_text = _block(outer_text, "repositories")
        mirror = repos_text.find(f'"{MIRROR}"')
        central = re.search(r"\bmavenCentral\s*\(\s*\)", repos)
        if mirror < 0:
            problems.append(f"{name}: Maven Central mirror {MIRROR} missing")
        elif central is None:
            problems.append(f"{name}: mavenCentral() fallback missing")
        elif mirror > central.start():
            problems.append(f"{name}: Maven Central mirror must come before mavenCentral()")
        calls = re.finditer(r"(?<![\w.])google\b\s*(\(\s*\))?", repos)
        if not all(_filtered(repos, call) for call in calls):
            problems.append(f"{name}: google() needs a content filter")
    return problems


def check_properties(text):
    props = {}
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            props[key.strip()] = value.strip()
    problems = []
    for key, minimum in ((TENTATIVES, MIN_TENTATIVES), (BACKOFF, MIN_BACKOFF_MS)):
        value = props.get(key)
        if value is None or not value.isdigit():
            problems.append(f"gradle.properties: {key} missing or not a number")
        elif int(value) < minimum:
            problems.append(f"gradle.properties: {key}={value} is below {minimum}")
    return problems


def main(root):
    root = Path(root)
    problems = check_settings((root / "settings.gradle.kts").read_text(encoding="utf-8"))
    problems += check_properties((root / "gradle.properties").read_text(encoding="utf-8"))
    for p in problems:
        print(f"gradle-repos: {p}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent))
