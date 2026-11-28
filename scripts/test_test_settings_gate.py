"""Tests for the per-module checkTestSettings Gradle gate (M1-68 part B, PR 320 R2-01). Run: python3 -I scripts/test_test_settings_gate.py

Needs a JDK and the Gradle wrapper, so it is a verify.sh / CI gate self-test (scripts/ci_scope.py), not part of scripts/hooks.
The convention plugins put every Test task on the JUnit Platform with failOnNoDiscoveredTests on, and register checkTestSettings in
every module; every Test task depends on it. The check reads the settings each Test task ends up with, so a module (or a later
configuration block) that turns one off again fails the build, which the guards script's text rule for the move cannot see.
Each bad setting is injected with a Gradle init script (-I) after the module is configured, so no source file changes.
"""

import os
import subprocess
import tempfile
import time
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
MODULES = (":app", ":core:data", ":core:domain", ":core:testing")
# Release unit tests are off (AGP: enableUnitTest = false for release), so each module has these Test tasks.
TEST_TASKS = (":app:testDebugUnitTest", ":core:data:testDebugUnitTest", ":core:domain:test", ":core:testing:test")
GATE_MESSAGE = "must run on the JUnit Platform with failOnNoDiscoveredTests"

# Groovy init script; after each project is configured (so after the convention plugin), %s is applied to the task with that path.
# M1-98: gradle.lifecycle.afterProject, not allprojects/afterEvaluate, which Gradle's isolated projects mode rejects
# (gradle.properties turns it on once M1-124 lands).
INIT = """
gradle.lifecycle.afterProject { p ->
    p.tasks.matching { it.path == '%s' }.configureEach { %s }
}
"""

BAD = {
    "fail-on-no-tests-off": (":core:domain:test", "failOnNoDiscoveredTests.set(false)"),
    "junit4-runner-android-app": (":app:testDebugUnitTest", "useJUnit()"),
    "junit4-runner-android-library": (":core:data:testDebugUnitTest", "useJUnit()"),
    "testng-runner": (":core:testing:test", "useTestNG()"),
    "fail-on-no-tests-off-android-app": (":app:testDebugUnitTest", "failOnNoDiscoveredTests.value(false)"),
    "junit4-runner-jvm-library": (":core:domain:test", "useJUnit()"),
}


def gradle(*args, init=None):
    cmd = [os.path.join(ROOT, "gradlew"), "-q", "--console=plain", "--no-daemon", *args]
    tmp = None
    if init is not None:
        with tempfile.NamedTemporaryFile("w", suffix=".init.gradle", delete=False) as tmp:
            tmp.write(INIT % init)
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


def module_of(task):
    return task.rsplit(":", 1)[0]


class TestSettingsGateTest(unittest.TestCase):
    def test_clean_build_passes_in_every_module(self):
        rc, out = gradle(*(m + ":checkTestSettings" for m in MODULES))
        self.assertEqual(rc, 0, out)

    def test_every_test_task_depends_on_its_module_check(self):
        for task in TEST_TASKS:
            with self.subTest(task=task):
                rc, out = gradle(task, "--dry-run")
                self.assertEqual(rc, 0, out)
                self.assertIn(module_of(task) + ":checkTestSettings SKIPPED", out)

    def test_broken_injection_is_not_mistaken_for_gate_rejection(self):
        # An injection that fails on its own (rc != 0, task path in the error) must not satisfy the negative tests.
        rc, out = gradle(":core:domain:checkTestSettings", init=(":core:domain:test", "failOnNoDiscoveredTests.nope()"))
        self.assertNotEqual(rc, 0, out)
        self.assertNotIn(GATE_MESSAGE, out)


def _make(name, task, statement):
    def test(self):
        rc, out = gradle(module_of(task) + ":checkTestSettings", init=(task, statement))
        self.assertNotEqual(rc, 0, f"gate accepted {name}:\n{out}")
        self.assertIn(GATE_MESSAGE, out, f"{name} failed for another reason, the gate did not reject it:\n{out}")
        self.assertIn(task, out)

    return test


for _name, (_task, _stmt) in BAD.items():
    setattr(TestSettingsGateTest, "test_fails_on_" + _name.replace("-", "_"), _make(_name, _task, _stmt))

if __name__ == "__main__":
    unittest.main()
