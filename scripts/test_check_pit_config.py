"""Tests for scripts/check_pit_config.py (M1-05, PLAN P16). Run: python3 -I scripts/test_check_pit_config.py

PIT with kotest-pitest runs on core/domain with a mutation score floor of 80 (owner decision, issue 15; raise later, never lower).
The checker reads the build files, so a removed plugin, a lowered or commented-out threshold, or a dropped verify.sh step fails.
"""

import os
import runpy
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
c = types.SimpleNamespace(**runpy.run_path(os.path.join(HERE, "check_pit_config.py")))


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


MUTATORS = (
    "CONDITIONALS_BOUNDARY", "INCREMENTS", "INVERT_NEGS", "MATH", "NEGATE_CONDITIONALS",
    "EMPTY_RETURNS", "FALSE_RETURNS", "TRUE_RETURNS", "NULL_RETURNS", "PRIMITIVE_RETURNS",
)  # PIT defaults minus VOID_METHOD_CALLS
GOOD_MUTATORS = "    mutators.set(listOf(" + ", ".join(f'"{m}"' for m in MUTATORS) + "))\n"

GOOD_DOMAIN = (
    "plugins {\n    alias(libs.plugins.pitest)\n}\n"
    "pitest {\n    pitestVersion.set(libs.versions.pitest.get())\n    junit5PluginVersion.set(\"1.2.3\")\n"
    + GOOD_MUTATORS +
    '    targetClasses.set(listOf("dk.bjarkebjarke.tally.domain.*"))\n    mutationThreshold.set(80)\n}\n'
)
GOOD_ROOT = "tasks.named(\"koverVerify\") { dependsOn(\":core:domain:pitest\") }\n"
GOOD_VERIFY = "if [ x ]; then\n  step mutation gradle :core:domain:pitest\nfi\n"
GOOD_CI = (
    "  tasks:\n    steps:\n"
    "      - name: pit config tests\n        run: python3 -I scripts/test_check_pit_config.py\n"
    "      - name: pit config\n        run: python3 -I scripts/check_pit_config.py\n"
)


class RealFiles(unittest.TestCase):
    def test_repository_is_wired(self):
        problems = c.problems(
            read("core", "domain", "build.gradle.kts"),
            read("build.gradle.kts"),
            read("scripts", "verify.sh"),
            read(".github", "workflows", "ci.yml"),
        )
        self.assertEqual(problems, [])


class Negative(unittest.TestCase):
    def check(self, domain=None, root=None, verify=None, ci=None):
        return c.problems(domain or GOOD_DOMAIN, root or GOOD_ROOT, verify or GOOD_VERIFY, GOOD_CI if ci is None else ci)

    def test_good_fixture_passes(self):
        self.assertEqual(self.check(), [])

    def test_threshold_below_80_fails(self):
        for t in ("79", "0", "50"):
            with self.subTest(t=t):
                self.assertTrue(self.check(domain=GOOD_DOMAIN.replace("set(80)", f"set({t})")))

    def test_threshold_above_80_is_allowed(self):
        self.assertEqual(self.check(domain=GOOD_DOMAIN.replace("set(80)", "set(85)")), [])

    def test_missing_or_commented_threshold_fails(self):
        self.assertTrue(self.check(domain=GOOD_DOMAIN.replace("    mutationThreshold.set(80)\n", "")))
        self.assertTrue(self.check(domain=GOOD_DOMAIN.replace("mutationThreshold.set(80)", "// mutationThreshold.set(80)")))

    def test_non_literal_threshold_fails(self):
        self.assertTrue(self.check(domain=GOOD_DOMAIN.replace("set(80)", "set(thr)")))

    def test_missing_plugin_or_junit5_engine_support_fails(self):
        self.assertTrue(self.check(domain=GOOD_DOMAIN.replace("alias(libs.plugins.pitest)", "")))
        self.assertTrue(self.check(domain=GOOD_DOMAIN.replace("junit5PluginVersion", "otherVersion")))

    def test_kotest_pitest_extension_is_refused(self):
        # kotest-extensions-pitest 1.2.0 needs Kotest 5 classes (io.kotest.mpp) and crashes the PIT minion on Kotest 6.
        self.assertTrue(self.check(domain=GOOD_DOMAIN + "dependencies { testImplementation(libs.kotest.pitest) }\n"))

    def test_target_must_be_domain_package(self):
        self.assertTrue(self.check(domain=GOOD_DOMAIN.replace("tally.domain.*", "tally.other.*")))

    def test_avoid_calls_and_exclusions_are_refused(self):
        # avoidCallsTo drops every mutant on a line that calls the class, so it empties the gate (review R1-02).
        for extra in (
            '    avoidCallsTo.set(setOf("kotlin.jvm.internal.Intrinsics"))\n',
            '    avoidCallsTo.set(setOf("kotlin"))\n',
            '    excludedClasses.set(listOf("dk.bjarkebjarke.tally.domain.*"))\n',
            '    excludedMethods.set(listOf("of"))\n',
            '    excludedTestClasses.set(listOf("*Test"))\n',
        ):
            with self.subTest(extra=extra):
                self.assertTrue(self.check(domain=GOOD_DOMAIN.replace("}\n", extra + "}\n")))

    def test_mutators_are_pinned_and_keep_conditionals(self):
        no_mutators = GOOD_DOMAIN.replace('    mutators.set(listOf("CONDITIONALS_BOUNDARY", "NEGATE_CONDITIONALS", "EMPTY_RETURNS"))\n', "")
        self.assertTrue(self.check(domain=no_mutators))
        self.assertTrue(self.check(domain=GOOD_DOMAIN.replace('"CONDITIONALS_BOUNDARY", ', "")))
        self.assertTrue(self.check(domain=GOOD_DOMAIN.replace('"NEGATE_CONDITIONALS"', '"NEGATE_CONDITIONALS", "VOID_METHOD_CALLS"')))

    def test_every_pinned_mutator_is_required(self):
        # R2-01: a shrunk list would silently drop arithmetic and return-value mutants.
        for name in MUTATORS:
            with self.subTest(name=name):
                shrunk = GOOD_DOMAIN.replace(f'"{name}", ', "").replace(f', "{name}"', "")
                self.assertNotEqual(shrunk, GOOD_DOMAIN)
                self.assertTrue(self.check(domain=shrunk))

    def test_only_two_conditionals_fails(self):
        two = GOOD_DOMAIN.replace(GOOD_MUTATORS, '    mutators.set(listOf("CONDITIONALS_BOUNDARY", "NEGATE_CONDITIONALS"))\n')
        self.assertTrue(self.check(domain=two))

    def test_extra_stronger_mutators_are_allowed(self):
        extra = GOOD_DOMAIN.replace('"MATH", ', '"MATH", "REMOVE_CONDITIONALS_ORDER_ELSE", ')
        self.assertEqual(self.check(domain=extra), [])

    def test_ci_must_run_checker_and_its_tests(self):
        # R1-03: CI ran neither script, so only verify.sh (not run by pre-push) noticed a removed koverVerify wiring.
        self.assertTrue(self.check(ci=""))
        self.assertTrue(self.check(ci=GOOD_CI.replace("scripts/check_pit_config.py", "scripts/other.py")))
        self.assertTrue(self.check(ci=GOOD_CI.replace("scripts/test_check_pit_config.py", "scripts/other.py")))
        self.assertTrue(self.check(ci=GOOD_CI.replace("run: ", "run: # ")))
        self.assertTrue(self.check(ci=GOOD_CI.replace("run: python3", "run: python3 -c 1; true #")))

    def test_ci_wiring_via_koverVerify_required(self):
        self.assertTrue(self.check(root="// no wiring\n"))
        self.assertTrue(self.check(root="// " + GOOD_ROOT))

    def test_verify_step_required_and_not_fast_only_skipped(self):
        self.assertTrue(self.check(verify="step unit-tests gradle test\n"))
        self.assertTrue(self.check(verify="# step mutation gradle :core:domain:pitest\n"))
        self.assertTrue(self.check(verify="step mutation gradle :core:domain:pitest || true\n"))


if __name__ == "__main__":
    unittest.main()
