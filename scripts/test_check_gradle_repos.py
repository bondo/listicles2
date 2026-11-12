"""Tests for scripts/check_gradle_repos.py. Run: python3 -I scripts/test_check_gradle_repos.py"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_gradle_repos as c  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
GOOD_REPOS = f"""
        google {{
            content {{ includeGroupAndSubgroups("androidx") }}
        }}
        maven("{c.MIRROR}")
        mavenCentral()
"""
GOOD_PROPS = f"{c.TENTATIVES}=6\n{c.BACKOFF}=1000\n"


def settings(plugin_repos=GOOD_REPOS, dep_repos=GOOD_REPOS):
    return (
        f"pluginManagement {{\n    repositories {{{plugin_repos}    }}\n}}\n"
        f"dependencyResolutionManagement {{\n    repositories {{{dep_repos}    }}\n}}\n"
    )


class Settings(unittest.TestCase):
    def test_good_settings_pass(self):
        self.assertEqual(c.check_settings(settings()), [])

    def test_mirror_missing(self):
        bad = GOOD_REPOS.replace(f'maven("{c.MIRROR}")', "")
        self.assertIn("pluginManagement: Maven Central mirror", c.check_settings(settings(plugin_repos=bad))[0])

    def test_mirror_after_central(self):
        bad = 'google() { content { includeGroup("x") } }\nmavenCentral()\nmaven("' + c.MIRROR + '")\n'
        self.assertEqual(
            c.check_settings(settings(dep_repos=bad)),
            ["dependencyResolutionManagement: Maven Central mirror must come before mavenCentral()"],
        )

    def test_central_fallback_missing(self):
        bad = GOOD_REPOS.replace("mavenCentral()", "")
        self.assertIn("mavenCentral() fallback missing", c.check_settings(settings(dep_repos=bad))[0])

    def test_unfiltered_google(self):
        bad = f'google()\nmaven("{c.MIRROR}")\nmavenCentral()\n'
        self.assertEqual(c.check_settings(settings(plugin_repos=bad)), ["pluginManagement: google() needs a content filter"])

    def test_google_with_parentheses_and_filter_passes(self):
        ok = GOOD_REPOS.replace("google {", "google() {")
        self.assertEqual(c.check_settings(settings(plugin_repos=ok)), [])

    def test_missing_block(self):
        self.assertIn("pluginManagement: no repositories block", c.check_settings("rootProject.name = \"x\"\n"))


class Properties(unittest.TestCase):
    def test_good_properties_pass(self):
        self.assertEqual(c.check_properties(GOOD_PROPS), [])

    def test_missing_properties(self):
        self.assertEqual(len(c.check_properties("org.gradle.parallel=true\n")), 2)

    def test_too_few_retries(self):
        self.assertEqual(
            c.check_properties(f"{c.TENTATIVES}=3\n{c.BACKOFF}=1000\n"),
            [f"gradle.properties: {c.TENTATIVES}=3 is below {c.MIN_TENTATIVES}"],
        )

    def test_commented_out_does_not_count(self):
        self.assertEqual(len(c.check_properties(f"# {c.TENTATIVES}=6\n{c.BACKOFF}=1000\n")), 1)

    def test_not_a_number(self):
        self.assertEqual(len(c.check_properties(f"{c.TENTATIVES}=lots\n{c.BACKOFF}=1000\n")), 1)


class Repo(unittest.TestCase):
    def test_repo_config_passes(self):
        self.assertEqual(c.main(ROOT), 0)


if __name__ == "__main__":
    unittest.main()
