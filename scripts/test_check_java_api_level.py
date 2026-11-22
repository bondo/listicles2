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
    # Class references without a member reference (M1-56): the class is only named by a class literal, a checkcast, an instanceof, a
    # catch type, an array type or an annotation. HexFormat is API 34 in the fixture file, so each is above minSdk 26.
    "ClassLiteralNew": "class ClassLiteralNew { static Object f() { return java.util.HexFormat.class; } }",
    "ClassLiteralNotInApi": "class ClassLiteralNotInApi { static Object f() { return java.net.http.HttpClient.class; } }",
    "CheckcastNew": "class CheckcastNew { static Object f(Object o) { return (java.util.HexFormat) o; } }",
    "InstanceofNew": "class InstanceofNew { static boolean f(Object o) { return o instanceof java.util.HexFormat; } }",
    "CatchNew": "class CatchNew { static void f(Runnable r) { try { r.run(); } catch (java.io.UncheckedIOException e) { return; } } }",
    "AnewarrayNew": "class AnewarrayNew { static Object f() { return new java.util.HexFormat[0]; } }",
    "CheckcastArrayNew": "class CheckcastArrayNew { static Object f(Object o) { return (java.util.HexFormat[][]) o; } }",
    "AnnotationNew": "@FunctionalInterface interface AnnotationNew { void f(); }",  # runtime-visible; FunctionalInterface is API 34 in the fixture
    "AnnotationOnClass": "@Holder(type = java.util.HexFormat.class) class AnnotationOnClass { }",  # class-retention: RuntimeInvisibleAnnotations
    "AnnotationOnField": "class AnnotationOnField { @Holder(type = java.util.HexFormat.class) int x; }",
    "AnnotationOnMethod": "class AnnotationOnMethod { @Holder(type = java.util.HexFormat.class) void f() { } }",
    "AnnotationOnParameter": "class AnnotationOnParameter { void f(int a, @Holder(type = java.util.HexFormat.class) int b) { } }",
    "AnnotationEnumValue": "@Holder(state = Thread.State.NEW) class AnnotationEnumValue { }",
    "AnnotationNested": "@Holder(nested = @Inner(type = java.util.HexFormat.class)) class AnnotationNested { }",
    "AnnotationArray": "@Holder(types = { String.class, java.util.HexFormat.class }) class AnnotationArray { }",
    "AnnotationDefault": "@interface AnnotationDefault { Class<?> type() default java.util.HexFormat.class; }",
    "AnnotationOldTypes": (
        "@Holder(type = String.class, types = { Object.class }, name = \"n\", count = 3, flag = true, ratio = 1.5, big = 5L, ch = 'c',"
        " state = Thread.State.NEW)"
        " class AnnotationOldTypes { }"
    ),
    # Passing cases: old classes in every position, a primitive class literal and arrays, a try/finally (catch type 0), lambda, string concat.
    "ClassRefsOld": (
        "class ClassRefsOld { @Deprecated static Object f(Object o, Runnable r) { Runnable lambda = () -> { };"
        " try { r.run(); } catch (RuntimeException e) { return \"x\" + o; } finally { lambda.run(); }"
        " int[] ints = (int[]) o; String[][] grid = new String[1][1]; boolean b = o instanceof java.util.List;"
        " return String.class == o ? (Object) ints : (b ? LocalRef.class : grid); } }"
        " class LocalRef { }"
    ),
}
# The bytecode walk must step over every instruction length: a switch (padding to 4 bytes at each alignment), `wide`, and ldc_w
# (a class constant above pool index 255), each followed by a class literal that has to be reached.
for pad in range(4):
    for kind, cases in (
        ("Table", "case 1: return 1; case 2: return 2; case 3: return 3;"),
        ("Lookup", "case 1: return 1; case 100: return 2; case 10000: return 3;"),
    ):
        SOURCES[f"Switch{kind}{pad}"] = (
            f"class Switch{kind}{pad} {{ static Object f(int x) {{ {'x++; ' * pad}switch (x) {{ {cases} default: break; }}"
            f" return java.util.HexFormat.class; }} }}"
        )
SOURCES["WideLocals"] = (
    "class WideLocals { static Object f() { " + " ".join(f"int v{i} = {i};" for i in range(260)) + " v259++; v258 += v259 + v257;"
    " return java.util.HexFormat.class; } }"
)
SOURCES["LdcWide"] = (
    "class LdcWide { static Object f() { Object[] a = { " + ", ".join(f'"s{i}"' for i in range(300)) + " }; return java.util.HexFormat.class; } }"
)
SOURCES["Holder"] = (
    "@interface Holder { Class<?> type() default Object.class; Class<?>[] types() default { }; Thread.State state() default Thread.State.NEW;"
    " Inner nested() default @Inner; Inner[] more() default { }; String name() default \"\"; int count() default 0; boolean flag() default false;"
    " double ratio() default 0;"
    " long big() default 0; char ch() default 'a'; }"
)
SOURCES["Inner"] = (
    "@interface Inner { Class<?> type() default Object.class; }"
)

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
	<class name="java/lang/RuntimeException" since="1"><extends name="java/lang/Object"/></class>
	<class name="java/lang/Deprecated" since="1"/>
	<class name="java/lang/FunctionalInterface" since="34"/>
	<class name="java/lang/annotation/Annotation" since="1"/>
	<class name="java/lang/Thread$State" since="1"><extends name="java/lang/Object"/></class>
	<class name="java/io/UncheckedIOException" since="34"><extends name="java/lang/RuntimeException"/></class>
	<class name="java/util/HexFormat" since="34"><extends name="java/lang/Object"/></class>
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


def synthetic_class(code, catch_type=0):
    """A minimal class file `Synth` whose static method f()V has the given bytecode (and one catch handler of catch_type over it)."""

    def utf8(text):
        return b"\x01" + len(text).to_bytes(2, "big") + text.encode()

    pool = [utf8("Synth"), b"\x07\x00\x01", utf8("java/lang/Object"), b"\x07\x00\x03", utf8("f"), utf8("()V"), utf8("Code")]
    table = b"\x00\x01" + (0).to_bytes(2, "big") + len(code).to_bytes(2, "big") + (0).to_bytes(2, "big") + catch_type.to_bytes(2, "big")
    body = b"\x00\x01\x00\x01" + len(code).to_bytes(4, "big") + code + table + b"\x00\x00"
    method = b"\x00\x09\x00\x05\x00\x06\x00\x01\x00\x07" + len(body).to_bytes(4, "big") + body
    return (
        b"\xca\xfe\xba\xbe\x00\x00\x00\x3d" + (len(pool) + 1).to_bytes(2, "big") + b"".join(pool)
        + b"\x00\x20\x00\x02\x00\x04\x00\x00\x00\x00\x00\x01" + method + b"\x00\x00"
    )


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

    def assert_class_violation(self, name, cls="java/util/HexFormat", api="API 34", min_sdk="26"):
        rc, out = self.check(name, min_sdk=min_sdk)
        self.assertEqual(rc, 1, out)
        self.assertIn(cls, out)
        self.assertIn(api, out)
        return out

    def test_class_only_used_as_a_class_literal_fails(self):
        out = self.assert_class_violation("ClassLiteralNew")
        self.assertIn("ClassLiteralNew: class java/util/HexFormat requires API 34 (minSdk 26)", out)

    def test_class_literal_of_a_class_missing_from_the_android_api_fails(self):
        self.assert_class_violation("ClassLiteralNotInApi", cls="java/net/http/HttpClient", api="not in the Android API")

    def test_checkcast_instanceof_and_catch_targets_fail(self):
        for name in ("CheckcastNew", "InstanceofNew"):
            with self.subTest(name=name):
                self.assert_class_violation(name)
        self.assert_class_violation("CatchNew", cls="java/io/UncheckedIOException")

    def test_array_element_types_are_looked_up(self):
        for name in ("AnewarrayNew", "CheckcastArrayNew"):  # anewarray java/util/HexFormat, checkcast [[Ljava/util/HexFormat;
            with self.subTest(name=name):
                self.assert_class_violation(name)

    def test_annotation_types_fail(self):
        self.assert_class_violation("AnnotationNew", cls="java/lang/FunctionalInterface")

    def test_class_values_inside_annotations_fail_in_every_position(self):
        # Holder has class retention (RuntimeInvisibleAnnotations); the class value is a descriptor, not a constant pool Class entry.
        names = ("AnnotationOnClass", "AnnotationOnField", "AnnotationOnMethod", "AnnotationOnParameter", "AnnotationNested", "AnnotationArray")
        for name in (*names, "AnnotationDefault"):
            with self.subTest(name=name):
                self.assert_class_violation(name)

    def test_enum_type_of_an_annotation_value_is_looked_up(self):
        api = os.path.join(self.tmp.name, "api-state.xml")
        with open(api, "w", encoding="utf-8") as f:
            f.write(API.replace('<class name="java/lang/Thread$State" since="1">', '<class name="java/lang/Thread$State" since="30">'))
        rc, out = self.check("AnnotationEnumValue", api=api)
        self.assertEqual(rc, 1, out)
        self.assertIn("java/lang/Thread$State requires API 30", out)

    def test_old_classes_in_every_position_pass(self):
        for name in ("ClassRefsOld", "AnnotationOldTypes", "AnnotationEnumValue", "Api26", "Holder"):
            with self.subTest(name=name):
                rc, out = self.check(name)
                self.assertEqual(rc, 0, out)

    def test_class_references_pass_when_min_sdk_is_high_enough(self):
        names = ("ClassLiteralNew", "CheckcastNew", "InstanceofNew", "CatchNew", "AnewarrayNew", "CheckcastArrayNew")
        for name in (*names, "AnnotationNew", "AnnotationOnParameter"):
            with self.subTest(name=name):
                self.assertEqual(self.check(name, min_sdk="34")[0], 0)

    def test_class_removed_in_a_later_api_fails_as_a_missing_class(self):
        api = os.path.join(self.tmp.name, "api-class-removed.xml")
        with open(api, "w", encoding="utf-8") as f:
            f.write(API.replace('<class name="java/util/HexFormat" since="34">', '<class name="java/util/HexFormat" since="34" removed="36">'))
        rc, out = self.check("ClassLiteralNew", min_sdk="34", api=api)
        self.assertEqual(rc, 1, out)
        self.assertIn("class java/util/HexFormat was removed in API 36", out)
        self.assertIn("NoClassDefFoundError", out)

    def test_the_bytecode_walk_steps_over_switches_wide_and_ldc_w(self):
        names = [f"Switch{kind}{pad}" for kind in ("Table", "Lookup") for pad in range(4)] + ["WideLocals", "LdcWide"]
        for name in names:
            with self.subTest(name=name):
                self.assert_class_violation(name)

    def test_bytecode_that_cannot_be_walked_fails_closed(self):
        for label, code in (
            ("unknown-opcode", b"\xca\xb1"),
            ("truncated-operand", b"\x12"),
            ("truncated-switch", b"\xaa\x00\x00"),
            ("ldc-outside-the-pool", b"\x12\x63\xb1"),
            ("checkcast-outside-the-pool", b"\xc0\x00\x63\xb1"),
        ):
            with self.subTest(label=label):
                path = os.path.join(self.tmp.name, f"{label}.class")
                with open(path, "wb") as f:
                    f.write(synthetic_class(code))
                rc, out = run("--api-versions", self.api, "--min-sdk", "26", path)
                self.assertEqual(rc, 2, out)

    def test_a_minimal_synthetic_class_with_a_class_handler_passes(self):
        # ldc of the class constant #2 (Synth itself) then return: nothing above minSdk, so the walk above fails only for its own reason.
        path = os.path.join(self.tmp.name, "minimal.class")
        with open(path, "wb") as f:
            f.write(synthetic_class(b"\x12\x02\x57\xb1", catch_type=2))
        rc, out = run("--api-versions", self.api, "--min-sdk", "26", path)
        self.assertEqual(rc, 0, out)

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
