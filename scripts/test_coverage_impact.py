"""Tests for scripts/coverage_impact.py (M1-07, PLAN P19). Run: python3 -I scripts/test_coverage_impact.py

The report lists changed lines that the unit tests do not execute. Missing or empty coverage data must fail clearly:
"nothing uncovered" may only ever mean "measured, and covered".
"""

import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import coverage_impact as ci  # noqa: E402  # justified: must follow the sys.path insert above

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "coverage_impact.py"
DOMAIN = "core/domain/src/main/kotlin/dk/bjarkebjarke/tally/domain"
DOMAIN_PKG = "dk/bjarkebjarke/tally/domain"


def report(*sources, empty=False):
    """A Kover (JaCoCo format) XML report. sources: (package, file, [(line, missed, covered), ...])."""
    doctype = '<!DOCTYPE report PUBLIC "-//JACOCO//DTD Report 1.1//EN" "report.dtd">'
    out = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>', doctype, '<report name="Kover">']
    for pkg, name, lines in sources:
        out.append(f'<package name="{pkg}"><sourcefile name="{name}">')
        out += [f'<line nr="{n}" mi="{mi}" ci="{cv}" mb="0" cb="0"/>' for n, mi, cv in lines]
        out.append("</sourcefile></package>")
    if empty:
        out.append("<counter type=\"LINE\" missed=\"0\" covered=\"0\"/>")
    out.append("</report>")
    return "\n".join(out)


def diff(path, *hunks):
    body = f"diff --git a/{path} b/{path}\n--- a/{path}\n+++ b/{path}\n"
    return body + "".join(f"@@ {h} @@\n+x\n" for h in hunks)


class ParseDiff(unittest.TestCase):
    def test_added_lines_of_a_hunk(self):
        self.assertEqual(ci.changed_lines(diff("a/B.kt", "-1,0 +5,3")), {"a/B.kt": {5, 6, 7}})

    def test_hunk_without_count_is_one_line(self):
        self.assertEqual(ci.changed_lines(diff("a/B.kt", "-3 +3")), {"a/B.kt": {3}})

    def test_pure_deletion_has_no_changed_lines(self):
        self.assertEqual(ci.changed_lines(diff("a/B.kt", "-4,2 +3,0")), {})

    def test_several_hunks_and_files(self):
        text = diff("a/B.kt", "-1 +1", "-9,0 +10,2") + diff("c/D.kt", "-0,0 +1,1")
        self.assertEqual(ci.changed_lines(text), {"a/B.kt": {1, 10, 11}, "c/D.kt": {1}})

    def test_deleted_file_is_ignored(self):
        text = "diff --git a/A.kt b/A.kt\ndeleted file mode 100644\n--- a/A.kt\n+++ /dev/null\n@@ -1,3 +0,0 @@\n-x\n"
        self.assertEqual(ci.changed_lines(text), {})

    def test_added_line_that_looks_like_a_file_header_is_content(self):
        text = diff("a/B.kt", "-1,0 +5,2", "-9,0 +10,1").replace("+x\n", "+++ b/other/C.kt\n+y\n", 1)
        self.assertEqual(ci.changed_lines(text), {"a/B.kt": {5, 6, 10}})

    def test_empty_diff(self):
        self.assertEqual(ci.changed_lines(""), {})


class ParseCoverage(unittest.TestCase):
    def test_lines_are_keyed_by_package_path_and_file(self):
        xml = report((DOMAIN_PKG, "Money.kt", [(3, 0, 2), (4, 1, 0)]))
        self.assertEqual(ci.coverage_lines(xml), {f"{DOMAIN_PKG}/Money.kt": {3: True, 4: False}})

    def test_line_is_covered_when_any_instruction_ran(self):
        xml = report((DOMAIN_PKG, "Money.kt", [(3, 2, 1)]))
        self.assertEqual(ci.coverage_lines(xml), {f"{DOMAIN_PKG}/Money.kt": {3: True}})

    def test_no_sources_is_an_error(self):
        with self.assertRaises(ci.CoverageError):
            ci.coverage_lines(report())

    def test_report_with_only_a_counter_is_an_error(self):
        with self.assertRaises(ci.CoverageError):
            ci.coverage_lines(report(empty=True))

    def test_malformed_xml_is_an_error(self):
        with self.assertRaises(ci.CoverageError):
            ci.coverage_lines("<report><package")

    def test_not_a_coverage_report_is_an_error(self):
        with self.assertRaises(ci.CoverageError):
            ci.coverage_lines("<html/>")


class Impact(unittest.TestCase):
    def setUp(self):
        self.cov = ci.coverage_lines(report((DOMAIN_PKG, "Money.kt", [(3, 0, 2), (4, 1, 0), (5, 1, 0), (9, 1, 0)])))
        self.path = f"{DOMAIN}/Money.kt"

    def test_changed_uncovered_line_is_reported(self):
        r = ci.impact({self.path: {4}}, self.cov)
        self.assertEqual(r.uncovered, {self.path: [4]})
        self.assertEqual(r.measured, 1)

    def test_changed_covered_line_is_not_reported(self):
        r = ci.impact({self.path: {3}}, self.cov)
        self.assertEqual(r.uncovered, {})
        self.assertEqual(r.measured, 1)

    def test_unchanged_uncovered_line_is_not_reported(self):
        r = ci.impact({self.path: {3, 1}}, self.cov)  # line 4, 5 and 9 are uncovered but not in the change
        self.assertEqual((r.uncovered, r.measured), ({}, 1))

    def test_changed_line_without_code_is_not_measured(self):
        r = ci.impact({self.path: {1, 2}}, self.cov)
        self.assertEqual((r.uncovered, r.measured), ({}, 0))

    def test_lines_come_back_sorted(self):
        self.assertEqual(ci.impact({self.path: {9, 4, 5}}, self.cov).uncovered, {self.path: [4, 5, 9]})

    def test_same_file_name_in_another_package_does_not_match(self):
        other = "core/domain/src/main/kotlin/dk/bjarkebjarke/tally/other/Money.kt"
        r = ci.impact({other: {4}}, self.cov)
        self.assertEqual(r.uncovered, {})
        self.assertEqual(r.unmeasured, [other])

    def test_changed_main_kotlin_file_without_report_entry_is_unmeasured(self):
        path = "app/src/main/kotlin/dk/bjarkebjarke/tally/Ui.kt"
        self.assertEqual(ci.impact({path: {1}}, self.cov).unmeasured, [path])

    def test_test_files_docs_and_scripts_are_not_unmeasured(self):
        changed = {p: {1} for p in ("core/domain/src/test/kotlin/MoneyTest.kt", "docs/PLAN.md", "scripts/x.py", "app/src/main/res/values/strings.xml")}
        self.assertEqual(ci.impact(changed, self.cov).unmeasured, [])


class Render(unittest.TestCase):
    def test_lines_are_collapsed_into_ranges(self):
        self.assertEqual(ci.ranges([1, 2, 3, 5, 7, 8]), "1-3, 5, 7-8")

    def test_uncovered_lines_are_listed_per_file(self):
        r = ci.Impact(uncovered={"a/B.kt": [4, 5, 9]}, measured=6, unmeasured=[])
        text = ci.render(r)
        self.assertIn("3 uncovered", text.splitlines()[0])
        self.assertIn("`a/B.kt`: 4-5, 9", text)

    def test_all_covered_says_how_many_were_measured(self):
        text = ci.render(ci.Impact(uncovered={}, measured=6, unmeasured=[]))
        self.assertIn("6 changed executable lines, all covered", text.splitlines()[0])

    def test_zero_measured_lines_is_not_reported_as_covered(self):
        first = ci.render(ci.Impact(uncovered={}, measured=0, unmeasured=[])).splitlines()[0]
        self.assertIn("no changed executable lines", first)
        self.assertNotIn("all covered", first)

    def test_unmeasured_files_are_listed(self):
        text = ci.render(ci.Impact(uncovered={}, measured=2, unmeasured=["app/src/main/kotlin/Ui.kt"]))
        self.assertIn("`app/src/main/kotlin/Ui.kt`", text)
        self.assertIn("no coverage data", text)


def git(cwd, *args):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=cwd, check=True, capture_output=True)


class Cli(unittest.TestCase):
    """The command line against a real throwaway repository."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.repo = Path(tmp.name) / "repo"
        self.repo.mkdir()
        self.xml = Path(tmp.name) / "report.xml"
        git(self.repo, "init", "-q", "-b", "main")
        self.src = self.repo / DOMAIN / "Money.kt"
        self.src.parent.mkdir(parents=True)
        self.src.write_text("package x\n\nfun a() = 1\nfun b() = 2\n")
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-q", "-m", "base")

    def run_cli(self, *args):
        return subprocess.run([sys.executable, "-I", str(SCRIPT), *args], cwd=self.repo, capture_output=True, text=True)

    def test_committed_uncovered_change_is_reported(self):
        self.src.write_text("package x\n\nfun a() = 1\nfun b() = 2\nfun c() = 3\n")
        git(self.repo, "commit", "-qam", "change")
        self.xml.write_text(report((DOMAIN_PKG, "Money.kt", [(3, 0, 1), (4, 0, 1), (5, 1, 0)])))
        r = self.run_cli("--xml", str(self.xml), "--base", "HEAD~1")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(f"`{DOMAIN}/Money.kt`: 5", r.stdout)
        self.assertIn("1 uncovered", r.stdout.splitlines()[0])

    def test_uncommitted_change_is_included(self):
        self.src.write_text("package x\n\nfun a() = 1\nfun b() = 22\n")
        self.xml.write_text(report((DOMAIN_PKG, "Money.kt", [(3, 0, 1), (4, 1, 0)])))
        r = self.run_cli("--xml", str(self.xml), "--base", "main")
        self.assertIn(f"`{DOMAIN}/Money.kt`: 4", r.stdout)

    def test_untracked_new_file_counts_as_all_changed(self):
        (self.src.parent / "New.kt").write_text("package x\n\nfun n() = 1\n")
        self.xml.write_text(report((DOMAIN_PKG, "New.kt", [(3, 1, 0)])))
        r = self.run_cli("--xml", str(self.xml), "--base", "main")
        self.assertIn(f"`{DOMAIN}/New.kt`: 3", r.stdout)

    def test_covered_change_is_not_reported(self):
        self.src.write_text("package x\n\nfun a() = 1\nfun b() = 22\n")
        self.xml.write_text(report((DOMAIN_PKG, "Money.kt", [(3, 0, 1), (4, 0, 1)])))
        r = self.run_cli("--xml", str(self.xml), "--base", "main")
        self.assertEqual(r.returncode, 0)
        self.assertIn("1 changed executable lines, all covered", r.stdout)
        self.assertNotIn("`" + DOMAIN, r.stdout)

    def test_untracked_nested_repository_is_skipped(self):
        nested = self.repo / ".claude" / "worktrees" / "w"
        nested.mkdir(parents=True)
        git(nested, "init", "-q")
        self.src.write_text("package x\n\nfun a() = 1\nfun b() = 22\n")
        self.xml.write_text(report((DOMAIN_PKG, "Money.kt", [(3, 0, 1), (4, 1, 0)])))
        r = self.run_cli("--xml", str(self.xml), "--base", "main")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(f"`{DOMAIN}/Money.kt`: 4", r.stdout)

    def test_ignored_build_output_is_not_a_changed_file(self):
        (self.repo / ".gitignore").write_text("build/\n")
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-q", "-m", "ignore")
        built = self.repo / "app" / "build" / "generated" / "src" / "main" / "G.kt"
        built.parent.mkdir(parents=True)
        built.write_text("package x\n")
        self.xml.write_text(report((DOMAIN_PKG, "Money.kt", [(3, 0, 1)])))
        r = self.run_cli("--xml", str(self.xml), "--base", "main")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("G.kt", r.stdout)

    def test_ci_merge_commit_in_a_depth_two_clone_with_head_parent_as_base(self):
        git(self.repo, "checkout", "-q", "-b", "feature")
        self.src.write_text("package x\n\nfun a() = 1\nfun b() = 2\nfun c() = 3\n")
        git(self.repo, "commit", "-qam", "feature")
        git(self.repo, "checkout", "-q", "main")
        (self.repo / "README").write_text("main moved\n")
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-q", "-m", "main moves")
        git(self.repo, "merge", "-q", "--no-ff", "-m", "pr merge commit", "feature")
        clone = self.xml.parent / "clone"
        git(self.xml.parent, "clone", "-q", "--depth", "2", f"file://{self.repo}", str(clone))
        self.xml.write_text(report((DOMAIN_PKG, "Money.kt", [(3, 0, 1), (4, 0, 1), (5, 1, 0)])))
        r = subprocess.run([sys.executable, "-I", str(SCRIPT), "--xml", str(self.xml), "--base", "HEAD^1"], cwd=clone, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(f"`{DOMAIN}/Money.kt`: 5", r.stdout)
        self.assertNotIn("README", r.stdout)

    def test_missing_report_fails_clearly(self):
        r = self.run_cli("--xml", str(self.xml.with_name("nope.xml")), "--base", "main")
        self.assertEqual(r.returncode, 2)
        self.assertIn("coverage_impact: cannot read", r.stderr)
        self.assertEqual(r.stdout, "")

    def test_empty_report_fails_clearly(self):
        self.xml.write_text(report())
        r = self.run_cli("--xml", str(self.xml), "--base", "main")
        self.assertEqual(r.returncode, 2)
        self.assertIn("no coverage data", r.stderr)
        self.assertEqual(r.stdout, "")

    def test_unknown_base_fails_clearly(self):
        self.xml.write_text(report((DOMAIN_PKG, "Money.kt", [(3, 0, 1)])))
        r = self.run_cli("--xml", str(self.xml), "--base", "no-such-ref")
        self.assertEqual(r.returncode, 2)
        self.assertIn("coverage_impact: cannot diff against no-such-ref", r.stderr)

    def test_usage_error(self):
        self.assertEqual(self.run_cli("--xml").returncode, 2)
        self.assertEqual(self.run_cli().returncode, 2)


def active_lines(path):
    return [ln for ln in path.read_text(encoding="utf-8").splitlines() if not ln.lstrip().startswith("#")]


def verify_problems(verify):
    """verify.sh must run the tests always (also with --fast) and the real report after the coverage step, outside --fast."""
    problems = []
    lines = verify.splitlines()
    if "step coverage-impact-tests python3 -I scripts/test_coverage_impact.py" not in lines:
        problems.append("verify.sh does not run the coverage impact tests as a top-level step")
    m = re.search(r"^if \[ \"\$FAST\" = 0 \]; then\n(.*?)^else\n", verify, re.S | re.M)
    block = m.group(1).splitlines() if m else []
    wanted = [
        "  step coverage-xml gradle koverXmlReport",
        "  step coverage-impact python3 -I scripts/coverage_impact.py --xml build/reports/kover/report.xml --base origin/main",
    ]
    idx = {w: block.index(w) if w in block else -1 for w in wanted}
    for w in wanted:
        if idx[w] < 0:
            problems.append(f"verify.sh full-run block lacks `{w.strip()}`")
    log = '"$LOG_DIR/coverage-impact.log"'
    show = f"  grep -q 'uncovered changed lines' {log} 2>/dev/null && sed -n '1p;3,12p' {log} | sed 's/^/      /'"
    if show not in block or (wanted[1] in block and block.index(show) < block.index(wanted[1])):
        problems.append("verify.sh does not show the uncovered lines after the coverage impact step")
    coverage = "  step coverage gradle koverVerify -x :core:domain:pitest"
    if coverage in block and all(i >= 0 for i in idx.values()) and not (block.index(coverage) < idx[wanted[0]] < idx[wanted[1]]):
        problems.append("verify.sh runs the coverage impact before the coverage step")
    return problems


CI_TESTS_STEP = "      - name: coverage impact tests (M1-07)\n        run: python3 -I scripts/test_coverage_impact.py\n"
CI_XML_STEP = (
    "      - name: test impact, uncovered changed lines (M1-07)\n"
    "        run: |\n"
    "          ./gradlew -q --console=plain koverXmlReport\n"
    '          python3 -I scripts/coverage_impact.py --xml build/reports/kover/report.xml --base HEAD^1 >> "$GITHUB_STEP_SUMMARY"\n'
)


def ci_problems(text):
    m = re.search(r"^  unit:\n(.*?)(?=^  [A-Za-z][\w-]*:\n|\Z)", text, re.S | re.M)
    if not m:
        return ["ci.yml has no unit job"]
    unit = m.group(1)
    problems = []
    if "fetch-depth: 2" not in unit:
        problems.append("unit: no two-commit checkout (the report needs HEAD^1)")
    if CI_XML_STEP not in unit:
        problems.append("unit: the coverage impact step is missing or changed")
    elif unit.index("koverVerify") > unit.index(CI_XML_STEP):
        problems.append("unit: the coverage impact step runs before the coverage step")
    if CI_TESTS_STEP not in unit:
        problems.append("unit: the coverage impact tests step is missing or changed")
    elif CI_XML_STEP in unit and unit.index(CI_TESTS_STEP) > unit.index(CI_XML_STEP):
        problems.append("unit: the coverage impact tests run after the report they test")
    if re.search(r"(?m)^\s*(?:-\s+)?if:", unit) or "continue-on-error" in unit:
        problems.append("unit: if or continue-on-error")
    return problems


class Wiring(unittest.TestCase):
    def test_repo_verify_sh(self):
        self.assertEqual(verify_problems("\n".join(active_lines(ROOT / "scripts" / "verify.sh")) + "\n"), [])

    def test_repo_ci_yml(self):
        self.assertEqual(ci_problems((ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")), [])

    def test_verify_mutations_are_flagged(self):
        good = "\n".join(active_lines(ROOT / "scripts" / "verify.sh")) + "\n"
        tests = "step coverage-impact-tests python3 -I scripts/test_coverage_impact.py"
        xml = "  step coverage-xml gradle koverXmlReport\n"
        impact = "  step coverage-impact python3 -I scripts/coverage_impact.py --xml build/reports/kover/report.xml --base origin/main\n"
        cases = [
            (tests + "\n", ""),
            (tests, "  " + tests),
            (xml, ""),
            (impact, ""),
            (impact, impact.replace("--base origin/main", "--base HEAD")),
            (xml + impact, impact + xml),
        ]
        shown = [ln for ln in good.splitlines() if "uncovered changed lines" in ln]
        self.assertEqual(len(shown), 1)
        cases += [(shown[0] + "\n", ""), (shown[0], shown[0].replace("uncovered changed lines", "- ")), (impact + shown[0] + "\n", shown[0] + "\n" + impact)]
        for old, new in cases:
            self.assertIn(old, good)
            self.assertNotEqual(verify_problems(good.replace(old, new, 1)), [], f"not flagged: {old!r} -> {new!r}")

    def test_ci_mutations_are_flagged(self):
        good = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        unit = good[good.index("\n  unit:\n") :]
        cases = [
            ("fetch-depth: 2", "fetch-depth: 1"),
            (CI_XML_STEP, ""),
            (CI_TESTS_STEP, ""),
            (CI_TESTS_STEP + CI_XML_STEP, CI_XML_STEP + CI_TESTS_STEP),
            (CI_XML_STEP, CI_XML_STEP.replace(">> ", "> ")),
            (CI_XML_STEP, CI_XML_STEP.replace("HEAD^1", "origin/main")),
            (CI_XML_STEP, CI_XML_STEP.replace("      - name:", "      - if: false\n        name:")),
            ("      - name: test-results gate tests", "      - continue-on-error: true\n        name: test-results gate tests"),
        ]
        for old, new in cases:
            self.assertIn(old, unit, old)
            mutated = good.replace(unit, unit.replace(old, new, 1), 1)
            self.assertNotEqual(ci_problems(mutated), [], f"not flagged: {old!r} -> {new!r}")


if __name__ == "__main__":
    unittest.main()
