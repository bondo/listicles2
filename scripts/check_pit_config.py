"""Checks that PIT mutation testing stays wired on core/domain (M1-05, PLAN P16). Run: python3 -I scripts/check_pit_config.py

Floor 80 (owner decision, issue 15): raise it later, never lower it. CI runs PIT through the unit job's Gradle call, because the root
`koverVerify` task depends on `:core:domain:pitest`; verify.sh runs the same task as its own step (skipped with --fast, like unit tests).
"""

import os
import re
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
FLOOR = 80
TASK = ":core:domain:pitest"


def active(text):
    return "\n".join(ln for ln in text.splitlines() if not ln.strip().startswith(("//", "#")))


def problems(domain, root, verify):
    out = []
    d, r, v = active(domain), active(root), active(verify)
    if not re.search(r"alias\(libs\.plugins\.pitest\)", d):
        out.append("core/domain/build.gradle.kts does not apply the pitest plugin")
    if "kotest.pitest" in d:
        out.append("kotest-extensions-pitest 1.2.0 needs Kotest 5 classes and crashes PIT on Kotest 6; use junit5PluginVersion")
    if not re.search(r"junit5PluginVersion\.set\(", d):
        out.append("pitest must run Kotest through the JUnit 5 plugin (junit5PluginVersion)")
    if not re.search(r'targetClasses\.set\(listOf\("dk\.bjarkebjarke\.tally\.domain\.\*"\)\)', d):
        out.append("pitest targetClasses must be dk.bjarkebjarke.tally.domain.*")
    m = re.search(r"mutationThreshold\.set\((\w+)\)", d)
    if not m or not m.group(1).isdigit():
        out.append("pitest mutationThreshold must be a literal number")
    elif int(m.group(1)) < FLOOR:
        out.append(f"pitest mutationThreshold {m.group(1)} is below the floor {FLOOR}")
    if not re.search(r'"koverVerify"\)\s*\{\s*dependsOn\("' + re.escape(TASK) + r'"\)', r):
        out.append("root build.gradle.kts: koverVerify does not depend on " + TASK + " (CI runs it through the unit job)")
    if not re.search(rf"(?m)^\s*step\s+mutation\s+gradle\s+{re.escape(TASK)}\s*$", v):
        out.append("verify.sh does not run `step mutation gradle " + TASK + "`")
    return out


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


def main():
    found = problems(read("core", "domain", "build.gradle.kts"), read("build.gradle.kts"), read("scripts", "verify.sh"))
    for p in found:
        print(f"pit-config: {p}")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
