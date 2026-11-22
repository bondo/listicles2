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
    def test_hunks(self):
        for hunk, want in [("-1,0 +5,3", {5, 6, 7}), ("-3 +3", {3}), ("-4,2 +3,0", set())]:
            with self.subTest(hunk=hunk):
                self.assertEqual(ci.changed_lines(diff("a/B.kt", hunk)), {"a/B.kt": want} if want else {})

    def test_several_hunks_and_files(self):
        text = diff("a/B.kt", "-1 +1", "-9,0 +10,2") + diff("c/D.kt", "-0,0 +1,1")
        self.assertEqual(ci.changed_lines(text), {"a/B.kt": {1, 10, 11}, "c/D.kt": {1}})

    def test_deleted_file_and_empty_diff_have_no_changed_lines(self):
        text = "diff --git a/A.kt b/A.kt\ndeleted file mode 100644\n--- a/A.kt\n+++ /dev/null\n@@ -1,3 +0,0 @@\n-x\n"
        self.assertEqual((ci.changed_lines(text), ci.changed_lines("")), ({}, {}))

    def test_added_line_that_looks_like_a_file_header_is_content(self):
        text = diff("a/B.kt", "-1,0 +5,2", "-9,0 +10,1").replace("+x\n", "+++ b/other/C.kt\n+y\n", 1)
        self.assertEqual(ci.changed_lines(text), {"a/B.kt": {5, 6, 10}})

    def test_quoted_and_tab_terminated_paths_are_decoded(self):
        cases = [  # (the text after `+++ `, the path)
            ('"b/m/p/S\\303\\246t.kt"', "m/p/S\u00e6t.kt"),
            ('"b/a\\tb\\"c\\\\d.kt"', 'a\tb"c\\d.kt'),
            ("b/m/p/A B.kt\t", "m/p/A B.kt"),
        ]
        for header, path in cases:
            with self.subTest(header=header):
                self.assertEqual(ci.changed_lines(diff("x", "-1,0 +2,1").replace("+++ b/x", f"+++ {header}")), {path: {2}})


class ParseCoverage(unittest.TestCase):
    def test_lines_are_keyed_by_package_path_and_file(self):
        xml = report((DOMAIN_PKG, "Money.kt", [(3, 0, 2), (4, 1, 0)]))
        self.assertEqual(ci.coverage_lines(xml), {f"{DOMAIN_PKG}/Money.kt": {3: True, 4: False}})

    def test_line_is_covered_when_any_instruction_ran(self):
        xml = report((DOMAIN_PKG, "Money.kt", [(3, 2, 1)]))
        self.assertEqual(ci.coverage_lines(xml), {f"{DOMAIN_PKG}/Money.kt": {3: True}})

    def test_unusable_reports_are_errors(self):
        for text in (report(), report(empty=True), "<report><package", "<html/>"):
            with self.subTest(text=text[:20]), self.assertRaises(ci.CoverageError):
                ci.coverage_lines(text)


class Impact(unittest.TestCase):
    def setUp(self):
        self.cov = ci.coverage_lines(report((DOMAIN_PKG, "Money.kt", [(3, 0, 2), (4, 1, 0), (5, 1, 0), (9, 1, 0)])))
        self.path = f"{DOMAIN}/Money.kt"

    def test_only_changed_lines_with_code_are_measured_and_only_uncovered_ones_reported(self):
        cases = [  # (changed lines, reported, measured); line 3 is covered, 4, 5 and 9 are not, 1 and 2 have no code
            ({4}, {self.path: [4]}, 1),
            ({3}, {}, 1),
            ({3, 1}, {}, 1),
            ({1, 2}, {}, 0),
        ]
        for changed, reported, measured in cases:
            with self.subTest(changed=changed):
                r = ci.impact({self.path: changed}, self.cov)
                self.assertEqual((r.uncovered, r.measured), (reported, measured))

    def test_lines_come_back_sorted(self):
        self.assertEqual(ci.impact({self.path: {9, 4, 5}}, self.cov).uncovered, {self.path: [4, 5, 9]})

    def test_same_file_name_in_another_package_does_not_match(self):
        other = "core/domain/src/main/kotlin/dk/bjarkebjarke/tally/other/Money.kt"
        r = ci.impact({other: {4}}, self.cov)
        self.assertEqual(r.uncovered, {})
        self.assertEqual(r.unmeasured, [other])

    def test_only_changed_main_kotlin_files_without_a_report_entry_are_unmeasured(self):
        path = "app/src/main/kotlin/dk/bjarkebjarke/tally/Ui.kt"
        others = ("core/domain/src/test/kotlin/MoneyTest.kt", "docs/PLAN.md", "scripts/x.py", "app/src/main/res/values/strings.xml")
        self.assertEqual(ci.impact({p: {1} for p in (path, *others)}, self.cov).unmeasured, [path])


class Render(unittest.TestCase):
    def test_lines_are_collapsed_into_ranges(self):
        self.assertEqual(ci.ranges([1, 2, 3, 5, 7, 8]), "1-3, 5, 7-8")

    def test_headline_and_listing(self):
        cases = [  # (uncovered, measured, headline part, must not be in the headline)
            ({"a/B.kt": [4, 5, 9]}, 6, "3 uncovered changed lines in 1 files", None),
            ({}, 6, "6 changed executable lines, all covered", None),
            ({}, 0, "no changed executable lines", "all covered"),
        ]
        for uncovered, measured, part, absent in cases:
            with self.subTest(part=part):
                text = ci.render(ci.Impact(uncovered, measured, []))
                self.assertIn(part, text.splitlines()[0])
                self.assertNotIn(absent or "\0", text.splitlines()[0])
        self.assertIn("`a/B.kt`: 4-5, 9", ci.render(ci.Impact({"a/B.kt": [4, 5, 9]}, 6, [])))

    def test_unmeasured_files_are_listed(self):
        text = ci.render(ci.Impact(uncovered={}, measured=2, unmeasured=["app/src/main/kotlin/Ui.kt"]))
        self.assertIn("`app/src/main/kotlin/Ui.kt`", text)
        self.assertIn("no coverage data", text)


def git(cwd, *args):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=cwd, check=True, capture_output=True)


class Cli(unittest.TestCase):
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

    def measure(self, *sources, base="main"):
        """Write a report for `sources` and run the CLI against `base`."""
        self.xml.write_text(report(*sources))
        return self.run_cli("--xml", str(self.xml), "--base", base)

    def test_committed_uncovered_change_is_reported(self):
        self.src.write_text("package x\n\nfun a() = 1\nfun b() = 2\nfun c() = 3\n")
        git(self.repo, "commit", "-qam", "change")
        r = self.measure((DOMAIN_PKG, "Money.kt", [(3, 0, 1), (4, 0, 1), (5, 1, 0)]), base="HEAD~1")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(f"`{DOMAIN}/Money.kt`: 5", r.stdout)
        self.assertIn("1 uncovered", r.stdout.splitlines()[0])

    def test_uncommitted_change_is_included(self):
        self.src.write_bytes(b"package x\n\nfun a() = 1\nfun b() = 22 // caf\xe9\n")  # a Latin-1 byte: git still diffs it as text
        r = self.measure((DOMAIN_PKG, "Money.kt", [(3, 0, 1), (4, 1, 0)]), base="main")
        self.assertIn(f"`{DOMAIN}/Money.kt`: 4", r.stdout)

    def test_untracked_new_file_counts_as_all_changed(self):
        (self.src.parent / "New.kt").write_text("package x\n\nfun n() = 1\n")
        r = self.measure((DOMAIN_PKG, "New.kt", [(3, 1, 0)]), base="main")
        self.assertIn(f"`{DOMAIN}/New.kt`: 3", r.stdout)

    def test_covered_change_is_not_reported(self):
        self.src.write_text("package x\n\nfun a() = 1\nfun b() = 22\n")
        r = self.measure((DOMAIN_PKG, "Money.kt", [(3, 0, 1), (4, 0, 1)]), base="main")
        self.assertEqual(r.returncode, 0)
        self.assertIn("1 changed executable lines, all covered", r.stdout)
        self.assertNotIn("`" + DOMAIN, r.stdout)

    def test_non_ascii_and_spaced_file_names_are_reported(self):
        for name in ("S\u00e6t.kt", "A B.kt"):
            (self.src.parent / name).write_text("package x\n\nfun n() = 1\n")
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-qm", "names")
        for name in ("S\u00e6t.kt", "A B.kt"):
            (self.src.parent / name).write_text("package x\n\nfun n() = 1\nfun m() = 2\n")
        r = self.measure((DOMAIN_PKG, "S\u00e6t.kt", [(3, 0, 1), (4, 1, 0)]), (DOMAIN_PKG, "A B.kt", [(3, 0, 1), (4, 1, 0)]), base="HEAD")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(f"`{DOMAIN}/S\u00e6t.kt`: 4", r.stdout)
        self.assertIn(f"`{DOMAIN}/A B.kt`: 4", r.stdout)

    def test_untracked_nested_repository_is_skipped(self):
        nested = self.repo / ".claude" / "worktrees" / "w"
        nested.mkdir(parents=True)
        git(nested, "init", "-q")
        self.src.write_text("package x\n\nfun a() = 1\nfun b() = 22\n")
        r = self.measure((DOMAIN_PKG, "Money.kt", [(3, 0, 1), (4, 1, 0)]), base="main")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(f"`{DOMAIN}/Money.kt`: 4", r.stdout)

    def test_ignored_build_output_is_not_a_changed_file(self):
        (self.repo / ".gitignore").write_text("build/\n")
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-q", "-m", "ignore")
        built = self.repo / "app" / "build" / "generated" / "src" / "main" / "G.kt"
        built.parent.mkdir(parents=True)
        built.write_text("package x\n")
        r = self.measure((DOMAIN_PKG, "Money.kt", [(3, 0, 1)]), base="main")
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

    def test_unusable_input_fails_clearly(self):
        ok = (DOMAIN_PKG, "Money.kt", [(3, 0, 1)])
        missing = self.run_cli("--xml", str(self.xml.with_name("nope.xml")), "--base", "main")
        cases = [
            (missing, "coverage_impact: cannot read"),
            (self.measure(), "no coverage data"),
            (self.measure(ok, base="no-such-ref"), "coverage_impact: cannot diff against no-such-ref"),
        ]
        for r, message in cases:
            with self.subTest(message=message):
                self.assertEqual((r.returncode, r.stdout), (2, ""))
                self.assertIn(message, r.stderr)

    def test_usage_error(self):
        self.assertEqual(self.run_cli("--xml").returncode, 2)
        self.assertEqual(self.run_cli().returncode, 2)


def active_lines(path):
    return [ln for ln in path.read_text(encoding="utf-8").splitlines() if not ln.lstrip().startswith("#")]


LOG = '"$LOG_DIR/coverage-impact.log"'
SHOW_LINE = (
    f"  grep -qE 'uncovered changed lines|no coverage data' {LOG} 2>/dev/null && "
    f"{{ sed -n '1,12p' {LOG} | sed 's/^/      /'; [ \"$(wc -l <{LOG})\" -le 12 ] || echo \"      ... more in {LOG[1:-1]}\"; }}"
)


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
    if SHOW_LINE not in block or (wanted[1] in block and block.index(SHOW_LINE) < block.index(wanted[1])):
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


class ShowLine(unittest.TestCase):
    def shown(self, log_text):
        lines = (ROOT / "scripts" / "verify.sh").read_text(encoding="utf-8").splitlines()
        line = next(ln for ln in lines if ln.lstrip().startswith("grep") and "uncovered changed lines" in ln)
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "coverage-impact.log").write_text(log_text)
            r = subprocess.run(["bash", "-c", line], env={"LOG_DIR": tmp, "PATH": "/usr/bin:/bin"}, capture_output=True, text=True)
        return r.stdout

    def test_uncovered_lines_and_unmeasured_files_are_shown(self):
        out = self.shown(ci.render(ci.Impact({"a/B.kt": [4]}, 2, ["m/src/main/kotlin/U.kt"])))
        for part in ("1 uncovered changed lines", "`a/B.kt`: 4", "`m/src/main/kotlin/U.kt`"):
            self.assertIn(part, out)
        self.assertNotIn("more in", out)

    def test_unmeasured_files_are_shown_even_when_nothing_is_uncovered(self):
        self.assertIn("`m/src/main/kotlin/U.kt`", self.shown(ci.render(ci.Impact({}, 0, ["m/src/main/kotlin/U.kt"]))))

    def test_all_covered_prints_nothing(self):
        self.assertEqual(self.shown(ci.render(ci.Impact({}, 5, []))), "")

    def test_long_report_is_cut_and_names_the_log(self):
        out = self.shown(ci.render(ci.Impact({f"f{i}.kt": [1] for i in range(30)}, 30, [])))
        self.assertLessEqual(len(out.splitlines()), 13)
        self.assertIn("more in", out)
        self.assertIn("coverage-impact.log", out)


class Wiring(unittest.TestCase):
    def test_repo_wiring_has_no_problems(self):
        self.assertEqual(verify_problems("\n".join(active_lines(ROOT / "scripts" / "verify.sh")) + "\n"), [])
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
        show = SHOW_LINE
        cases += [
            (show + "\n", ""),
            (show, show.replace("uncovered changed lines", "- ")),
            (show, show.replace("|no coverage data", "")),
            (show, show.replace("-le 12 ] || echo", "-le 12 ] && echo")),
            (impact + show + "\n", show + "\n" + impact),
        ]
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
