"""Tests for the :checkJavaApiLevel Gradle gate (M1-37, issue 228). Run: python3 -I scripts/test_java_api_level_gate.py

Needs a JDK, the Gradle wrapper and the Android SDK platform of the app's compileSdk (AGP installs it), so it is its own verify.sh step
and runs with the other Gradle gate self-tests (scripts/ci_scope.py). It uses the real api-versions.xml. The checker's own cases are in
scripts/test_check_java_api_level.py. Each source is injected into :core:domain with a Gradle init script (-I), so no tracked file changes.
Every negative case must fail with the checker's own message, so a compile error in an injection is not mistaken for the gate working.
"""

import os
import subprocess
import tempfile
import time
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
CHECKER_MESSAGE = "java-api-level:"

KOTLIN = {
    "StreamToList": (
        "package probe\nfun streamToList(s: java.util.stream.Stream<String>): List<String> = s.toList()\n"
    ),
    "NonNullElse": (
        "package probe\nfun nonNullElse(a: String?): String = java.util.Objects.requireNonNullElse(a, \"x\")\n"
    ),
}
JAVA_API_26 = (
    "package probe;\n"
    "public final class Api26 {\n"
    "    public static String f(String a) {\n"
    "        Runnable r = () -> { };\n"
    "        r.run();\n"
    "        return java.util.Objects.requireNonNull(a) + \"/\" + java.time.LocalDate.now() + java.util.Arrays.asList(1, 2).stream().count();\n"
    "    }\n"
    "}\n"
)

# Groovy init script. %s is the directory holding the injected sources; %s the statement run on the root project after it is evaluated.
INIT = """
allprojects {
    afterEvaluate { p ->
        if (p.path == ':core:domain') {
            p.kotlin.sourceSets.main.kotlin.srcDir('%s')
            p.sourceSets.main.java.srcDir('%s')
        }
    }
}
rootProject { r0 ->
    if (r0.gradle.parent == null) r0.afterEvaluate { r -> %s }  // the main build, not the included build-logic
}
"""


def gradle(*args, kotlin=None, java=None, root_statement=""):
    """Runs Gradle with the given sources added to :core:domain; returns (exit code, output)."""
    with tempfile.TemporaryDirectory() as tmp:
        for sub, files, ext in (("kotlin", kotlin or {}, ".kt"), ("java", java or {}, ".java")):
            os.makedirs(os.path.join(tmp, sub), exist_ok=True)
            for name, text in files.items():
                with open(os.path.join(tmp, sub, name + ext), "w", encoding="utf-8") as f:
                    f.write(text)
        init = os.path.join(tmp, "inject.init.gradle")
        with open(init, "w", encoding="utf-8") as f:
            f.write(INIT % (os.path.join(tmp, "kotlin"), os.path.join(tmp, "java"), root_statement))
        cmd = [os.path.join(ROOT, "gradlew"), "-q", "--console=plain", "--no-daemon", "-I", init, *args]
        # Retry only Maven/Gradle 429 (rate limit) so a throttled download is not read as a test failure.
        for attempt in range(5):
            r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
            out = r.stdout + r.stderr
            if "429" in out and "Too Many Requests" in out and attempt < 4:
                time.sleep(10 * (attempt + 1))
                continue
            return r.returncode, out


class JavaApiLevelGateTest(unittest.TestCase):
    def test_clean_build_passes(self):
        rc, out = gradle("checkJavaApiLevel")
        self.assertEqual(rc, 0, out)
        self.assertIn(CHECKER_MESSAGE, out)  # the checker really ran

    def test_api_26_calls_pass(self):
        rc, out = gradle("checkJavaApiLevel", java={"Api26": JAVA_API_26})
        self.assertEqual(rc, 0, out)

    def test_stream_to_list_fails(self):
        rc, out = gradle("checkJavaApiLevel", kotlin={"StreamToList": KOTLIN["StreamToList"]})
        self.assertNotEqual(rc, 0, out)
        self.assertIn(CHECKER_MESSAGE, out)
        self.assertIn("java/util/stream/Stream.toList()Ljava/util/List; requires API 34", out)

    def test_require_non_null_else_fails(self):
        rc, out = gradle("checkJavaApiLevel", kotlin={"NonNullElse": KOTLIN["NonNullElse"]})
        self.assertNotEqual(rc, 0, out)
        self.assertIn(CHECKER_MESSAGE, out)
        self.assertIn("java/util/Objects.requireNonNullElse", out)
        self.assertIn("requires API 30", out)

    def test_missing_api_versions_file_fails_closed(self):
        # Replaces the arguments of the real task, just before it runs, with a path that does not exist: the build must fail, not pass.
        statement = (
            "r.tasks.named('checkJavaApiLevel') { t -> t.doFirst { t.argumentProviders.clear();"
            " t.setArgs(['-I', r.projectDir.path + '/scripts/check_java_api_level.py', '--api-versions', '/nonexistent/data/api-versions.xml',"
            " '--min-sdk', '26', r.projectDir.path + '/core/domain/build/classes/kotlin/main']) } }"
        )
        # The injected closure holds the project, which the configuration cache cannot store.
        rc, out = gradle("--no-configuration-cache", "checkJavaApiLevel", root_statement=statement)
        self.assertNotEqual(rc, 0, out)
        self.assertIn("cannot check", out)
        self.assertIn("api-versions.xml", out)


if __name__ == "__main__":
    unittest.main()
