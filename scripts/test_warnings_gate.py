"""Tests for the :checkWarningsAsErrors Gradle gate (M0.5-09). Run: python3 -I scripts/test_warnings_gate.py

Needs a JDK and the Gradle wrapper, so it is its own verify.sh / CI step (not part of scripts/hooks).
Each bad configuration is injected with a Gradle init script (-I), so no source file changes.
The gate must pass on the clean build and fail, naming the task, for every way of turning
warnings-as-errors off or hiding warnings.
"""

import os
import subprocess
import tempfile
import time
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
TASK = ":core:domain:compileKotlin"
APP_TASK = ":app:compileDebugKotlin"
MODULES = (":app", ":core:data", ":core:domain", ":core:testing")
GATE_MESSAGE = "warnings are not all errors"

# Groovy init script; %s is the statement applied to the compile task's compilerOptions. M1-98: gradle.lifecycle.beforeProject, not
# allprojects, which Gradle's isolated projects mode rejects
# (gradle.properties turns it on once M1-124 lands).
INIT = """
gradle.lifecycle.beforeProject { p ->
    p.tasks.matching { it.path == '%s' }.configureEach { %s }
}
"""

BAD = {
    "all-warnings-as-errors-off": "compilerOptions.allWarningsAsErrors.set(false)",
    "warning-level-disabled": "compilerOptions.freeCompilerArgs.add('-Xwarning-level=DEPRECATION:disabled')",
    "warning-level-disabled-other-id": "compilerOptions.freeCompilerArgs.add('-Xwarning-level=UNUSED_VARIABLE:disabled')",
    "nowarn": "compilerOptions.freeCompilerArgs.add('-nowarn')",
    "suppress-warnings-property": "compilerOptions.suppressWarnings.set(true)",
    "warning-level-split-arg": "compilerOptions.freeCompilerArgs.addAll(['-Xwarning-level', 'DEPRECATION:disabled'])",
    "suppress-warning-split-arg": "compilerOptions.freeCompilerArgs.addAll(['-Xsuppress-warning', 'DEPRECATION'])",
    "warning-level-comma-list": "compilerOptions.freeCompilerArgs.add('-Xwarning-level=DEPRECATION:disabled,UNUSED_VARIABLE:error')",
    "warning-level-comma-list-split": "compilerOptions.freeCompilerArgs.addAll(['-Xwarning-level', 'DEPRECATION:disabled,UNUSED_VARIABLE:error'])",
    "warning-level-comma-list-spaces": "compilerOptions.freeCompilerArgs.add('-Xwarning-level=DEPRECATION:disabled , UNUSED_VARIABLE:error')",
    "warning-level-trailing-comma": "compilerOptions.freeCompilerArgs.add('-Xwarning-level=DEPRECATION:disabled,')",
    "warning-level-repeated-then-error": ("compilerOptions.freeCompilerArgs.addAll("
                                         "['-Xwarning-level=DEPRECATION:disabled', '-Xwarning-level=DEPRECATION:error'])"),
    "warning-level-empty-value": "compilerOptions.freeCompilerArgs.add('-Xwarning-level=')",
    "warning-level-bare-last": "compilerOptions.freeCompilerArgs.add('-Xwarning-level')",
    "warning-level-uppercase-error": "compilerOptions.freeCompilerArgs.add('-Xwarning-level=DEPRECATION:ERROR')",
    "xsuppress-warning": "compilerOptions.freeCompilerArgs.add('-Xsuppress-warning=DEPRECATION')",
    # Issue 48 (PR 47 R2-03, R4-01, R4-02; M1-68 part B3): every -Xsuppress-* and -Xdont-warn* flag, and any @argfile, whose
    # contents the gate cannot see (args.txt could hold -Xwarning-level=DEPRECATION:disabled).
    "xsuppress-version-warnings": "compilerOptions.freeCompilerArgs.add('-Xsuppress-version-warnings')",
    "xsuppress-other-flag": "compilerOptions.freeCompilerArgs.add('-Xsuppress-deprecated-jvm-target-warning')",
    "xdont-warn-on-error-suppression": "compilerOptions.freeCompilerArgs.add('-Xdont-warn-on-error-suppression')",
    "xdont-warn-other-flag": "compilerOptions.freeCompilerArgs.add('-Xdont-warn-anything')",
    "argfile": "compilerOptions.freeCompilerArgs.add('@args.txt')",
    # PR 359 R1-02: the value of a bare flag that is not otherwise checked, so only the @ rule can reject it.
    "argfile-as-value": "compilerOptions.freeCompilerArgs.addAll(['-opt-in', '@x.txt'])",
}


def gradle(*args, init=None, task=TASK):
    cmd = [os.path.join(ROOT, "gradlew"), "-q", "--console=plain", "--no-daemon", *args]
    tmp = None
    if init is not None:
        with tempfile.NamedTemporaryFile("w", suffix=".init.gradle", delete=False) as tmp:
            tmp.write(INIT % (task, init))
        cmd += ["-I", tmp.name]
    try:
        # Retry only Maven/Gradle 429 (rate limit) so a throttled download is not read as a test failure.
        for attempt in range(5):
            r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
            out = r.stdout + r.stderr
            if "429" in out and "Too Many Requests" in out and attempt < 4:
                time.sleep(10 * (attempt + 1))
                continue
            return r.returncode, out
    finally:
        if tmp is not None:
            os.unlink(tmp.name)


class WarningsGateTest(unittest.TestCase):
    def test_clean_build_passes(self):
        rc, out = gradle("checkWarningsAsErrors")
        self.assertEqual(rc, 0, out)

    def test_all_error_levels_are_accepted(self):
        rc, out = gradle(
            "checkWarningsAsErrors",
            init="compilerOptions.freeCompilerArgs.add('-Xwarning-level=DEPRECATION:error, UNUSED_VARIABLE:error')",
        )
        self.assertEqual(rc, 0, out)

    def test_flags_that_only_mention_warnings_are_accepted(self):
        # Issue 48's rules match prefixes (-Xsuppress-, -Xdont-warn, @), not any flag naming warnings or suppression.
        rc, out = gradle(
            "checkWarningsAsErrors",
            init="compilerOptions.freeCompilerArgs.addAll(['-Xreport-all-warnings', '-Xno-suppress-x', '-Xwarn@x'])",
        )
        self.assertEqual(rc, 0, out)

    def test_broken_injection_is_not_mistaken_for_gate_rejection(self):
        # An injection that fails on its own (rc != 0, task path in the error) must not satisfy the negative tests.
        rc, out = gradle("checkWarningsAsErrors", init="compilerOptions.nope.set(true)")
        self.assertNotEqual(rc, 0, out)
        self.assertNotIn(GATE_MESSAGE, out)

    def test_detekt_depends_on_gate(self):
        rc, out = gradle("detekt", "--dry-run")
        self.assertEqual(rc, 0, out)
        self.assertIn(":checkWarningsAsErrors", out)
        # M1-68 part B2: each module checks its own compile tasks, and the root runs every module's checks by task path.
        for module in MODULES:
            self.assertIn(f"{module}:tallyChecks SKIPPED", out)
            self.assertIn(f"{module}:checkWarningsAsErrors SKIPPED", out)

    def test_each_module_checks_its_own_compile_tasks(self):
        rc, out = gradle(":app:checkWarningsAsErrors", init="compilerOptions.allWarningsAsErrors.set(false)", task=APP_TASK)
        self.assertNotEqual(rc, 0, out)
        self.assertIn(GATE_MESSAGE, out)
        self.assertIn(APP_TASK, out)
        rc, out = gradle(":core:domain:checkWarningsAsErrors", init="compilerOptions.allWarningsAsErrors.set(false)", task=APP_TASK)
        self.assertEqual(rc, 0, out)


def _make(name, statement):
    def test(self):
        rc, out = gradle("checkWarningsAsErrors", init=statement)
        self.assertNotEqual(rc, 0, f"gate accepted {name}:\n{out}")
        self.assertIn(GATE_MESSAGE, out, f"{name} failed for another reason, the gate did not reject it:\n{out}")
        self.assertIn(TASK, out)

    return test


for _name, _stmt in BAD.items():
    setattr(WarningsGateTest, "test_fails_on_" + _name.replace("-", "_"), _make(_name, _stmt))

if __name__ == "__main__":
    unittest.main()
