"""Keeps triaged Dependabot alerts fixed (issue 187): no known-vulnerable version of a listed dependency may come back.

Two sources, both lists of what really resolves:
  * firebase/package-lock.json (npm): every `node_modules/**/<name>` entry must be outside the vulnerable range.
  * gradle/verification-metadata.xml (Gradle): Gradle fails the build for an artifact without an entry, so a component with a
    jar or aar here is a version that resolves somewhere. Pom-only and module-only entries (parents, BOMs) are not used code.
A rule is one advisory: the package, the first fixed version and, when the advisory has a lower bound, the first affected version.
Adding a bump for a new alert: add its row to RULES with the advisory id, then fix the manifests until this passes.
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
    fixed: str  # first version that is not vulnerable
    advisory: str
    first_affected: str = "0"


# One row per package and fixed version; the row names the most severe advisory (grpc-js also GHSA-f596-whhp-79r4, bcprov also GHSA-qp49-qgx5-5m26).
RULES = [
    Rule("npm", "@grpc/grpc-js", "1.13.6", "GHSA-m9gg-hp2v-232j"),
    Rule("npm", "minimatch", "11.0.1", "GHSA-g3hv-75wg-m249", first_affected="7.0.0"),
    Rule("npm", "uuid", "11.1.1", "GHSA-w5hq-g745-h8pq"),
    Rule("gradle", "org.freemarker:freemarker", "2.3.35", "GHSA-27j2-h3m2-8237", first_affected="2.2.0"),
    Rule("gradle", "org.bouncycastle:bcprov-jdk18on", "1.85", "GHSA-9pwp-9qqc-pr26"),
    Rule("gradle", "org.bouncycastle:bcpkix-jdk18on", "1.84", "GHSA-wg6q-6289-32hp", first_affected="1.49"),
    Rule("gradle", "com.google.guava:guava", "33.7.2", "GHSA-xxph-c9ww-hj94", first_affected="4.0"),
    Rule("gradle", "org.codehaus.plexus:plexus-utils", "3.6.1", "GHSA-6fmv-xxpf-w3cw"),
    Rule("gradle", "org.bitbucket.b_c:jose4j", "0.9.6", "GHSA-3677-xxcr-wjqv"),
    Rule("gradle", "org.jdom:jdom2", "2.0.6.1", "GHSA-2363-cqg2-863c"),
    Rule("gradle", "org.apache.commons:commons-lang3", "3.18.0", "GHSA-j288-q9x7-2f5v", first_affected="3.0"),
    Rule("gradle", "org.apache.httpcomponents:httpclient", "4.5.13", "GHSA-7r82-7xv7-xcpj"),
]


def version_key(version):
    """Sort key of a version: its numeric dot parts; a suffix such as -jre or -android is ignored."""
    return tuple(int(p) for p in re.findall(r"[0-9]+", version.split("-", 1)[0]))


def _vulnerable(rule, version):
    key = version_key(version)
    return version_key(rule.first_affected) <= key < version_key(rule.fixed)


def _report(rule, version, where):
    return f"{where}: {rule.name} {version} is vulnerable ({rule.advisory}), first fixed in {rule.fixed}"


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
        problems += [_report(r, version, where) for r in rules if r.name == name and _vulnerable(r, version)]
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
            problems += [_report(r, version, where) for r in rules if r.name == gav and _vulnerable(r, version)]
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
