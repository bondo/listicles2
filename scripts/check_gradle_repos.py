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


def _block(text, name):
    """Body of the first `name { ... }` block, or None."""
    m = re.search(r"\b" + re.escape(name) + r"(\(\))?\s*\{", text)
    if not m:
        return None
    depth, i = 1, m.end()
    while i < len(text) and depth:
        depth += {"{": 1, "}": -1}.get(text[i], 0)
        i += 1
    return text[m.end() : i - 1] if depth == 0 else None


def check_settings(text):
    problems = []
    for name in BLOCKS:
        outer = _block(text, name)
        repos = _block(outer, "repositories") if outer is not None else None
        if repos is None:
            problems.append(f"{name}: no repositories block")
            continue
        mirror = repos.find(MIRROR)
        central = repos.find("mavenCentral()")
        if mirror < 0:
            problems.append(f"{name}: Maven Central mirror {MIRROR} missing")
        elif central < 0:
            problems.append(f"{name}: mavenCentral() fallback missing")
        elif mirror > central:
            problems.append(f"{name}: Maven Central mirror must come before mavenCentral()")
        google = re.search(r"\bgoogle(\(\))?\s*(\{)?", repos)
        if google and not (google.group(2) and "content" in (_block(repos[google.start() :], "google") or "")):
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
