"""Keeps triaged Dependabot alerts fixed (issue 187): no known-vulnerable version of a listed dependency may come back.

Two sources, both lists of what really resolves:
  * firebase/package-lock.json (npm): every `node_modules/**/<name>` entry must be outside the vulnerable range.
  * gradle/verification-metadata.xml (Gradle): Gradle fails the build for an artifact without an entry, so a component with a
    jar or aar here is a version that resolves somewhere. Pom-only and module-only entries (parents, BOMs) are not used code.
A rule is one advisory: the package and every vulnerable range of it, each as (first affected, first fixed). Advisories often list
several ranges (one per release line); copy all of them. Adding a bump for a new alert: add its row to RULES with the advisory id, then
fix the manifests until this passes.
Run: python3 -I scripts/dependency_floors.py [repo root]  (exit 1 and one line per vulnerable version).
"""

import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import NamedTuple


class Rule(NamedTuple):
    ecosystem: str  # "npm" or "gradle"
    name: str  # npm package name, or Gradle group:artifact
    advisory: str
    ranges: tuple  # ((first affected, first fixed), ...): every vulnerable range of the advisory, ordered and disjoint


# One row per package; the row names the most severe advisory (grpc-js also GHSA-f596-whhp-79r4, bcprov also GHSA-qp49-qgx5-5m26).
# A range starts at "0" when the advisory has no lower bound. Copy every range from the advisory page, not just the first one.
RULES = [
    Rule("npm", "@grpc/grpc-js", "GHSA-m9gg-hp2v-232j", (("0", "1.13.6"), ("1.14.0", "1.14.5"))),
    Rule("npm", "minimatch", "GHSA-g3hv-75wg-m249", (("7.0.0", "11.0.1"),)),
    Rule("npm", "uuid", "GHSA-w5hq-g745-h8pq", (("0", "11.1.1"), ("12.0.0", "12.0.1"), ("13.0.0", "13.0.1"))),
    Rule("gradle", "org.freemarker:freemarker", "GHSA-27j2-h3m2-8237", (("2.2.0", "2.3.35"),)),
    Rule("gradle", "org.bouncycastle:bcprov-jdk18on", "GHSA-9pwp-9qqc-pr26", (("0", "1.85"),)),
    Rule("gradle", "org.bouncycastle:bcpkix-jdk18on", "GHSA-wg6q-6289-32hp", (("1.49", "1.84"),)),
    Rule("gradle", "com.google.guava:guava", "GHSA-xxph-c9ww-hj94", (("4.0", "33.7.2"),)),
    Rule("gradle", "org.codehaus.plexus:plexus-utils", "GHSA-6fmv-xxpf-w3cw", (("0", "3.6.1"), ("4.0.0", "4.0.3"))),
    Rule("gradle", "org.bitbucket.b_c:jose4j", "GHSA-3677-xxcr-wjqv", (("0", "0.9.6"),)),
    Rule("gradle", "org.jdom:jdom2", "GHSA-2363-cqg2-863c", (("0", "2.0.6.1"),)),
    Rule("gradle", "org.apache.commons:commons-lang3", "GHSA-j288-q9x7-2f5v", (("3.0", "3.18.0"),)),
    Rule("gradle", "org.apache.httpcomponents:httpclient", "GHSA-7r82-7xv7-xcpj", (("0", "4.5.13"), ("5.0.0", "5.0.3"))),
]


def version_key(version):
    """Sort key of a version: its numeric dot parts; a suffix such as -jre or -android is ignored."""
    return tuple(int(p) for p in re.findall(r"[0-9]+", version.split("-", 1)[0]))


def _fixed_in(rule, version):
    """The first fixed version of the range that contains `version`, or None if the version is not vulnerable."""
    key = version_key(version)
    for first_affected, fixed in rule.ranges:
        if version_key(first_affected) <= key < version_key(fixed):
            return fixed
    return None


def _report(rule, version, fixed, where):
    return f"{where}: {rule.name} {version} is vulnerable ({rule.advisory}), first fixed in {fixed}"


def _problems(rules, name, version, where):
    return [_report(r, version, fixed, where) for r in rules if r.name == name for fixed in [_fixed_in(r, version)] if fixed]


def check_npm_lock(text, where="firebase/package-lock.json"):
    try:
        packages = json.loads(text).get("packages")
    except (ValueError, AttributeError):
        return [f"{where}: not valid JSON"]
    if not isinstance(packages, dict) or len(packages) < 2:
        return [f"{where}: has no packages section, so nothing could be checked"]
    rules = [r for r in RULES if r.ecosystem == "npm"]
    problems = []
    for path, info in packages.items():
        name = path.rsplit("node_modules/", 1)[-1]
        version = info.get("version") if isinstance(info, dict) else None
        if not version:
            continue
        problems += _problems(rules, name, version, where)
    return problems


def check_gradle_metadata(text, where="gradle/verification-metadata.xml"):
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return [f"{where}: not valid XML"]
    components = [e for e in root.iter() if e.tag.rsplit("}", 1)[-1] == "component"]
    if not components:
        return [f"{where}: has no components, so nothing could be checked"]
    rules = [r for r in RULES if r.ecosystem == "gradle"]
    problems = []
    for comp in components:
        gav = f"{comp.get('group')}:{comp.get('name')}"
        version = comp.get("version") or ""
        used = any((a.get("name") or "").endswith((".jar", ".aar")) for a in comp)
        if used:
            problems += _problems(rules, gav, version, where)
    return problems


def main(root):
    root = Path(root)
    problems = []
    for rel, check in (("firebase/package-lock.json", check_npm_lock), ("gradle/verification-metadata.xml", check_gradle_metadata)):
        path = root / rel
        if path.is_file():
            problems += check(path.read_text(encoding="utf-8"), rel)
        else:
            problems.append(f"{rel}: file not found")
    for p in problems:
        print(f"dependency-floors: {p}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent))
