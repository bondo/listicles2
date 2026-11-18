"""Tests for scripts/check_gradle_repos.py. Run: python3 -I scripts/test_check_gradle_repos.py"""

import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_gradle_repos as c  # noqa: E402  # justified: must follow the sys.path insert above

ROOT = Path(__file__).resolve().parent.parent
GOOD_REPOS = f"""
        google {{
            content {{ includeGroupAndSubgroups("androidx") }}
        }}
        maven("{c.MIRROR}")
        mavenCentral()
"""
CHECK_CMD = "python3 -I scripts/check_gradle_repos.py"
TEST_CMD = "python3 -I scripts/test_check_gradle_repos.py"
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

    def test_line_commented_mirror_does_not_count(self):
        bad = 'google { content { includeGroup("androidx") } }\n// maven("' + c.MIRROR + '")\nmavenCentral()\n'
        self.assertIn("Maven Central mirror " + c.MIRROR + " missing", c.check_settings(settings(dep_repos=bad))[0])

    def test_block_commented_central_does_not_count(self):
        bad = 'google { content { includeGroup("androidx") } }\nmaven("' + c.MIRROR + '")\n/* mavenCentral() */\n'
        self.assertIn("mavenCentral() fallback missing", c.check_settings(settings(dep_repos=bad))[0])

    def test_commented_out_mirror_on_one_line(self):
        bad = 'google{content{includeGroup("androidx")}} // maven("' + c.MIRROR + '") mavenCentral()\n'
        self.assertNotEqual(c.check_settings(settings(dep_repos=bad)), [])

    def test_no_google_is_fine_despite_googleapis_url(self):
        ok = f'maven("{c.MIRROR}")\nmavenCentral()\n'
        self.assertEqual(c.check_settings(settings(plugin_repos=ok, dep_repos=ok)), [])

    def test_second_unfiltered_google(self):
        bad = GOOD_REPOS + "        google()\n"
        self.assertEqual(c.check_settings(settings(dep_repos=bad)), ["dependencyResolutionManagement: google() needs a content filter"])

    def test_empty_content_filter(self):
        bad = GOOD_REPOS.replace('includeGroupAndSubgroups("androidx")', "")
        self.assertEqual(c.check_settings(settings(plugin_repos=bad)), ["pluginManagement: google() needs a content filter"])

    def test_google_block_without_content(self):
        bad = f'google {{ }}\nmaven("{c.MIRROR}")\nmavenCentral()\n'
        self.assertEqual(c.check_settings(settings(plugin_repos=bad)), ["pluginManagement: google() needs a content filter"])

    def test_second_outer_block_with_unfiltered_google(self):
        bad = settings() + "dependencyResolutionManagement {\n    repositories {\n        google()\n    }\n}\n"
        self.assertEqual(c.check_settings(bad), ["dependencyResolutionManagement: google() needs a content filter"])

    def test_second_repositories_block_with_unfiltered_google(self):
        bad = settings(dep_repos=GOOD_REPOS + "    }\n    repositories {\n        google()\n")
        self.assertEqual(c.check_settings(bad), ["dependencyResolutionManagement: google() needs a content filter"])

    def test_qualified_unfiltered_google(self):
        bad = GOOD_REPOS + "        this.google()\n"
        self.assertEqual(c.check_settings(settings(plugin_repos=bad)), ["pluginManagement: google() needs a content filter"])

    def test_central_before_mirror_across_repositories_blocks(self):
        first = 'google { content { includeGroup("androidx") } }\nmavenCentral()\n'
        bad = settings(dep_repos=first + f'    }}\n    repositories {{\n        maven("{c.MIRROR}")\n')
        self.assertEqual(
            c.check_settings(bad),
            ["dependencyResolutionManagement: Maven Central mirror must come before mavenCentral()"],
        )

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


HASH = "a" * 64
GOOD_META = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<verification-metadata xmlns="https://schema.gradle.org/dependency-verification">\n'
    "   <configuration>\n      <verify-metadata>true</verify-metadata>\n      <verify-signatures>false</verify-signatures>\n"
    "   </configuration>\n   <components>\n"
    '      <component group="g" name="n" version="1">\n'
    f'         <artifact name="n-1.jar">\n            <sha256 value="{HASH}" origin="Generated by Gradle"/>\n         </artifact>\n'
    "      </component>\n   </components>\n</verification-metadata>\n"
)


class Verification(unittest.TestCase):
    def check(self, meta=GOOD_META, props=GOOD_PROPS):
        return c.check_verification(meta, props)

    def test_good_metadata_passes(self):
        self.assertEqual(self.check(), [])

    def test_missing_metadata_file(self):
        self.assertEqual(self.check(meta=None), ["verification-metadata.xml missing"])

    def test_not_xml(self):
        self.assertEqual(self.check(meta="<oops"), ["verification-metadata.xml is not well-formed XML"])

    def test_verification_switched_off_in_metadata(self):
        bad = GOOD_META.replace("<verify-metadata>true", "<verify-metadata>false")
        self.assertEqual(self.check(meta=bad), ["verification-metadata.xml: verify-metadata must be true"])

    def test_no_components(self):
        bad = GOOD_META[: GOOD_META.index("<components>")] + "<components/>\n</verification-metadata>\n"
        self.assertEqual(self.check(meta=bad), ["verification-metadata.xml: no components"])

    def test_artifact_without_sha256(self):
        bad = GOOD_META.replace(f'<sha256 value="{HASH}" origin="Generated by Gradle"/>', "")
        self.assertEqual(self.check(meta=bad), ["verification-metadata.xml: artifact n-1.jar of g:n:1 has no sha256"])

    def test_malformed_sha256_value(self):
        bad = GOOD_META.replace(HASH, "abc")
        self.assertEqual(self.check(meta=bad), ["verification-metadata.xml: artifact n-1.jar of g:n:1 has no sha256"])

    def test_trusted_artifacts_bypass(self):
        bad = GOOD_META.replace("</configuration>", '<trusted-artifacts><trust group="g"/></trusted-artifacts></configuration>')
        self.assertEqual(self.check(meta=bad), ["verification-metadata.xml: trusted-artifacts bypass verification"])

    def test_gradle_properties_switch_off(self):
        for value in ("off", "lenient"):
            self.assertEqual(
                self.check(props=GOOD_PROPS + f"org.gradle.dependency.verification={value}\n"),
                [f"gradle.properties: org.gradle.dependency.verification={value} disables verification"],
            )

    def test_gradle_properties_strict_is_fine_and_commented_off_ignored(self):
        self.assertEqual(self.check(props=GOOD_PROPS + "org.gradle.dependency.verification=strict\n"), [])
        self.assertEqual(self.check(props=GOOD_PROPS + "# org.gradle.dependency.verification=off\n"), [])


class Repo(unittest.TestCase):
    def test_repo_config_passes(self):
        self.assertEqual(c.main(ROOT), 0)


def read(*parts):
    return ROOT.joinpath(*parts).read_text(encoding="utf-8")


def active_lines(text):
    return [ln.strip() for ln in text.splitlines() if ln.strip() and not ln.strip().startswith("#")]


def runs(text, command):
    """True if an active line is exactly the command as a verify.sh `step <name> <cmd>` or a workflow `run: <cmd>`."""
    pattern = re.compile(rf"^(?:step\s+[\w-]+\s+|(?:-\s+)?run:\s+){re.escape(command)}$")
    return any(pattern.match(ln) for ln in active_lines(text))


def job(text, name):
    m = re.search(rf"^  {re.escape(name)}:\n(.*?)(?=^  [A-Za-z][\w-]*:[ \t]*(?:#.*)?$|\Z)", text, re.S | re.M)
    return m.group(1) if m else None


def wiring_problems(verify, ci):
    """Problems with how verify.sh and ci.yml run the check and its tests (both must run in verify.sh even with --fast)."""
    problems = []
    top_level = "\n".join(ln for ln in verify.splitlines() if ln == ln.lstrip())
    for cmd in (CHECK_CMD, TEST_CMD):
        if not runs(top_level, cmd):
            problems.append(f"verify.sh does not run `{cmd}` as a top-level step")
    static = job(ci, "static")
    if static is None:
        return problems + ["ci.yml has no static job"]
    for cmd in (CHECK_CMD, TEST_CMD):
        if not runs(static, cmd):
            problems.append(f"ci.yml static job does not run `{cmd}`")
    if re.search(r"(?m)^\s*(?:-\s+)?if:", static) or "continue-on-error" in static:
        problems.append("ci.yml static job has if: or continue-on-error")
    if re.search(r"(?m)^    permissions:", static) or not re.search(r"(?m)^permissions:\n  contents: read\n(?!  )", ci):
        problems.append("ci.yml permissions must stay contents: read only, with no job-level override on static")
    return problems

GOOD_VERIFY = f"step gradle-repos {CHECK_CMD}\nstep gradle-repos-tests {TEST_CMD}\nif [ x ]; then\n  step unit-tests gradle test\nfi\n"
GOOD_CI = (
    "permissions:\n  contents: read\n\njobs:\n"
    "  static:\n    name: static\n    runs-on: ubuntu-latest\n    steps:\n"
    f"      - name: gradle repos tests\n        run: {TEST_CMD}\n"
    f"      - name: gradle repos\n        run: {CHECK_CMD}\n"
    "  python-lint:\n    name: python-lint\n    runs-on: ubuntu-latest\n    steps:\n      - run: echo hi\n"
)


class Wiring(unittest.TestCase):
    def test_real_wiring_is_complete(self):
        self.assertEqual(wiring_problems(read("scripts", "verify.sh"), read(".github", "workflows", "ci.yml")), [])

    def mutated(self, verify=(), ci=()):
        v, c = GOOD_VERIFY, GOOD_CI
        for old, new in verify:
            self.assertIn(old, v)
            v = v.replace(old, new)
        for old, new in ci:
            self.assertIn(old, c)
            c = c.replace(old, new)
        return wiring_problems(v, c)

    def test_good_synthetic_wiring_passes(self):
        self.assertEqual(wiring_problems(GOOD_VERIFY, GOOD_CI), [])

    def test_check_missing_from_ci(self):
        got = self.mutated(ci=[(f"        run: {CHECK_CMD}", "        run: echo skipped")])
        self.assertEqual(got, [f"ci.yml static job does not run `{CHECK_CMD}`"])

    def test_tests_missing_from_ci(self):
        got = self.mutated(ci=[(f"        run: {TEST_CMD}", "        run: echo skipped")])
        self.assertEqual(got, [f"ci.yml static job does not run `{TEST_CMD}`"])

    def test_check_in_the_wrong_ci_job_does_not_count(self):
        moved = [(f"        run: {CHECK_CMD}\n", ""), ("      - run: echo hi\n", f"      - run: {CHECK_CMD}\n")]
        got = self.mutated(ci=moved)
        self.assertIn(f"ci.yml static job does not run `{CHECK_CMD}`", got)

    def test_commented_out_step_in_ci_does_not_count(self):
        got = self.mutated(ci=[(f"        run: {CHECK_CMD}", f"        # run: {CHECK_CMD}")])
        self.assertIn(f"ci.yml static job does not run `{CHECK_CMD}`", got)

    def test_continue_on_error_is_flagged(self):
        got = self.mutated(ci=[("  static:\n    name: static\n", "  static:\n    name: static\n    continue-on-error: true\n")])
        self.assertIn("ci.yml static job has if: or continue-on-error", got)

    def test_or_true_after_the_check_does_not_count(self):
        got = self.mutated(ci=[(f"        run: {CHECK_CMD}", f"        run: {CHECK_CMD} || true")])
        self.assertEqual(got, [f"ci.yml static job does not run `{CHECK_CMD}`"])

    def test_step_level_if_is_flagged(self):
        got = self.mutated(ci=[(f"        run: {CHECK_CMD}", f"        if: false\n        run: {CHECK_CMD}")])
        self.assertEqual(got, ["ci.yml static job has if: or continue-on-error"])

    def test_step_starting_with_if_is_flagged(self):
        step = f"      - name: gradle repos\n        run: {CHECK_CMD}"
        got = self.mutated(ci=[(step, f"      - if: false\n        name: gradle repos\n        run: {CHECK_CMD}")])
        self.assertEqual(got, ["ci.yml static job has if: or continue-on-error"])

    def test_next_job_key_with_a_comment_still_ends_the_static_job(self):
        moved = [(f"      - name: gradle repos\n        run: {CHECK_CMD}\n", ""), ("  python-lint:\n", "  python-lint: # lint\n"),
                 ("      - run: echo hi\n", f"      - run: {CHECK_CMD}\n")]
        self.assertEqual(self.mutated(ci=moved), [f"ci.yml static job does not run `{CHECK_CMD}`"])

    def test_job_level_permissions_on_static_are_flagged(self):
        got = self.mutated(ci=[("  static:\n    name: static\n", "  static:\n    name: static\n    permissions:\n      contents: write\n")])
        self.assertTrue(any("permissions" in p for p in got), got)

    def test_wider_top_level_permissions_are_flagged(self):
        got = self.mutated(ci=[("permissions:\n  contents: read\n", "permissions:\n  contents: read\n  issues: write\n")])
        self.assertTrue(any("permissions" in p for p in got), got)

    def test_check_missing_from_verify(self):
        got = self.mutated(verify=[(f"step gradle-repos {CHECK_CMD}", "")])
        self.assertEqual(got, [f"verify.sh does not run `{CHECK_CMD}` as a top-level step"])

    def test_check_moved_into_the_fast_branch_is_flagged(self):
        got = self.mutated(verify=[(f"step gradle-repos {CHECK_CMD}", f"  step gradle-repos {CHECK_CMD}")])
        self.assertEqual(got, [f"verify.sh does not run `{CHECK_CMD}` as a top-level step"])

    def test_tests_missing_from_verify(self):
        got = self.mutated(verify=[(f"step gradle-repos-tests {TEST_CMD}", "")])
        self.assertEqual(got, [f"verify.sh does not run `{TEST_CMD}` as a top-level step"])


if __name__ == "__main__":
    unittest.main()
