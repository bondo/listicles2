"""Tests for the :checkJdkRelease Gradle gate (issue 211). Run: python3 -I scripts/test_jdk_release_gate.py

Needs a JDK and the Gradle wrapper, so it is its own verify.sh step (not part of scripts/hooks).
Each bad configuration is injected with a Gradle init script (-I), so no source file changes. The injection runs
in gradle.lifecycle.afterProject (afterEvaluate), after the build's own shared setting, so it overrides what the build configured.
The gate must pass on the clean build and fail, naming the task or configuration, for every way a JVM module
could compile against the JDK 21 API, and for a test-support module that reaches a non-test configuration.
"""

import os
import subprocess
import tempfile
import time
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
GATE_MESSAGE = "JVM modules must compile against the JDK 17 API"
KOTLIN_TASK = ":core:domain:compileKotlin"
JAVA_TASK = ":core:domain:compileJava"
# Groovy init script; the first %s is a project path, the second the statement run for that project after it is evaluated.
# M1-98: gradle.lifecycle.afterProject, not allprojects/afterEvaluate, which Gradle's isolated projects mode rejects
# (gradle.properties turns it on once M1-124 lands).
INIT = """
gradle.lifecycle.afterProject { p ->
    if (p.path == '%s') {
        %s
    }
}
"""


def on_task(name, statement):
    return f"p.tasks.matching {{ it.name == '{name}' }}.configureEach {{ {statement} }}"


KOTLIN_BAD = {
    "flag-missing": "compilerOptions.freeCompilerArgs.set(['-Xfoo'])",
    "release-21": "compilerOptions.freeCompilerArgs.set(['-Xjdk-release=21'])",
    "release-17-then-21": "compilerOptions.freeCompilerArgs.add('-Xjdk-release=21')",
    "release-8": "compilerOptions.freeCompilerArgs.set(['-Xjdk-release=1.8'])",
}
JAVA_BAD = {
    "release-21": "options.release.set(21)",
    "release-unset": "options.release.set((Integer) null)",
}


# Adds the project :fakes in the given directory to this build only (the init script also runs for build-logic).
SETTINGS_INIT = """
settingsEvaluated { s ->
    if (s.rootDir.canonicalPath == new File('%s').canonicalPath) {
        s.include(':fakes')
        s.project(':fakes').projectDir = new File('%s')
    }
}
"""


def gradle(*args, init=None, project=":core:domain", settings=None):
    cmd = [os.path.join(ROOT, "gradlew"), "-q", "--console=plain", "--no-daemon", *args]
    tmp = None
    if init is not None or settings is not None:
        with tempfile.NamedTemporaryFile("w", suffix=".init.gradle", delete=False) as tmp:
            tmp.write(settings if settings is not None else INIT % (project, init))
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


class JdkReleaseGateTest(unittest.TestCase):
    def test_clean_build_passes(self):
        rc, out = gradle("checkJdkRelease")
        self.assertEqual(rc, 0, out)

    def test_broken_injection_is_not_mistaken_for_gate_rejection(self):
        # An injection that fails on its own must not satisfy the negative tests.
        rc, out = gradle("checkJdkRelease", init=on_task("compileKotlin", "compilerOptions.nope.set(true)"))
        self.assertNotEqual(rc, 0, out)
        self.assertNotIn(GATE_MESSAGE, out)

    def test_message_names_the_gap_it_closes(self):
        # Release 17 closes the JDK 18 to 21 gap only; the message must not promise that every API exists on API 26.
        rc, out = gradle("checkJdkRelease", init=on_task("compileKotlin", "compilerOptions.freeCompilerArgs.set([])"))
        self.assertNotEqual(rc, 0, out)
        self.assertIn("JDK 18 to 21", out)
        self.assertNotIn("has every method called", out)

    def test_detekt_depends_on_gate(self):
        rc, out = gradle("detekt", "--dry-run")
        self.assertEqual(rc, 0, out)
        self.assertIn(":checkJdkRelease", out)
        # M1-68 part B2: every module checks its own configurations (and a JVM library its compile tasks), run by task path.
        for module in (":app", ":core:data", ":core:domain", ":core:testing"):
            self.assertIn(f"{module}:checkJdkRelease SKIPPED", out)

    def test_every_module_checks_its_own_configurations(self):
        for module in (":app", ":core:data"):
            with self.subTest(module=module):
                rc, out = gradle(f"{module}:checkJdkRelease", init="p.dependencies.add('implementation', p.project(':core:testing'))", project=module)
                self.assertNotEqual(rc, 0, f"gate accepted a main dependency on :core:testing in {module}:\n{out}")
                self.assertIn(f"{module}:implementation -> :core:testing", out)

    def test_non_test_dependency_on_test_support_module_fails(self):
        rc, out = gradle("checkJdkRelease", init="p.dependencies.add('implementation', p.project(':core:testing'))")
        self.assertNotEqual(rc, 0, f"gate accepted a main dependency on :core:testing:\n{out}")
        self.assertIn(":core:domain:implementation -> :core:testing", out)

    def test_the_testsupport_plugin_on_an_unlisted_module_fails(self):
        # PR 349 R1-01: tally.jvm.testsupport skips the JDK 17 compile check, so it must not work outside the
        # test-support modules that the leak check (and checkJavaApiLevel) also follow. A JVM library there passes.
        for plugin, fails in (("tally.jvm.testsupport", True), ("tally.jvm.library", False)):
            with self.subTest(plugin=plugin), tempfile.TemporaryDirectory() as d:
                with open(os.path.join(d, "build.gradle.kts"), "w") as f:
                    f.write(f'plugins {{\n    id("{plugin}")\n}}\n')
                rc, out = gradle(":fakes:checkJdkRelease", settings=SETTINGS_INIT % (ROOT, d))
                if fails:
                    self.assertNotEqual(rc, 0, f"an unlisted module got the test-support exemption:\n{out}")
                    self.assertIn("tally.jvm.testsupport is only for the test-support modules [:core:testing], not :fakes", out)
                else:
                    self.assertEqual(rc, 0, out)

    def test_test_dependency_on_test_support_module_passes(self):
        rc, out = gradle("checkJdkRelease", init="p.dependencies.add('testImplementation', p.project(':core:testing'))")
        self.assertEqual(rc, 0, out)


def _make(task, name, statement):
    def test(self):
        rc, out = gradle("checkJdkRelease", init=on_task(task.rsplit(":", 1)[1], statement))
        self.assertNotEqual(rc, 0, f"gate accepted {name}:\n{out}")
        self.assertIn(GATE_MESSAGE, out, f"{name} failed for another reason, the gate did not reject it:\n{out}")
        self.assertIn(task, out)

    return test


for _name, _stmt in KOTLIN_BAD.items():
    setattr(JdkReleaseGateTest, "test_kotlin_fails_on_" + _name.replace("-", "_"), _make(KOTLIN_TASK, _name, _stmt))
for _name, _stmt in JAVA_BAD.items():
    setattr(JdkReleaseGateTest, "test_java_fails_on_" + _name.replace("-", "_"), _make(JAVA_TASK, _name, _stmt))

if __name__ == "__main__":
    unittest.main()
