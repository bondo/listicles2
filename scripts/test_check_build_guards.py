"""Tests for scripts/check_build_guards.py (M1-51, issue 257, checklist follow-up 4 in docs/ANDROID-BEST-PRACTICES.md): the targetSdk floor.
Failing fixtures (the guard must report them) and passing fixtures (it must not), and a check that it does not pass vacuously on the real
repository (it must have read a targetSdk). The manifest guard (M1-58) and the catalog-only coordinates guard (M1-59) add their own tests.
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


class CommandLine(unittest.TestCase):
    def run_cli(self, root=None):
        args = [sys.executable, "-I", os.path.join(HERE, "check_build_guards.py")] + ([root] if root else [])
        return subprocess.run(args, capture_output=True, text=True)

    def test_the_real_repository_exits_zero_with_one_summary_line(self):
        r = self.run_cli()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(len(r.stdout.strip().splitlines()), 1, r.stdout)

    def test_a_bad_tree_exits_one_and_prints_one_line_per_problem(self):
        root = tree({"app/build.gradle.kts": "android { defaultConfig { targetSdk = 30 } }\n", "lib/build.gradle": "android { targetSdk 29 }\n"})
        r = self.run_cli(root)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        lines = [ln for ln in r.stdout.splitlines() if ln.startswith("build-guards: ")]
        self.assertEqual(len(lines), 2, r.stdout)
        self.assertTrue(all("targetSdk" in ln for ln in lines))

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
