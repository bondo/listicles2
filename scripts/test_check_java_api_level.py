"""Tests for scripts/check_java_api_level.py (M1-37, issue 228). Run: python3 -I scripts/test_check_java_api_level.py

The checker scans compiled JVM-module classes for references to java/ and android/ members and checks each against the SDK's
api-versions.xml for minSdk 26 (lint NewApi skips pure JVM modules). Fixtures are Java sources compiled here with
`javac --release 17`, checked against a small hand-written api-versions.xml in the real format, so no SDK is needed.
The real file is exercised end to end by scripts/test_java_api_level_gate.py (Gradle). Every bad case must fail closed.
"""

import os
import re
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
CHECKER = os.path.join(HERE, "check_java_api_level.py")

SOURCES = {
    "StreamToList": "class StreamToList { static java.util.List<String> f(java.util.stream.Stream<String> s) { return s.toList(); } }",
    "NonNullElse": "class NonNullElse { static String f(String a) { return java.util.Objects.requireNonNullElse(a, \"x\"); } }",
    "Api26": (
        "class Api26 { static Object f(String a) { Runnable r = () -> { };"
        " return java.util.Objects.requireNonNull(a) + \"/\" + java.time.LocalDate.now() + Local.id(r); } }"
        " class Local { static Object id(Object o) { return o; } }"
    ),
    "InheritedOld": "class InheritedOld { static Object f(java.util.ArrayList<String> l) { return l.stream(); } }",
    "InheritedNew": "class InheritedNew { static Object[] f(java.util.ArrayList<String> l) { return l.toArray(String[]::new); } }",
    "NewField": "class NewField { static Object f() { return System.out; } }",
    "NotInApi": "class NotInApi { static Object f() { return java.net.http.HttpClient.newHttpClient(); } }",
    "NoSuchMember": "class NoSuchMember { static Object f() { return \"x\".describeConstable(); } }",
    "NewInterface": "class NewInterface implements java.util.random.RandomGenerator { public long nextLong() { return 0; } }",
    "InheritedProject": (
        "class InheritedProject { static Object[] f(MyList l) { return l.toArray(String[]::new); } static Object g(MyList l) { return l.stream(); } }"
        " class MyList extends java.util.ArrayList<String> { }"
    ),
    "Removed": "class Removed { static void f(Thread t) { t.suspend(); } }",
    "ArrayClone": "class ArrayClone { static Object f(String[] a) { return a.clone(); } }",
}

API = """<?xml version="1.0" encoding="utf-8"?>
<api version="4">
	<sdk id="30" shortname="R-ext" name="R Extensions" reference="android/os/Build$VERSION_CODES$R"/>
	<class name="java/lang/Object" since="1">
		<method name="&lt;init>()V"/>
		<method name="toString()Ljava/lang/String;"/>
	</class>
	<class name="java/lang/String" since="1">
		<extends name="java/lang/Object"/>
		<method name="&lt;init>()V"/>
		<method name="valueOf(Ljava/lang/Object;)Ljava/lang/String;"/>
	</class>
	<class name="java/lang/System" since="1">
		<extends name="java/lang/Object"/>
		<field name="out" since="30"/>
	</class>
	<class name="java/lang/Thread" since="1">
		<extends name="java/lang/Object"/>
		<method name="suspend()V" removed="36"/>
	</class>
	<class name="java/lang/Runnable" since="1"><method name="run()V"/></class>
	<class name="java/lang/Class" since="1"><extends name="java/lang/Object"/></class>
	<class name="java/util/Collection" since="1">
		<method name="stream()Ljava/util/stream/Stream;" since="24"/>
		<method name="toArray(Ljava/util/function/IntFunction;)[Ljava/lang/Object;" since="33"/>
	</class>
	<class name="java/util/List" since="1"><extends name="java/lang/Object"/><implements name="java/util/Collection"/></class>
	<class name="java/util/ArrayList" since="1"><extends name="java/lang/Object"/><implements name="java/util/List"/></class>
	<class name="java/util/Objects" since="19">
		<extends name="java/lang/Object"/>
		<method name="requireNonNull(Ljava/lang/Object;)Ljava/lang/Object;"/>
		<method name="requireNonNullElse(Ljava/lang/Object;Ljava/lang/Object;)Ljava/lang/Object;" since="30"/>
	</class>
	<class name="java/util/stream/Stream" since="24">
		<method name="toList()Ljava/util/List;" since="34"/>
	</class>
	<class name="java/time/LocalDate" since="26">
		<extends name="java/lang/Object"/>
		<method name="now()Ljava/time/LocalDate;"/>
	</class>
</api>
"""


def run(*args):
    r = subprocess.run([sys.executable, "-I", CHECKER, *args], capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


class CheckerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.src, cls.out = (os.path.join(cls.tmp.name, d) for d in ("src", "classes"))
        os.makedirs(cls.src)
        os.makedirs(cls.out)
        for name, text in SOURCES.items():
            with open(os.path.join(cls.src, name + ".java"), "w", encoding="utf-8") as f:
                f.write(text)
        javac = subprocess.run(
            ["javac", "--release", "17", "-d", cls.out, *(os.path.join(cls.src, n + ".java") for n in SOURCES)],
            capture_output=True, text=True,
        )
        assert javac.returncode == 0, javac.stdout + javac.stderr
        cls.api = os.path.join(cls.tmp.name, "api-versions.xml")
        with open(cls.api, "w", encoding="utf-8") as f:
            f.write(API)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def check(self, name, min_sdk="26", api=None):
        return run("--api-versions", api or self.api, "--min-sdk", min_sdk, os.path.join(self.out, name + ".class"))

    def test_stream_to_list_fails(self):
        rc, out = self.check("StreamToList")
        self.assertEqual(rc, 1, out)
        self.assertIn("java/util/stream/Stream.toList()Ljava/util/List;", out)
        self.assertIn("API 34", out)

    def test_require_non_null_else_fails(self):
        rc, out = self.check("NonNullElse")
        self.assertEqual(rc, 1, out)
        self.assertIn("java/util/Objects.requireNonNullElse", out)
        self.assertIn("API 30", out)

    def test_api_26_calls_pass_lambda_and_string_concat_included(self):
        # The class has an invokedynamic lambda and string concatenation: their bootstrap methods are desugared by D8, not checked.
        rc, out = self.check("Api26")
        self.assertEqual(rc, 0, out)

    def test_the_same_call_passes_when_min_sdk_is_high_enough(self):
        self.assertEqual(self.check("StreamToList", min_sdk="34")[0], 0)
        self.assertEqual(self.check("StreamToList", min_sdk="33")[0], 1)
        self.assertEqual(self.check("NonNullElse", min_sdk="30")[0], 0)
        self.assertEqual(self.check("NonNullElse", min_sdk="29")[0], 1)

    def test_member_inherited_from_an_older_interface_passes(self):
        self.assertEqual(self.check("InheritedOld")[0], 0)

    def test_member_inherited_from_a_newer_interface_member_fails(self):
        rc, out = self.check("InheritedNew")
        self.assertEqual(rc, 1, out)
        self.assertIn("toArray", out)
        self.assertIn("API 33", out)

    def test_field_newer_than_min_sdk_fails(self):
        rc, out = self.check("NewField")
        self.assertEqual(rc, 1, out)
        self.assertIn("java/lang/System.out", out)
        self.assertIn("API 30", out)

    def test_jdk_class_missing_from_the_android_api_fails(self):
        rc, out = self.check("NotInApi")
        self.assertEqual(rc, 1, out)
        self.assertIn("java/net/http/HttpClient", out)
        self.assertIn("not in the Android API", out)

    def test_member_missing_from_a_known_class_fails(self):
        rc, out = self.check("NoSuchMember")
        self.assertEqual(rc, 1, out)
        self.assertIn("describeConstable", out)
        self.assertIn("not in the Android API", out)

    def test_implemented_interface_missing_from_the_android_api_fails(self):
        rc, out = self.check("NewInterface")
        self.assertEqual(rc, 1, out)
        self.assertIn("java/util/random/RandomGenerator", out)

    def test_member_inherited_through_a_project_class_is_resolved(self):
        rc, out = run("--api-versions", self.api, "--min-sdk", "26",
                      os.path.join(self.out, "InheritedProject.class"), os.path.join(self.out, "MyList.class"))
        self.assertEqual(rc, 1, out)
        self.assertIn("toArray", out)
        self.assertNotIn("stream", out)  # Collection.stream is API 24

    def test_member_removed_in_a_later_api_fails(self):
        # Android 16 removed Thread.suspend: the call compiles against JDK 17 and then throws NoSuchMethodError on API 36 and up.
        rc, out = self.check("Removed")
        self.assertEqual(rc, 1, out)
        self.assertIn("java/lang/Thread.suspend()V", out)
        self.assertIn("removed in API 36", out)

    def test_class_and_parent_edge_removed_in_a_later_api_fail(self):
        for label, old, new, fixture in (
            ("class", '<class name="java/time/LocalDate" since="26">', '<class name="java/time/LocalDate" since="26" removed="30">', "Api26"),
            ("edge", '<implements name="java/util/Collection"/>', '<implements name="java/util/Collection" removed="30"/>', "InheritedOld"),
        ):
            with self.subTest(label=label):
                self.assertIn(old, API)
                api = os.path.join(self.tmp.name, f"api-removed-{label}.xml")
                with open(api, "w", encoding="utf-8") as f:
                    f.write(API.replace(old, new))
                rc, out = self.check(fixture, api=api)
                self.assertEqual(rc, 1, out)
                self.assertIn("removed in API 30", out)

    def test_an_unreadable_removed_fails_closed(self):
        api = os.path.join(self.tmp.name, "api-bad-removed.xml")
        with open(api, "w", encoding="utf-8") as f:
            f.write(API.replace('removed="36"', 'removed="later"'))
        rc, out = self.check("Api26", api=api)
        self.assertEqual(rc, 2, out)
        self.assertIn("removed", out)

    def test_array_clone_is_not_an_unknown_class(self):
        self.assertEqual(self.check("ArrayClone")[0], 0)

    def test_a_directory_is_scanned_recursively_and_reports_every_class(self):
        rc, out = run("--api-versions", self.api, "--min-sdk", "26", self.out)
        self.assertEqual(rc, 1, out)
        for needle in ("Stream.toList", "requireNonNullElse", "HttpClient"):
            self.assertIn(needle, out)
        self.assertNotIn("Api26.f", out)

    def test_whole_number_levels_with_a_minor_part(self):
        for since, expected in (("26", 0), ("27", 1), ("26.1", 1), ("37.0", 1), ("25.9", 0)):
            with self.subTest(since=since):
                api = os.path.join(self.tmp.name, f"api-{since}.xml")
                with open(api, "w", encoding="utf-8") as f:
                    f.write(API.replace('requireNonNullElse(Ljava/lang/Object;Ljava/lang/Object;)Ljava/lang/Object;" since="30"',
                                        f'requireNonNullElse(Ljava/lang/Object;Ljava/lang/Object;)Ljava/lang/Object;" since="{since}"'))
                self.assertEqual(self.check("NonNullElse", api=api)[0], expected)

    def test_an_unreadable_since_fails_closed(self):
        api = os.path.join(self.tmp.name, "api-bad-since.xml")
        with open(api, "w", encoding="utf-8") as f:
            f.write(API.replace('since="30"/>\n\t</class>\n\t<class name="java/util/stream', 'since="soon"/>\n\t</class>\n\t<class name="java/util/stream'))
        rc, out = self.check("Api26", api=api)
        self.assertEqual(rc, 2, out)
        self.assertIn("since", out)

    def test_missing_api_versions_file_fails_closed(self):
        rc, out = self.check("Api26", api=os.path.join(self.tmp.name, "nope", "api-versions.xml"))
        self.assertEqual(rc, 2, out)
        self.assertIn("api-versions.xml", out)

    def test_empty_malformed_or_truncated_api_versions_file_fails_closed(self):
        for label, text in (
            ("empty", ""),
            ("not-xml", "this is not xml"),
            ("wrong-root", "<foo><class name='java/lang/Object' since='1'/></foo>"),
            ("no-anchor-classes", '<api version="4"><class name="android/Manifest" since="1"/></api>'),
            ("truncated", API[: len(API) // 2]),
        ):
            with self.subTest(label=label):
                api = os.path.join(self.tmp.name, f"api-{label}.xml")
                with open(api, "w", encoding="utf-8") as f:
                    f.write(text)
                rc, out = self.check("Api26", api=api)
                self.assertEqual(rc, 2, out)

    def test_no_class_files_fails_closed(self):
        empty = os.path.join(self.tmp.name, "empty-dir")
        os.makedirs(empty, exist_ok=True)
        rc, out = run("--api-versions", self.api, "--min-sdk", "26", empty)
        self.assertEqual(rc, 2, out)
        self.assertIn("no class files", out)
        rc, out = run("--api-versions", self.api, "--min-sdk", "26", os.path.join(self.tmp.name, "does-not-exist"))
        self.assertEqual(rc, 2, out)

    def test_corrupt_class_file_fails_closed(self):
        with open(os.path.join(self.out, "Api26.class"), "rb") as f:
            good = f.read()
        for label, data in (("bad-magic", b"NOTACLASS" * 8), ("truncated", good[:60])):
            with self.subTest(label=label):
                bad = os.path.join(self.tmp.name, f"{label}.class")
                with open(bad, "wb") as f:
                    f.write(data)
                rc, out = run("--api-versions", self.api, "--min-sdk", "26", bad)
                self.assertEqual(rc, 2, out)

    def test_usage_errors_fail_closed(self):
        self.assertEqual(run("--api-versions", self.api, self.out)[0], 2)  # no --min-sdk
        self.assertEqual(run("--min-sdk", "26", self.out)[0], 2)  # no --api-versions
        self.assertEqual(run("--api-versions", self.api, "--min-sdk", "twenty-six", self.out)[0], 2)
        self.assertEqual(run("--api-versions", self.api, "--min-sdk", "26")[0], 2)  # no paths


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


class WiringTest(unittest.TestCase):
    """Without this wiring a green verify.sh or CI would not mean the check ran."""

    def test_verify_sh_runs_the_unit_tests_and_the_gradle_check(self):
        verify = read("scripts", "verify.sh")
        for line in (
            r"step java-api-level-tests python3 -I scripts/test_check_java_api_level\.py",
            r"step java-api-level gradle checkJavaApiLevel",
        ):
            self.assertRegex(verify, rf"(?m)^{line}\s*$")

    def test_ci_runs_the_unit_tests_and_the_gradle_check(self):
        ci = read(".github", "workflows", "ci.yml")
        self.assertRegex(ci, r"(?m)^\s*run: python3 -I scripts/test_check_java_api_level\.py\s*$")
        self.assertRegex(ci, r"(?m)^\s*run: \./gradlew -q --console=plain checkJavaApiLevel\s*$")

    def test_the_gradle_gate_self_test_runs_when_its_inputs_change(self):
        scope = read("scripts", "ci_scope.py")
        self.assertRegex(scope, r"SELFTESTS = \([^)]*scripts/test_java_api_level_gate\.py")
        self.assertRegex(scope, r"RUN_FILES = \{[^}]*scripts/test_java_api_level_gate\.py")
        self.assertRegex(scope, r"RUN_FILES = \{[^}]*scripts/check_java_api_level\.py")
        self.assertIn("test_java_api_level_gate.py", read("scripts", "verify.sh"))

    def test_the_gradle_task_checks_the_jvm_modules_against_min_sdk_from_the_app(self):
        build = re.sub(r"(?m)^\s*//.*$", "", read("build.gradle.kts"))
        self.assertRegex(build, r'tasks\.register[^\n]*"checkJavaApiLevel"')
        self.assertIn("check_java_api_level.py", build)
        self.assertRegex(build, r"api-versions\.xml")
        self.assertRegex(build, r"minSdk")


if __name__ == "__main__":
    unittest.main()
