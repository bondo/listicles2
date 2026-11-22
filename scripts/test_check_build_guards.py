"""Tests for scripts/check_build_guards.py (M1-51, M1-58 and M1-59, issue 257, checklist follow-ups 3, 4 and 5 in
docs/ANDROID-BEST-PRACTICES.md): catalog-only coordinates, the targetSdk floor, and manifest cleartext and backup.
Failing fixtures (the guard must report them) and passing fixtures (it must not), and checks that it does not pass vacuously on the real
repository (it must have read dependency declarations, a targetSdk and a manifest).
Run: python3 -I scripts/test_check_build_guards.py
"""

import importlib
import os
import re
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
sys.path.insert(0, HERE)

cbg = importlib.import_module("check_build_guards")


def tree(files):
    """A temporary directory holding the given {relative path: text} files; returns its path."""
    d = tempfile.mkdtemp(prefix="build-guards-")
    for rel, text in files.items():
        path = os.path.join(d, *rel.split("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
    return d


MANIFEST_NS = 'xmlns:android="http://schemas.android.com/apk/res/android"'


def manifest(app_attrs="", extra=""):
    return f'<?xml version="1.0"?>\n<manifest {MANIFEST_NS}>\n<application {app_attrs}>{extra}</application>\n</manifest>\n'


class Coordinates(unittest.TestCase):
    OK = "dependencies {\n    implementation(libs.androidx.core.ktx)\n}\n"
    JUST = "// justified: fixture project needs a literal coordinate"

    def problems(self, build_text, name="app/build.gradle.kts", extra=None):
        files = {name: build_text}
        files.update(extra or {})
        return cbg.catalog_problems(tree(files))

    def assert_flagged(self, build_text, count=1, **kw):
        found = self.problems(build_text, **kw)
        self.assertEqual(len(found), count, f"{build_text!r} -> {found}")
        self.assertTrue(all("catalog" in p for p in found), found)
        return found

    def assert_clean(self, build_text, **kw):
        self.assertEqual(self.problems(build_text, **kw), [], build_text)

    def test_catalog_references_pass(self):
        self.assert_clean(
            "dependencies {\n    implementation(libs.a)\n    implementation(platform(libs.bom))\n    testImplementation(project(\":core:testing\"))\n"
            "    debugImplementation(kotlin(\"test\"))\n    detektPlugins(libs.compose.rules.detekt)\n    add(\"classpath\", \"$coordinate:$version\")\n"
            "    implementation(libs.a) { exclude(group = \"org.x\", module = \"y\") }\n}\n"
        )

    def test_a_literal_coordinate_is_flagged_in_any_configuration(self):
        for call in (
            'implementation("androidx.core:core-ktx:1.0.0")',
            'testImplementation("io.kotest:kotest-assertions-core:6.0.0")',
            'androidTestImplementation("a.b:c:1")',
            'api("a.b:c:1")',
            'compileOnly("a.b:c:1")',
            'runtimeOnly("a.b:c:1")',
            'kapt("a.b:c:1")',
            'ksp("a.b:c:1")',
            'detektPlugins("a.b:c:1")',
            'classpath("a.b:c:1")',
            'lintChecks("a.b:c:1")',
            'robolectricAndroidAll("a.b:c:1")',  # any configuration, also one this guard has never heard of
            'customLibs("a.b:c:1")',
            '"implementation"("a.b:c:1")',
            'implementation("a.b:c")',  # no version is still a literal coordinate
            'implementation("a.b:c:1.0:classifier@aar")',
            'implementation("a.b:c:${libs.versions.x.get()}")',  # a version that bypasses the catalog entry
            'implementation(platform("a.b:c:1"))',
            'implementation(enforcedPlatform("a.b:c:1"))',
            'implementation(module("a.b:c:1"))',
            'implementation(dependencies.create("a.b:c:1"))',
            'implementation(libs.a) { because("x") }; implementation("a.b:c:1")',
            'if (ci) implementation("a.b:c:1")',
            'add("implementation", "a.b:c:1")',
            'constraints { implementation("a.b:c:1") }',
            'implementation(group = "a.b", name = "c", version = "1")',
            'implementation(name = "c", group = "a.b")',
            'implementation("a.b", "c", "1")',  # the positional group, name, version form
            'implementation(kotlin("stdlib", "2.0.0"))',  # a literal version next to the module name
        ):
            with self.subTest(call=call):
                self.assert_flagged(f"dependencies {{\n    {call}\n}}\n")

    def test_groovy_forms_are_flagged_in_dot_gradle_files(self):
        for call in (
            "implementation 'a.b:c:1'",
            'testImplementation "a.b:c:1"',
            "implementation('a.b:c:1')",
            "implementation group: 'a.b', name: 'c', version: '1'",
            "implementation([group: 'a.b', name: 'c'])",
            "classpath 'a.b:c:1'",
            "implementation platform('a.b:c:1')",
            "add 'implementation', 'a.b:c:1'",
        ):
            with self.subTest(call=call):
                self.assert_flagged(f"dependencies {{\n    {call}\n}}\n", name="lib/build.gradle")
        self.assert_flagged("dependencies {\n    implementation 'a.b:c:1', 'd.e:f:2'\n}\n", count=2, name="lib/build.gradle")
        self.assert_clean("dependencies {\n    implementation libs.a\n    testImplementation project(':core:testing')\n}\n", name="lib/build.gradle")

    def test_a_declaration_outside_a_dependencies_block_is_flagged(self):
        for text in (
            'dependencies.add("implementation", "a.b:c:1")\n',
            'project.dependencies { implementation("a.b:c:1") }\n',
            'dependencies.constraints { implementation("a.b:c:1") }\n',
            'configurations.all { resolutionStrategy { force("a.b:c:1") } }\n',
            "configurations.all { resolutionStrategy.force 'a.b:c:1' }\n",
            'configurations.all { resolutionStrategy.dependencySubstitution { substitute(module("a.b:c")).using(module("a.b:d:2")) } }\n',
            'val bom = dependencies.platform("a.b:c:1")\n',
        ):
            with self.subTest(text=text):
                self.assert_flagged(self.OK + text, count=2 if "substitute" in text else 1)

    def test_a_call_over_several_lines_is_flagged(self):
        self.assert_flagged('dependencies {\n    implementation(\n        "a.b:c:1",\n    )\n}\n')
        self.assert_flagged('dependencies {\n    implementation(\n        platform(\n            "a.b:c:1"\n        )\n    )\n}\n')
        self.assert_flagged('dependencies {\n    implementation(\n        group = "a.b",\n        name = "c",\n    )\n}\n')

    def test_a_dependency_in_a_buildscript_block_is_flagged(self):
        self.assert_flagged('buildscript { dependencies { classpath("a.b:c:1") } }\n' + self.OK)
        self.assert_flagged("buildscript {\n    dependencies {\n        classpath 'a.b:c:1'\n    }\n}\n" + self.OK, name="build.gradle")

    def test_a_literal_plugin_version_is_flagged_but_none_passes(self):
        for text in (
            'plugins {\n    id("com.example.plugin") version "1.2.3"\n}\n',
            'plugins {\n    id("com.example.plugin") version "1.2.3" apply false\n}\n',
            'plugins {\n    kotlin("jvm") version "2.0.0"\n}\n',
            'plugins {\n    id("com.example.plugin")\n        .version("1.2.3")\n}\n',
            'pluginManagement { plugins { id("com.example.plugin") version "1.2.3" } }\n',
            'pluginManagement { resolutionStrategy { eachPlugin { useVersion("1.2.3") } } }\n',
            'pluginManagement { resolutionStrategy { eachPlugin { useModule("a.b:c:1") } } }\n',
        ):
            with self.subTest(text=text):
                self.assert_flagged(text + self.OK)
        self.assert_flagged("plugins {\n    id 'com.example.plugin' version '1.2.3'\n}\n" + self.OK, name="lib/build.gradle")
        self.assert_clean(
            'plugins {\n    id("app.cash.licensee")\n    alias(libs.plugins.kover) apply false\n    `java-library`\n    kotlin("jvm")\n}\n'
            'version = "1.0"\nval v = libs.versions.kotlin.get()\neachPlugin { useVersion(System.getProperty("x")) }\n' + self.OK
        )

    def test_a_catalog_declared_in_gradle_code_is_flagged(self):
        for name in ("settings.gradle.kts", "settings.gradle"):
            with self.subTest(name=name):
                found = self.assert_flagged(
                    'dependencyResolutionManagement {\n    versionCatalogs {\n        create("tools") { from(files("tools.toml")) }\n    }\n}\n',
                    name=name,
                    extra={"app/build.gradle.kts": self.OK},
                )
                self.assertRegex(found[0], r"^settings\.gradle(\.kts)?:2: .*versionCatalogs")
        found = self.assert_flagged(  # the literal version of a library declared in code is a second problem
            'dependencyResolutionManagement { versionCatalogs {\n    create("tools") { library("x", "a.b", "c").version("1") }\n} }\n',
            count=2,
            name="settings.gradle.kts",
            extra={"app/build.gradle.kts": self.OK},
        )
        self.assertIn("literal version", found[1])
        self.assert_clean('val s = "versionCatalogs"\n' + self.OK)

    def test_comments_do_not_count(self):
        self.assert_clean('dependencies {\n    // implementation("a.b:c:1")\n    implementation(libs.a)\n}\n')
        self.assert_clean('dependencies {\n    /* implementation("a.b:c:1")\n       api("a.b:c:1") */\n    implementation(libs.a)\n}\n')
        self.assert_clean('dependencies {\n    implementation(libs.a) // was implementation("a.b:c:1")\n}\n')
        self.assert_clean('// plugins { id("x") version "1" }\n// versionCatalogs\n' + self.OK)

    def test_a_comment_opener_inside_a_string_does_not_hide_the_next_line(self):
        self.assert_flagged('val u = "http://example.com"\ndependencies {\n    implementation("a.b:c:1")\n}\n')
        self.assert_flagged('val u = "/*"\ndependencies {\n    implementation("a.b:c:1")\n}\n')

    def test_a_brace_inside_a_string_does_not_end_the_dependencies_block(self):
        self.assert_flagged('dependencies {\n    implementation(libs.a) { because("a } b") }\n    implementation("a.b:c:1")\n}\n')

    def test_strings_that_are_not_dependency_declarations_pass(self):
        self.assert_clean(
            self.OK
            + 'val allowed = "fixture:apache:1.0,fixture:mit:1.0"\nval c = licenseeCase("google", "fixture:google-a:1.0", passes = true)\n'
            + 'include(":app", ":core:domain")\ntasks.named("detekt") { dependsOn(":app:licensee") }\nval t = "-Dtally.targetSdk=$targetSdk"\n'
            + 'patched.forEach { (coordinate, version) -> add("classpath", "$coordinate:$version") }\nval m = mapOf("a" to "b")\n'
            + 'extra["x"] = file("a:b:c")\nval list = mutableListOf<String>().apply { add("a.b:c:1") }\n'
        )

    def test_a_justified_literal_passes_only_with_three_words_of_reason_in_a_comment(self):
        self.assert_clean(f'{self.OK}dependencies {{ implementation("a.b:c:1") }} {self.JUST}\n')
        self.assert_clean(f'{self.OK}dependencies {{ implementation("a.b:c:1") /* justified: fixture project needs literal */ }}\n')
        self.assert_clean(f"plugins {{ id 'x' version '1' }} {self.JUST}\n{self.OK}", name="lib/build.gradle")
        self.assert_flagged(f'{self.OK}dependencies {{ implementation("a.b:c:1") }} // justified: ok\n')
        self.assert_flagged(f'{self.OK}dependencies {{ implementation("a.b:c:1") }} // justified:\n')
        self.assert_flagged(f'{self.OK}dependencies {{ implementation("a.b:c:1") }} // justified: x y z\n')
        # The reason must be on the line of the literal, not on the line above, and in a comment, not in a string.
        self.assert_flagged(f'{self.OK}{self.JUST}\ndependencies {{ implementation("a.b:c:1") }}\n')
        self.assert_flagged(f'{self.OK}dependencies {{ implementation("a.b:c:1", "justified: fixture project needs literal") }}\n')
        # One justified literal does not waive another line.
        self.assert_flagged(f'dependencies {{\n    implementation("a.b:c:1") {self.JUST}\n    implementation("d.e:f:1")\n}}\n')

    def test_the_message_names_file_and_line(self):
        found = self.assert_flagged("// one\n// two\ndependencies {\n    implementation(\"a.b:c:1\")\n}\n")
        self.assertRegex(found[0], r"^app/build\.gradle\.kts:4: ")
        self.assertIn("a.b:c", found[0])

    def test_every_gradle_file_is_read_but_not_build_output(self):
        bad = 'dependencies { implementation("a.b:c:1") }\n'
        for name in (
            "build.gradle.kts", "core/domain/build.gradle.kts", "settings.gradle.kts", "buildSrc/src/main/kotlin/x.gradle.kts", "deep/er/mod/build.gradle",
            "init.gradle",
        ):
            with self.subTest(name=name):
                self.assert_flagged(bad, name=name, extra={"app/build.gradle.kts": self.OK})
        for name in ("app/build/tmp/build.gradle.kts", "node_modules/x/build.gradle", "app/.gradle/x.gradle.kts", "firebase/build.gradle.kts.txt"):
            with self.subTest(name=name):
                self.assert_clean(bad, name=name, extra={"app/build.gradle.kts": self.OK})

    def test_a_tree_without_gradle_files_or_declarations_does_not_pass_vacuously(self):
        for files in (
            {},
            {"README.md": "dependencies { implementation(libs.a) }\n"},
            {"app/build.gradle.kts": "plugins { alias(libs.plugins.x) }\n"},
            {"app/build.gradle.kts": "dependencies {\n}\n// dependencies { implementation(libs.a) }\n"},
            {"lib/build.gradle": "dependencies {}\nimplementation(libs.a)\n"},
        ):
            with self.subTest(files=files):
                found = cbg.catalog_problems(tree(files))
                self.assertEqual(len(found), 1, found)
                self.assertIn("vacuously", found[0])

    def test_stats_count_files_and_declarations(self):
        files = {
            "app/build.gradle.kts": self.OK + "dependencies {\n    api(libs.b)\n    testImplementation(libs.c)\n    constraints { api(libs.d) }\n}\n",
            "x/build.gradle": "dependencies {\n    implementation libs.a\n}\n",
            "y/build.gradle": "// none\n",
        }
        self.assertEqual(cbg.catalog_stats(tree(files)), (3, 5))

    def test_the_real_repository_passes_and_is_looked_at(self):
        self.assertEqual(cbg.catalog_problems(ROOT), [])
        files, declarations = cbg.catalog_stats(ROOT)
        self.assertGreaterEqual(files, 9)
        self.assertGreaterEqual(declarations, 40)


class TargetSdk(unittest.TestCase):
    def problems(self, text, name="app/build.gradle.kts"):
        return cbg.target_sdk_problems(tree({name: text}))

    def cfg(self, line):
        return f"android {{\n    defaultConfig {{\n        minSdk = 26\n        {line}\n    }}\n}}\n"

    def test_at_or_above_the_floor_passes(self):
        for v in (36, 37, 40, 100):
            with self.subTest(v=v):
                self.assertEqual(self.problems(self.cfg(f"targetSdk = {v}")), [])

    def test_below_the_floor_is_flagged(self):
        for v in (35, 34, 30, 1, 0):
            with self.subTest(v=v):
                found = self.problems(self.cfg(f"targetSdk = {v}"))
                self.assertEqual(len(found), 1, found)
                self.assertIn("targetSdk", found[0])
                self.assertRegex(found[0], r"^app/build\.gradle\.kts:4: ")

    def test_every_dsl_form_is_read(self):
        ok = {
            "targetSdk = 36": 36,
            "targetSdk=36": 36,
            "targetSdk(36)": 36,
            "targetSdkVersion(36)": 36,
            "targetSdkVersion 36": 36,
            "targetSdk 36": 36,
            "targetSdk { version = release(36) }": 36,
        }
        for line in ok:
            with self.subTest(line=line):
                self.assertEqual(self.problems(self.cfg(line)), [])
                low = re.sub(r"36", "35", line)
                self.assertEqual(len(self.problems(self.cfg(low))), 1, low)

    def test_a_groovy_build_file_is_read(self):
        """R1-01: `*.gradle` files count, not only `*.gradle.kts`."""
        self.assertEqual(len(self.problems("android { targetSdk 29 }\n", name="lib/build.gradle")), 1)
        self.assertEqual(self.problems("android { targetSdk 36 }\n", name="lib/build.gradle"), [])

    def test_the_multi_line_block_form_is_read(self):
        text = self.cfg("targetSdk {\n            version = release(35)\n        }")
        self.assertEqual(len(self.problems(text)), 1)
        self.assertEqual(self.problems(self.cfg("targetSdk {\n            version = release(37)\n        }")), [])

    def test_a_value_that_cannot_be_read_fails_closed(self):
        for line in (
            "targetSdk = libs.versions.target.get().toInt()", "targetSdk = someVariable", "targetSdkPreview = \"Z\"", "targetSdk = 36 - 1", "targetSdk = 3_5",
        ):
            with self.subTest(line=line):
                found = self.problems(self.cfg(line))
                self.assertEqual(len(found), 1, found)
                self.assertIn("targetSdk", found[0])

    def test_a_preview_target_is_flagged(self):
        self.assertEqual(len(self.problems(self.cfg("targetSdkPreview = \"Baklava\""))), 1)
        self.assertEqual(len(self.problems(self.cfg("targetSdk { version = preview(\"Baklava\") }"))), 1)

    def test_a_lower_value_anywhere_is_flagged_even_if_another_is_fine(self):
        text = (
            "android {\n    defaultConfig { targetSdk = 37 }\n    productFlavors {\n        create(\"old\") { targetSdk = 30 }\n    }\n}\n"
        )
        found = self.problems(text)
        self.assertEqual(len(found), 1, found)
        self.assertRegex(found[0], r":4: ")

    def test_a_qualified_or_setter_assignment_is_read_next_to_a_plain_one(self):
        """R1-01: these forms used to be invisible, so another plain `targetSdk = 37` made the guard pass."""
        plain = "android { defaultConfig { targetSdk = 37 } }\n"
        for low in (
            "android.defaultConfig.targetSdk = 30",
            "defaultConfig.targetSdk = 30",
            "android { productFlavors { create(\"old\") { this.targetSdk = 30 } } }",
            "android { defaultConfig { setTargetSdkVersion(30) } }",
            "android { defaultConfig { setTargetSdk(30) } }",
            "android?.defaultConfig?.targetSdk = 30",
            "android.defaultConfig.targetSdkVersion(30)",
        ):
            with self.subTest(low=low):
                found = self.problems(plain + low + "\n")
                self.assertEqual(len(found), 1, found)
                self.assertIn("below the Play minimum", found[0])
                self.assertRegex(found[0], r":2: ")

    def test_a_qualified_or_setter_assignment_at_the_floor_passes_and_counts(self):
        for ok in ("android.defaultConfig.targetSdk = 36", "this.targetSdk = 37", "defaultConfig { setTargetSdkVersion(37) }"):
            with self.subTest(ok=ok):
                self.assertEqual(self.problems(ok + "\n"), [])
                self.assertEqual(len(cbg.target_sdk_values(tree({"app/build.gradle.kts": ok + "\n"}))), 1)

    def test_a_qualified_or_setter_value_that_cannot_be_read_fails_closed(self):
        plain = "android { defaultConfig { targetSdk = 37 } }\n"
        for bad in (
            "android.defaultConfig.targetSdk = someVariable",
            "this.targetSdk = 36 - 1",
            "defaultConfig.setTargetSdkVersion(v)",
            "android.defaultConfig.targetSdkPreview = \"Z\"",
        ):
            with self.subTest(bad=bad):
                self.assertEqual(len(self.problems(plain + bad + "\n")), 1, bad)

    def test_any_other_assignment_or_call_of_target_sdk_fails_closed(self):
        """R2-01: a qualifier the statement pattern cannot parse must not hide a low target next to a plain `targetSdk = 37`."""
        plain = "android { defaultConfig { targetSdk = 37 } }\n"
        for hidden in (
            'getByName("x").targetSdk = 30',
            'productFlavors["old"].targetSdk = 30',
            "a!!.targetSdk = 30",
            "defaultConfig .targetSdk = 30",
            "defaultConfig\n    .targetSdk = 30",
            "defaultConfig\n    .setTargetSdkVersion(30)",
            "defaultConfig\n    .targetSdk\n    = 30",
            'getByName("x").targetSdk { version = release(30) }',
            "a.targetSdkVersion 30",
            "a().targetSdk(30)",
            "val targetSdk = 30",
        ):
            with self.subTest(hidden=hidden):
                found = self.problems(plain + hidden + "\n")
                self.assertEqual(len(found), 1, found)
                self.assertIn("targetSdk", found[0].replace("TargetSdk", "targetSdk"))
                self.assertRegex(found[0], r":[2-5]: ")

    def test_a_target_sdk_that_only_a_loose_pattern_sees_is_not_a_vacuous_pass(self):
        found = self.problems('getByName("x").targetSdk = 37\n')
        self.assertEqual(len(found), 1, found)  # unreadable, so there is no value to count and the problem says so

    def test_reads_of_a_qualified_target_sdk_do_not_count(self):
        text = (
            "android { defaultConfig { targetSdk = 37 } }\n"
            "val a = android.defaultConfig.targetSdk\nval b = checkNotNull(android.defaultConfig.targetSdk)\n"
            "println(android.defaultConfig.targetSdk)\nfoo(android.defaultConfig.targetSdk, 1)\nif (x == android.defaultConfig.targetSdk) {}\n"
            "if (android.defaultConfig.targetSdk == 36) {}\nval c = x.targetSdk\nval d = 1\nfun f(targetSdk: Int) = targetSdk\n"
            "val e = a.targetSdk ?: 0\nval f = a.targetSdk > 3\n"
        )
        self.assertEqual(self.problems(text), [])

    def test_comments_and_non_declarations_do_not_count(self):
        text = (
            "// targetSdk = 20\n/* targetSdk = 21 */\nandroid { defaultConfig { targetSdk = 37 } }\n"
            "val x = \"targetSdk = 22\"\nclass A(@get:Input val targetSdk: Int)\nval y = checkNotNull(android.defaultConfig.targetSdk)\n"
            "val args = \"-Dtally.targetSdk=$targetSdk\"\n"
        )
        self.assertEqual(self.problems(text), [])

    def test_a_tree_without_a_target_sdk_does_not_pass_vacuously(self):
        for files in ({}, {"app/build.gradle.kts": "android { compileSdk = 37 }\n"}, {"README.md": "targetSdk = 37\n"}):
            with self.subTest(files=files):
                found = cbg.target_sdk_problems(tree(files))
                self.assertTrue(any("no targetSdk" in p for p in found), found)

    def test_build_output_is_not_read(self):
        found = cbg.target_sdk_problems(tree({"app/build.gradle.kts": self.cfg("targetSdk = 37"), "app/build/x.gradle.kts": self.cfg("targetSdk = 20")}))
        self.assertEqual(found, [])

    def test_the_floor_is_pinned_and_a_floor_constant_cannot_quietly_drop(self):
        self.assertEqual(cbg.TARGET_SDK_FLOOR, 36)

    def test_the_real_repository_passes_and_has_a_target_sdk(self):
        self.assertEqual(cbg.target_sdk_problems(ROOT), [])
        values = cbg.target_sdk_values(ROOT)
        self.assertTrue(values and all(v >= 36 for _p, _l, v in values), values)


class Manifest(unittest.TestCase):
    RULES = 'android:dataExtractionRules="@xml/data_extraction_rules" android:fullBackupContent="@xml/backup_rules"'
    RULE_FILES = {
        "app/src/main/res/xml/data_extraction_rules.xml": "<data-extraction-rules/>",
        "app/src/main/res/xml/backup_rules.xml": "<full-backup-content/>",
    }

    def problems(self, text, name="app/src/main/AndroidManifest.xml", extra=None):
        files = {name: text}
        files.update(extra or {})
        return cbg.manifest_problems(tree(files))

    def test_backup_off_passes_with_or_without_rules(self):
        self.assertEqual(self.problems(manifest('android:allowBackup="false"')), [])
        self.assertEqual(self.problems(manifest(f'android:allowBackup="false" {self.RULES}'), extra=self.RULE_FILES), [])

    def test_backup_on_with_both_rules_and_their_files_passes(self):
        self.assertEqual(self.problems(manifest(f'android:allowBackup="true" {self.RULES}'), extra=self.RULE_FILES), [])

    def test_backup_on_without_rules_is_flagged(self):
        found = self.problems(manifest('android:allowBackup="true"'))
        self.assertEqual(len(found), 1, found)
        self.assertIn("allowBackup", found[0])

    def test_backup_on_with_only_one_rule_is_flagged(self):
        one = 'android:allowBackup="true" android:dataExtractionRules="@xml/data_extraction_rules"'
        two = 'android:allowBackup="true" android:fullBackupContent="@xml/backup_rules"'
        for attrs in (one, two):
            with self.subTest(attrs=attrs):
                found = self.problems(manifest(attrs), extra=self.RULE_FILES)
                self.assertEqual(len(found), 1, found)

    def test_a_rule_that_points_to_a_missing_file_is_flagged(self):
        found = self.problems(manifest(f'android:allowBackup="true" {self.RULES}'))
        self.assertEqual(len(found), 2, found)
        self.assertTrue(all("missing" in p for p in found), found)

    def test_a_rule_that_is_not_an_xml_resource_is_flagged(self):
        found = self.problems(
            manifest('android:allowBackup="true" android:dataExtractionRules="@string/x" android:fullBackupContent="backup.xml"'),
            extra=self.RULE_FILES,
        )
        self.assertEqual(len(found), 2, found)

    def test_no_allow_backup_attribute_means_on_and_needs_rules(self):
        self.assertEqual(len(self.problems(manifest(""))), 1)
        self.assertEqual(self.problems(manifest(self.RULES), extra=self.RULE_FILES), [])

    def test_an_overlay_manifest_without_the_attribute_inherits_the_main_one(self):
        main = {"app/src/main/AndroidManifest.xml": manifest('android:allowBackup="false"')}
        self.assertEqual(self.problems(manifest(""), name="app/src/debug/AndroidManifest.xml", extra=main), [])

    def test_an_overlay_manifest_that_turns_backup_on_is_flagged(self):
        found = self.problems(
            manifest('android:allowBackup="true"'),
            name="app/src/debug/AndroidManifest.xml",
            extra={"app/src/main/AndroidManifest.xml": manifest('android:allowBackup="false"')},
        )
        self.assertEqual(len(found), 1, found)
        self.assertIn("src/debug", found[0])

    def test_a_value_that_is_not_a_literal_fails_closed(self):
        for v in ("@bool/backup", "${allowBackup}", "TRUE ", ""):
            with self.subTest(v=v):
                self.assertEqual(len(self.problems(manifest(f'android:allowBackup="{v}"'))), 1)

    def test_true_in_any_letter_case_counts_as_true(self):
        self.assertEqual(len(self.problems(manifest('android:allowBackup="TRUE"'))), 1)
        self.assertEqual(len(self.problems(manifest('android:allowBackup="false" android:usesCleartextTraffic="True"'))), 1)

    def test_an_overlay_without_allow_backup_needs_a_main_application_that_sets_it(self):
        """R1-02: the overlay inherits the main manifest's value only when that manifest has an <application> (and is checked itself)."""
        overlay = manifest('android:label="x"')
        lib = f"<manifest {MANIFEST_NS}><uses-permission android:name=\"x\"/></manifest>"
        for main in ({}, {"app/src/main/AndroidManifest.xml": lib}):
            with self.subTest(main=list(main)):
                found = self.problems(overlay, name="app/src/release/AndroidManifest.xml", extra=main)
                self.assertEqual(len(found), 1, found)
                self.assertIn("allowBackup", found[0])
                self.assertIn("src/release", found[0])
        main = {"app/src/main/AndroidManifest.xml": manifest('android:allowBackup="false"')}
        self.assertEqual(self.problems(overlay, name="app/src/release/AndroidManifest.xml", extra=main), [])
        main = {"app/src/main/AndroidManifest.xml": manifest(f'android:allowBackup="true" {self.RULES}')}
        extra = dict(main, **self.RULE_FILES)
        self.assertEqual(self.problems(overlay, name="app/src/release/AndroidManifest.xml", extra=extra), [])

    def test_an_android_test_manifest_without_allow_backup_needs_no_main_manifest(self):
        """A library module has only the test APK's manifest (`core/data/src/androidTest`); that APK is never shipped. Setting it on still needs rules."""
        main = {"app/src/main/AndroidManifest.xml": manifest('android:allowBackup="false"')}
        name = "lib/src/androidTest/AndroidManifest.xml"
        self.assertEqual(cbg.manifest_problems(tree(dict(main, **{name: manifest("")}))), [])
        found = cbg.manifest_problems(tree(dict(main, **{name: manifest('android:allowBackup="true"')})))
        self.assertEqual(len(found), 1, found)
        self.assertIn("allowBackup", found[0])

    def test_an_overlay_of_another_module_does_not_inherit_this_modules_main_manifest(self):
        main = {"app/src/main/AndroidManifest.xml": manifest('android:allowBackup="false"')}
        found = self.problems(manifest(""), name="other/src/release/AndroidManifest.xml", extra=main)
        self.assertEqual(len(found), 1, found)

    def test_only_the_android_namespace_counts_in_a_manifest(self):
        """R1-03: `tools:` (or any other prefix) with the same local name must not hide or replace the `android:` attribute."""
        tools = 'xmlns:tools="http://schemas.android.com/tools"'

        def tm(attrs):
            return f"<manifest {MANIFEST_NS} {tools}><application {attrs}/></manifest>"
        for bad in (
            'android:allowBackup="false" android:usesCleartextTraffic="true" tools:usesCleartextTraffic="false"',
            'tools:usesCleartextTraffic="false" android:allowBackup="false" android:usesCleartextTraffic="true"',
            'android:allowBackup="true" tools:allowBackup="false"',
            'tools:allowBackup="false" android:allowBackup="true"',
            'android:allowBackup="true" tools:dataExtractionRules="@xml/data_extraction_rules" tools:fullBackupContent="@xml/backup_rules"',
        ):
            with self.subTest(bad=bad):
                found = self.problems(tm(bad), extra=self.RULE_FILES)
                self.assertEqual(len(found), 1, found)
        for ok in (
            'android:allowBackup="false" tools:usesCleartextTraffic="true"',
            'android:allowBackup="false" tools:allowBackup="true"',
            'tools:allowBackup="true" android:allowBackup="false"',
        ):
            with self.subTest(ok=ok):
                self.assertEqual(self.problems(tm(ok)), [])

    def test_only_the_android_namespace_counts_for_the_backup_rules(self):
        tools = 'xmlns:tools="http://schemas.android.com/tools"'
        text = f'<manifest {MANIFEST_NS} {tools}><application android:allowBackup="true" {self.RULES} tools:dataExtractionRules="@xml/other"/></manifest>'
        self.assertEqual(self.problems(text, extra=self.RULE_FILES), [])

    def test_network_security_config_attributes_are_not_namespaced(self):
        """R1-03: a prefixed `cleartextTrafficPermitted` cannot hide the plain one, and a prefixed one alone is not the plain one."""
        tools = 'xmlns:tools="http://schemas.android.com/tools"'
        base = {"app/src/main/AndroidManifest.xml": manifest('android:allowBackup="false"')}

        def nsc(attrs):
            return dict(base, **{"app/src/main/res/xml/nsc.xml": f"<network-security-config {tools}><base-config {attrs}/></network-security-config>"})

        for bad in (
            'cleartextTrafficPermitted="true" tools:cleartextTrafficPermitted="false"',
            'tools:cleartextTrafficPermitted="false" cleartextTrafficPermitted="true"',
        ):
            with self.subTest(bad=bad):
                found = cbg.manifest_problems(tree(nsc(bad)))
                self.assertEqual(len(found), 1, found)
        self.assertEqual(cbg.manifest_problems(tree(nsc('tools:cleartextTrafficPermitted="true"'))), [])

    def test_cleartext_traffic_is_flagged_and_false_passes(self):
        found = self.problems(manifest('android:allowBackup="false" android:usesCleartextTraffic="true"'))
        self.assertEqual(len(found), 1, found)
        self.assertIn("usesCleartextTraffic", found[0])
        self.assertEqual(self.problems(manifest('android:allowBackup="false" android:usesCleartextTraffic="false"')), [])

    def test_cleartext_traffic_that_is_not_a_literal_is_flagged(self):
        self.assertEqual(len(self.problems(manifest('android:allowBackup="false" android:usesCleartextTraffic="@bool/clear"'))), 1)
        self.assertEqual(len(self.problems(manifest('android:allowBackup="false" android:usesCleartextTraffic="${clear}"'))), 1)

    def test_cleartext_traffic_in_an_overlay_manifest_is_flagged(self):
        found = self.problems(
            manifest('android:usesCleartextTraffic="true"'),
            name="app/src/debug/AndroidManifest.xml",
            extra={"app/src/main/AndroidManifest.xml": manifest('android:allowBackup="false"')},
        )
        self.assertEqual(len(found), 1, found)

    def test_a_network_security_config_with_cleartext_permitted_is_flagged(self):
        main = {"app/src/main/AndroidManifest.xml": manifest('android:allowBackup="false" android:networkSecurityConfig="@xml/nsc"')}
        for body in (
            '<base-config cleartextTrafficPermitted="true"/>',
            '<domain-config cleartextTrafficPermitted="true"><domain>example.com</domain></domain-config>',
            '<base-config cleartextTrafficPermitted="TRUE"><trust-anchors/></base-config>',
            '<base-config cleartextTrafficPermitted="@bool/x"/>',
            '<domain-config><domain>a.com</domain><domain-config cleartextTrafficPermitted="true"><domain>b.a.com</domain></domain-config></domain-config>',
        ):
            with self.subTest(body=body):
                files = dict(main)
                files["app/src/main/res/xml/nsc.xml"] = f"<network-security-config>{body}</network-security-config>"
                found = cbg.manifest_problems(tree(files))
                self.assertEqual(len(found), 1, found)
                self.assertIn("cleartextTrafficPermitted", found[0])
                self.assertIn("nsc.xml", found[0])

    def test_the_android_test_source_set_may_allow_cleartext_for_the_emulators(self):
        """The test APK talks plain HTTP to the Auth emulator on 10.0.2.2 (`core/data/src/androidTest`) and is never shipped, so it is the
        one place where cleartext is accepted: its manifest and its network security configs."""
        nsc = '<network-security-config><base-config cleartextTrafficPermitted="true"/></network-security-config>'
        files = {
            "app/src/main/AndroidManifest.xml": manifest('android:allowBackup="false"'),
            "app/src/androidTest/AndroidManifest.xml": manifest('android:usesCleartextTraffic="true"'),
            "app/src/androidTest/res/xml/nsc.xml": nsc,
        }
        self.assertEqual(cbg.manifest_problems(tree(files)), [])

    def test_every_other_source_set_stays_checked_for_cleartext(self):
        nsc = '<network-security-config><base-config cleartextTrafficPermitted="true"/></network-security-config>'
        bad = 'android:allowBackup="false" android:usesCleartextTraffic="true"'
        for src in ("debug", "release", "main", "test", "androidTestFixtures", "androidTestDebug", "foo/androidTest", "androidTest2"):
            with self.subTest(src=src):
                base = {"app/src/main/AndroidManifest.xml": manifest('android:allowBackup="false"')}
                in_manifest = dict(base, **{f"app/src/{src}/AndroidManifest.xml": manifest(bad)})
                self.assertEqual(len(cbg.manifest_problems(tree(in_manifest))), 1)
                self.assertEqual(len(cbg.manifest_problems(tree(dict(base, **{f"app/src/{src}/res/xml/nsc.xml": nsc})))), 1)

    def test_a_malformed_android_test_manifest_still_fails_closed(self):
        files = {
            "app/src/main/AndroidManifest.xml": manifest('android:allowBackup="false"'),
            "app/src/androidTest/AndroidManifest.xml": "<manifest><application",
        }
        found = cbg.manifest_problems(tree(files))
        self.assertEqual(len(found), 1, found)
        self.assertIn("cannot parse", found[0])

    def test_a_network_security_config_in_any_source_set_is_read(self):
        files = {
            "app/src/main/AndroidManifest.xml": manifest('android:allowBackup="false"'),
            "app/src/debug/res/xml-v24/x.xml": '<network-security-config><base-config cleartextTrafficPermitted="true"/></network-security-config>',
        }
        self.assertEqual(len(cbg.manifest_problems(tree(files))), 1)

    def test_a_network_security_config_without_cleartext_passes(self):
        files = {
            "app/src/main/AndroidManifest.xml": manifest('android:allowBackup="false"'),
            "app/src/main/res/xml/nsc.xml": '<network-security-config><base-config cleartextTrafficPermitted="false"/>'
            '<domain-config><domain>a.com</domain><pin-set/></domain-config></network-security-config>',
        }
        self.assertEqual(cbg.manifest_problems(tree(files)), [])

    def test_other_xml_files_are_not_network_security_configs(self):
        files = {
            "app/src/main/AndroidManifest.xml": manifest('android:allowBackup="false"'),
            "app/src/main/res/layout/x.xml": '<LinearLayout cleartextTrafficPermitted="true"/>',
        }
        self.assertEqual(cbg.manifest_problems(tree(files)), [])

    def test_malformed_xml_fails_closed(self):
        found = self.problems("<manifest><application")
        self.assertEqual(len(found), 1, found)
        self.assertIn("cannot parse", found[0])

    def test_a_malformed_xml_resource_fails_closed(self):
        files = {
            "app/src/main/AndroidManifest.xml": manifest('android:allowBackup="false"'),
            "app/src/main/res/xml/nsc.xml": "<network-security-config><base-config",
        }
        found = cbg.manifest_problems(tree(files))
        self.assertEqual(len(found), 1, found)
        self.assertIn("nsc.xml", found[0])
        self.assertIn("cannot parse", found[0])

    def test_build_output_is_not_read(self):
        files = {
            "app/src/main/AndroidManifest.xml": manifest('android:allowBackup="false"'),
            "app/build/intermediates/merged/AndroidManifest.xml": manifest('android:allowBackup="true" android:usesCleartextTraffic="true"'),
        }
        self.assertEqual(cbg.manifest_problems(tree(files)), [])

    def test_a_library_manifest_without_an_application_element_is_not_checked(self):
        lib = f'<manifest {MANIFEST_NS}><uses-permission android:name="x"/></manifest>'
        self.assertEqual(self.problems(manifest('android:allowBackup="false"'), extra={"lib/src/main/AndroidManifest.xml": lib}), [])

    def test_a_tree_without_an_application_manifest_does_not_pass_vacuously(self):
        for files in ({}, {"lib/src/main/AndroidManifest.xml": f'<manifest {MANIFEST_NS}/>'}, {"README.md": "x"}):
            with self.subTest(files=files):
                found = cbg.manifest_problems(tree(files))
                self.assertTrue(any("no manifest" in p for p in found), found)

    def test_the_real_repository_passes_and_has_an_application_manifest(self):
        self.assertEqual(cbg.manifest_problems(ROOT), [])
        self.assertGreaterEqual(len(cbg.application_manifests(ROOT)), 1)


class CommandLine(unittest.TestCase):
    GOOD_BUILD = "android { defaultConfig { targetSdk = 36 } }\ndependencies {\n    implementation(libs.a)\n    testImplementation(libs.b)\n}\n"

    def run_cli(self, root=None):
        args = [sys.executable, "-I", os.path.join(HERE, "check_build_guards.py")] + ([root] if root else [])
        return subprocess.run(args, capture_output=True, text=True)

    def test_the_real_repository_exits_zero_with_one_summary_line(self):
        r = self.run_cli()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(len(r.stdout.strip().splitlines()), 1, r.stdout)

    def test_a_bad_tree_exits_one_and_prints_one_line_per_problem(self):
        root = tree(
            {
                "app/build.gradle.kts": "android { defaultConfig { targetSdk = 30 } }\ndependencies { implementation(libs.a) }\n",
                "lib/build.gradle": "android { targetSdk 29 }\ndependencies {\n    implementation 'a.b:c:1'\n}\n",
                "app/src/main/AndroidManifest.xml": manifest('android:allowBackup="true" android:usesCleartextTraffic="true"'),
            }
        )
        r = self.run_cli(root)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        lines = [ln for ln in r.stdout.splitlines() if ln.startswith("build-guards: ")]
        self.assertEqual(len(lines), 5, r.stdout)  # a literal coordinate, two targetSdk, cleartext, allowBackup
        self.assertTrue(any(ln.startswith("build-guards: lib/build.gradle:3: ") and "catalog" in ln for ln in lines), r.stdout)
        self.assertEqual(sum("targetSdk" in ln for ln in lines), 2, r.stdout)
        self.assertTrue(any("usesCleartextTraffic" in ln for ln in lines))
        self.assertTrue(any("allowBackup" in ln for ln in lines))

    def test_a_tree_with_only_a_bad_manifest_exits_one(self):
        root = tree({"app/build.gradle.kts": self.GOOD_BUILD, "app/src/main/AndroidManifest.xml": manifest("")})
        r = self.run_cli(root)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)

    def test_a_tree_with_only_a_literal_coordinate_exits_one(self):
        files = {
            "app/build.gradle.kts": self.GOOD_BUILD + 'dependencies { testImplementation("a.b:c:1") }\n',
            "app/src/main/AndroidManifest.xml": manifest('android:allowBackup="false"'),
        }
        r = self.run_cli(tree(files))
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertEqual(len(r.stdout.strip().splitlines()), 1, r.stdout)
        self.assertIn("catalog", r.stdout)

    def test_the_summary_line_names_the_manifests_read(self):
        files = {
            "app/build.gradle.kts": self.GOOD_BUILD,
            "app/src/main/AndroidManifest.xml": manifest('android:allowBackup="false"'),
        }
        root = tree(files)
        r = self.run_cli(root)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("1 manifest", r.stdout)
        self.assertIn("1 Gradle file", r.stdout)
        self.assertIn("2 dependency declarations", r.stdout)

    def test_an_empty_tree_exits_one(self):
        self.assertEqual(self.run_cli(tree({})).returncode, 1)


class Wiring(unittest.TestCase):
    def read(self, *parts):
        with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
            return f.read()

    def test_verify_sh_runs_the_tests_and_the_check(self):
        text = self.read("scripts", "verify.sh")
        self.assertRegex(text, r"(?m)^step build-guards-tests python3 -I scripts/test_check_build_guards\.py$")
        self.assertRegex(text, r"(?m)^step build-guards python3 -I scripts/check_build_guards\.py$")

    def test_ci_runs_the_tests_and_the_check_in_the_tasks_job(self):
        text = self.read(".github", "workflows", "ci.yml")
        m = re.search(r"(?m)^  tasks:\n(.*?)(?=^  [A-Za-z][\w-]*:\n|\Z)", text, re.S)
        self.assertIsNotNone(m)
        for cmd in ("python3 -I scripts/test_check_build_guards.py", "python3 -I scripts/check_build_guards.py"):
            self.assertRegex(m.group(1), rf"(?m)^        run: {re.escape(cmd)}$")


if __name__ == "__main__":
    unittest.main()
