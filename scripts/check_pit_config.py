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
# PIT defaults minus VOID_METHOD_CALLS (see core/domain/build.gradle.kts). Extra, stronger mutators are allowed; dropping one is not.
MUTATORS = (
    "CONDITIONALS_BOUNDARY",
    "INCREMENTS",
    "INVERT_NEGS",
    "MATH",
    "NEGATE_CONDITIONALS",
    "EMPTY_RETURNS",
    "FALSE_RETURNS",
    "TRUE_RETURNS",
    "NULL_RETURNS",
    "PRIMITIVE_RETURNS",
)
CI_SCRIPTS = ("scripts/test_check_pit_config.py", "scripts/check_pit_config.py")


def active(text):
    return "\n".join(ln for ln in text.splitlines() if not ln.strip().startswith(("//", "#")))


def problems(domain, root, verify, ci):
    out = []
    d, r, v, w = active(domain), active(root), active(verify), active(ci)
    if not re.search(r"alias\(libs\.plugins\.pitest\)", d):
        out.append("core/domain/build.gradle.kts does not apply the pitest plugin")
    if "kotest.pitest" in d:
        out.append("kotest-extensions-pitest 1.2.0 needs Kotest 5 classes and crashes PIT on Kotest 6; use junit5PluginVersion")
    if not re.search(r"junit5PluginVersion\.set\(", d):
        out.append("pitest must run Kotest through the JUnit 5 plugin (junit5PluginVersion)")
    if not re.search(r'targetClasses\.set\(listOf\("dk\.bjarkebjarke\.tally\.domain\.\*"\)\)', d):
        out.append("pitest targetClasses must be dk.bjarkebjarke.tally.domain.*")
    if re.search(r"avoidCallsTo|excludedClasses|excludedMethods|excludedTestClasses", d):
        out.append("pitest must not use avoidCallsTo or exclusions: they drop real mutants and empty the gate")
    ml = re.search(r"mutators\.set\(\s*listOf\(([^)]*)\)\s*,?\s*\)", d)
    names = re.findall(r'"(\w+)"', ml.group(1)) if ml else []
    if not names:
        out.append("pitest mutators must be pinned explicitly (PIT defaults without VOID_METHOD_CALLS)")
    else:
        for need in MUTATORS:
            if need not in names:
                out.append(f"pitest mutators must include {need}")
        if "VOID_METHOD_CALLS" in names:
            out.append("pitest mutators must not include VOID_METHOD_CALLS (Kotlin null-check intrinsics are equivalent mutants)")
    m = re.search(r"mutationThreshold\.set\((\w+)\)", d)
    if not m or not m.group(1).isdigit():
        out.append("pitest mutationThreshold must be a literal number")
    elif int(m.group(1)) < FLOOR:
        out.append(f"pitest mutationThreshold {m.group(1)} is below the floor {FLOOR}")
    if not re.search(r'"koverVerify"\)\s*\{\s*dependsOn\("' + re.escape(TASK) + r'"\)', r):
        out.append("root build.gradle.kts: koverVerify does not depend on " + TASK + " (CI runs it through the unit job)")
    if not re.search(rf"(?m)^\s*step\s+mutation\s+gradle\s+{re.escape(TASK)}\s*$", v):
        out.append("verify.sh does not run `step mutation gradle " + TASK + "`")
    for script in CI_SCRIPTS:
        if not re.search(rf"(?m)^\s*(?:-\s+)?run:\s+python3 -I {re.escape(script)}\s*$", w):
            out.append(f"ci.yml (tasks job) does not run `python3 -I {script}`: only verify.sh would notice a broken PIT wiring")
    return out


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


def main():
    found = problems(
        read("core", "domain", "build.gradle.kts"),
        read("build.gradle.kts"),
        read("scripts", "verify.sh"),
        read(".github", "workflows", "ci.yml"),
    )
    for p in found:
        print(f"pit-config: {p}")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
