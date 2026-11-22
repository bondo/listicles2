"""Tests for scripts/check_build_guards.py (M1-51, issue 257, checklist follow-ups 3-5 in docs/ANDROID-BEST-PRACTICES.md).

Three guards, each with failing fixtures (the guard must report them) and passing fixtures (it must not), and a check that it does not
pass vacuously on the real repository (it must have looked at build files, dependency declarations, a targetSdk and a manifest).
  * catalog-only coordinates: no `group:artifact[:version]` string in a dependency declaration of a Gradle build file.
  * targetSdk floor: every targetSdk in a build file is a literal at or above the Play minimum (36).
  * manifest: no cleartext traffic, and `allowBackup` other than "false" needs both backup rule attributes with files that exist.
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

MANIFEST_NS = 'xmlns:android="http://schemas.android.com/apk/res/android"'


def tree(files):
    """A temporary directory holding the given {relative path: text} files; returns its path."""
    d = tempfile.mkdtemp(prefix="build-guards-")
    for rel, text in files.items():
        path = os.path.join(d, *rel.split("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
    return d


def manifest(app_attrs="", extra=""):
    return f'<?xml version="1.0"?>\n<manifest {MANIFEST_NS}>\n<application {app_attrs}>{extra}</application>\n</manifest>\n'


class Coordinates(unittest.TestCase):
    OK = "dependencies {\n    implementation(libs.androidx.core.ktx)\n}\n"

    def problems(self, build_text, name="app/build.gradle.kts", extra=None):
        files = {name: build_text}
        files.update(extra or {})
        return cbg.catalog_problems(tree(files))

    def assert_flagged(self, build_text, **kw):
        found = self.problems(build_text, **kw)
        self.assertTrue(any("catalog" in p for p in found), f"not flagged: {build_text!r} -> {found}")

    def assert_clean(self, build_text, **kw):
        self.assertEqual(self.problems(build_text, **kw), [], build_text)

    def test_catalog_references_pass(self):
        self.assert_clean(
            "dependencies {\n    implementation(libs.a)\n    implementation(platform(libs.bom))\n    testImplementation(project(\":core:testing\"))\n"
            "    debugImplementation(kotlin(\"test\"))\n    detektPlugins(libs.compose.rules.detekt)\n}\n"
        )

    def test_a_literal_coordinate_is_flagged_in_each_configuration_form(self):
        for call in (
            'implementation("androidx.core:core-ktx:1.0.0")',
            'testImplementation("io.kotest:kotest-assertions-core:6.0.0")',
            'debugImplementation("a.b:c:1")',
            'androidTestImplementation("a.b:c:1")',
            'api("a.b:c:1")',
            'compileOnly("a.b:c:1")',
            'runtimeOnly("a.b:c:1")',
            'testRuntimeOnly("a.b:c:1")',
            'kapt("a.b:c:1")',
            'ksp("a.b:c:1")',
            'detektPlugins("a.b:c:1")',
            'classpath("a.b:c:1")',
            'lintChecks("a.b:c:1")',
            'implementation(platform("a.b:c:1"))',
            'implementation(enforcedPlatform("a.b:c:1"))',
            'implementation("a.b:c")',  # no version is still a literal coordinate
            'implementation("a.b:c:1.0:classifier@aar")',
            'add("classpath", "a.b:c:1")',
            'add("implementation", "a.b:c:1")',
            '"implementation"("a.b:c:1")',
            'implementation("a.b:c:${libs.versions.x.get()}")',  # a version that bypasses the catalog entry
            'implementation(group = "a.b", name = "c", version = "1")',
            'implementation(module("a.b:c:1"))',
            'implementation(dependencies.create("a.b:c:1"))',
            'resolutionStrategy { force("a.b:c:1") }',
        ):
            with self.subTest(call=call):
                self.assert_flagged(f"dependencies {{\n    {call}\n}}\n")

    def test_a_configuration_declared_in_a_build_file_counts_wherever_it_is_used(self):
        for decl in ('val customLibs by configurations.creating', 'configurations.create("customLibs")', 'configurations.register("customLibs")'):
            with self.subTest(decl=decl):
                extra = {"lib/build.gradle.kts": decl + "\n"}
                self.assert_flagged('dependencies { customLibs("a.b:c:1") }\n', extra=extra)
                self.assert_clean('dependencies { customLibs(libs.a) }\n', extra=extra)
        self.assert_clean('dependencies { customLibs("a.b:c:1") }\ndependencies { implementation(libs.a) }\n')  # not a configuration

    def test_a_call_over_several_lines_is_flagged(self):
        self.assert_flagged('dependencies {\n    implementation(\n        "a.b:c:1",\n    )\n}\n')
        self.assert_flagged('dependencies {\n    implementation(\n        platform(\n            "a.b:c:1"\n        )\n    )\n}\n')

    def test_a_dependency_in_a_constraints_or_buildscript_block_is_flagged(self):
        self.assert_flagged('buildscript { dependencies { classpath("a.b:c:1") } }')
        self.assert_flagged('dependencies { constraints { implementation("a.b:c:1") } }')

    def test_groovy_forms_are_flagged_in_dot_gradle_files(self):
        self.assert_flagged("dependencies {\n    implementation 'a.b:c:1'\n}\n", name="app/build.gradle")
        self.assert_flagged('dependencies {\n    testImplementation "a.b:c:1"\n}\n', name="lib/build.gradle")
        self.assert_flagged("dependencies { implementation('a.b:c:1') }", name="lib/build.gradle")

    def test_a_plugin_with_a_literal_version_is_flagged_but_without_one_passes(self):
        self.assert_flagged('plugins {\n    id("com.example.plugin") version "1.2.3"\n}\n')
        self.assert_flagged('plugins {\n    kotlin("jvm") version "2.0.0"\n}\n')
        self.assert_clean('plugins {\n    id("app.cash.licensee")\n    alias(libs.plugins.kover)\n    `java-library`\n    kotlin("jvm")\n}\n' + self.OK)

    def test_a_catalog_declared_in_gradle_code_is_flagged(self):
        self.assert_flagged(
            'dependencyResolutionManagement { versionCatalogs { create("libs") { library("x", "a.b", "c").version("1") } } }\n',
            name="settings.gradle.kts",
            extra={"app/build.gradle.kts": self.OK},
        )

    def test_comments_do_not_count(self):
        self.assert_clean('dependencies {\n    // implementation("a.b:c:1")\n    implementation(libs.a)\n}\n')
        self.assert_clean('dependencies {\n    /* implementation("a.b:c:1")\n       api("a.b:c:1") */\n    implementation(libs.a)\n}\n')
        self.assert_clean('dependencies {\n    implementation(libs.a) // was implementation("a.b:c:1")\n}\n')

    def test_a_comment_opener_inside_a_string_does_not_hide_the_next_line(self):
        self.assert_flagged('val u = "http://example.com"\ndependencies {\n    implementation("a.b:c:1")\n}\n')
        self.assert_flagged('val u = "/*"\ndependencies {\n    implementation("a.b:c:1")\n}\n')

    def test_strings_that_are_not_dependency_declarations_pass(self):
        self.assert_clean(
            self.OK
            + 'val allowed = "fixture:apache:1.0,fixture:mit:1.0"\nval c = licenseeCase("google", "fixture:google-a:1.0", passes = true)\n'
            + 'include(":app", ":core:domain")\ntasks.named("detekt") { dependsOn(":app:licensee") }\nval t = "-Dtally.targetSdk=$targetSdk"\n'
            + 'patched.forEach { (coordinate, version) -> add("classpath", "$coordinate:$version") }\n'
            + 'extra["x"] = file("a:b:c")\n'
        )

    def test_a_justified_literal_passes_only_with_three_words_of_reason(self):
        self.assert_clean(f'{self.OK}dependencies {{ implementation("a.b:c:1") }} // justified: fixture project needs a literal coordinate\n')
        self.assert_flagged(f'{self.OK}dependencies {{ implementation("a.b:c:1") }} // justified: ok\n')
        self.assert_flagged(f'{self.OK}dependencies {{ implementation("a.b:c:1") }} // justified:\n')
        # The reason must be on the line of the literal, not on the line above.
        self.assert_flagged(f'{self.OK}// justified: fixture project needs a literal coordinate\ndependencies {{ implementation("a.b:c:1") }}\n')

    def test_the_message_names_file_and_line(self):
        found = self.problems("// one\n// two\ndependencies {\n    implementation(\"a.b:c:1\")\n}\n")
        self.assertEqual(len(found), 1, found)
        self.assertRegex(found[0], r"^app/build\.gradle\.kts:4: ")

    def test_every_gradle_file_is_read_but_not_build_output_or_the_catalog(self):
        bad = 'dependencies { implementation("a.b:c:1") }\n'
        for name in (
            "build.gradle.kts", "core/domain/build.gradle.kts", "settings.gradle.kts", "buildSrc/src/main/kotlin/x.gradle.kts", "deep/er/mod/build.gradle",
        ):
            with self.subTest(name=name):
                self.assert_flagged(bad, name=name, extra={"app/build.gradle.kts": self.OK})
        for name in ("app/build/tmp/build.gradle.kts", "node_modules/x/build.gradle", "app/.gradle/x.gradle.kts", "firebase/build.gradle.kts.txt"):
            with self.subTest(name=name):
                self.assert_clean(bad, name=name, extra={"app/build.gradle.kts": self.OK})

    def test_a_tree_without_declarations_does_not_pass_vacuously(self):
        for files in ({}, {"app/build.gradle.kts": "plugins { alias(libs.plugins.x) }\n"}, {"README.md": "implementation(libs.a)\n"}):
            with self.subTest(files=files):
                found = cbg.catalog_problems(tree(files))
                self.assertTrue(any("vacuous" in p or "no Gradle" in p or "no dependency" in p for p in found), found)

    def test_stats_count_files_and_declarations(self):
        files, declarations = cbg.catalog_stats(tree({"app/build.gradle.kts": self.OK + "dependencies { api(libs.b) }\n", "x/build.gradle": "// none\n"}))
        self.assertEqual((files, declarations), (2, 2))

    def test_the_real_repository_passes_and_is_looked_at(self):
        self.assertEqual(cbg.catalog_problems(ROOT), [])
        files, declarations = cbg.catalog_stats(ROOT)
        self.assertGreaterEqual(files, 5)
        self.assertGreaterEqual(declarations, 20)


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
                "app/build.gradle.kts": 'android { defaultConfig { targetSdk = 30 } }\ndependencies { implementation("a.b:c:1") }\n',
                "app/src/main/AndroidManifest.xml": manifest('android:allowBackup="true" android:usesCleartextTraffic="true"'),
            }
        )
        r = self.run_cli(root)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        lines = [ln for ln in r.stdout.splitlines() if ln.startswith("build-guards: ")]
        self.assertEqual(len(lines), 4, r.stdout)  # coordinate, targetSdk, cleartext, allowBackup
        self.assertTrue(any("catalog" in ln for ln in lines))
        self.assertTrue(any("targetSdk" in ln for ln in lines))
        self.assertTrue(any("usesCleartextTraffic" in ln for ln in lines))
        self.assertTrue(any("allowBackup" in ln for ln in lines))

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
