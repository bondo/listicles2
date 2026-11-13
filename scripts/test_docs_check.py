"""Tests for scripts/docs_check.py (M0.5-12). Run: python3 -I scripts/test_docs_check.py

The checker must pass on good docs, fail on each kind of bad input, and pass on the real repository docs.
"""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import docs_check  # noqa: E402  # justified: must follow the sys.path insert above

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "docs_check.py"


class Repo:
    """A throwaway repo tree: files maps relative path to text; an empty-string file is created empty."""

    def __init__(self, files, allow=None):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        for rel, text in files.items():
            p = self.root / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text, encoding="utf-8")
        self.allow = self.root / "scripts" / "docs_check_allowlist.txt"
        if allow is not None:
            self.allow.parent.mkdir(parents=True, exist_ok=True)
            self.allow.write_text(allow, encoding="utf-8")

    def check(self):
        return docs_check.check(self.root, self.allow)

    def kinds(self):
        return sorted(p.kind for p in self.check())

    def close(self):
        self.tmp.cleanup()


class Base(unittest.TestCase):
    def repo(self, files, allow=None):
        r = Repo(files, allow)
        self.addCleanup(r.close)
        return r


class GoodDocs(Base):
    def test_existing_relative_link_and_path(self):
        r = self.repo({"docs/A.md": "See [b](B.md) and `scripts/x.py`.\n", "docs/B.md": "", "scripts/x.py": ""})
        self.assertEqual(r.check(), [])

    def test_link_with_anchor_and_title(self):
        r = self.repo({"docs/A.md": '[b](B.md#section "title") [c](sub/C.md?x=1#y)\n', "docs/B.md": "", "docs/sub/C.md": ""})
        self.assertEqual(r.check(), [])

    def test_parent_relative_link(self):
        r = self.repo({"docs/sub/A.md": "[up](../B.md)\n", "docs/B.md": ""})
        self.assertEqual(r.check(), [])

    def test_external_and_anchor_links_ignored(self):
        text = "[w](https://example.com/nope.md) [m](mailto:a@b.c) [a](#here) [h](http://x/y/z.md)\n"
        self.assertEqual(self.repo({"docs/A.md": text}).check(), [])

    def test_link_to_directory(self):
        self.assertEqual(self.repo({"docs/A.md": "[d](adr/)\n", "docs/adr/x.md": ""}).check(), [])

    def test_path_with_line_suffix(self):
        r = self.repo({"docs/A.md": "`scripts/x.py:12` `scripts/x.py:3-9` `scripts/x.py#L4`\n", "scripts/x.py": ""})
        self.assertEqual(r.check(), [])

    def test_path_relative_to_doc_dir(self):
        self.assertEqual(self.repo({"docs/A.md": "`adr/x.md`\n", "docs/adr/x.md": ""}).check(), [])

    def test_directory_path(self):
        self.assertEqual(self.repo({"docs/A.md": "`scripts/hooks/`\n", "scripts/hooks/h.py": ""}).check(), [])

    def test_not_paths_are_ignored(self):
        text = "`and/or` `a/b` `git push origin foo/bar` `src/*.kt` `docs/<name>.md` `docs/{a,b}.md` `$HOME/x.md` `~/x.md` `/abs/x.md`\n"
        self.assertEqual(self.repo({"docs/A.md": text, "docs/z.md": ""}).check(), [])

    def test_fenced_code_and_html_comments_ignored(self):
        text = "```\n[x](nope.md) `docs/nope.md`\n```\n<!-- [y](nope2.md) `docs/nope2.md` -->\n~~~\n`docs/nope3.md`\n~~~\n"
        self.assertEqual(self.repo({"docs/A.md": text}).check(), [])

    def test_inline_link_inside_code_span_is_not_a_link(self):
        self.assertEqual(self.repo({"docs/A.md": "`[x](nope.md)`\n"}).check(), [])

    def test_allowlisted_planned_path(self):
        r = self.repo({"docs/A.md": "Later: `docs/milestones/M1.md` and [x](later.md).\n"},
                      allow="docs/milestones/M1.md  # planned: M1-01\ndocs/later.md  # planned: M1-02\n")
        self.assertEqual(r.check(), [])

    def test_allowlist_comments_and_blank_lines(self):
        r = self.repo({"docs/A.md": "`docs/p.md`\n"}, allow="# header\n\ndocs/p.md  # planned: M1-01\n")
        self.assertEqual(r.check(), [])

    def test_subdirectory_docs_are_checked(self):
        self.assertEqual(self.repo({"docs/reviews/R.md": "[a](../A.md) `docs/A.md`\n", "docs/A.md": ""}).check(), [])


class BadDocs(Base):
    def test_broken_relative_link(self):
        r = self.repo({"docs/A.md": "line1\n[b](B.md)\n"})
        (p,) = r.check()
        self.assertEqual((p.kind, p.file, p.line, p.target), ("broken-link", "docs/A.md", 2, "B.md"))

    def test_broken_link_with_anchor_reports_file_part(self):
        (p,) = self.repo({"docs/A.md": "[b](B.md#sec)\n"}).check()
        self.assertEqual((p.kind, p.target), ("broken-link", "B.md"))

    def test_broken_link_in_subdirectory(self):
        (p,) = self.repo({"docs/reviews/R.md": "[b](../B.md)\n"}).check()
        self.assertEqual((p.kind, p.file), ("broken-link", "docs/reviews/R.md"))

    def test_backticked_path_that_does_not_exist(self):
        (p,) = self.repo({"docs/A.md": "a\nb\nSee `scripts/gone.py`.\n", "scripts/x.py": ""}).check()
        self.assertEqual((p.kind, p.file, p.line, p.target), ("missing-path", "docs/A.md", 3, "scripts/gone.py"))

    def test_missing_directory_path(self):
        (p,) = self.repo({"docs/A.md": "`scripts/hooks/`\n", "scripts/x.py": ""}).check()
        self.assertEqual(p.kind, "missing-path")

    def test_missing_path_with_line_suffix_reports_bare_path(self):
        (p,) = self.repo({"docs/A.md": "`scripts/gone.py:12`\n"}).check()
        self.assertEqual(p.target, "scripts/gone.py")

    def test_stale_allowlist_entry_that_now_exists(self):
        r = self.repo({"docs/A.md": "`docs/p.md`\n", "docs/p.md": ""}, allow="docs/p.md  # planned: M1-01\n")
        (p,) = r.check()
        self.assertEqual((p.kind, p.target), ("stale-allow", "docs/p.md"))

    def test_stale_allowlist_entry_that_no_doc_mentions(self):
        r = self.repo({"docs/A.md": "nothing here\n"}, allow="docs/never.md  # planned: M1-01\n")
        (p,) = r.check()
        self.assertEqual((p.kind, p.target), ("stale-allow", "docs/never.md"))

    def test_allowlist_entry_without_reason(self):
        r = self.repo({"docs/A.md": "`docs/p.md`\n"}, allow="docs/p.md\n")
        self.assertEqual(r.kinds(), ["bad-allow"])

    def test_allowlist_entry_with_empty_reason(self):
        r = self.repo({"docs/A.md": "`docs/p.md`\n"}, allow="docs/p.md  #   \n")
        self.assertEqual(r.kinds(), ["bad-allow"])

    def test_duplicate_allowlist_entry(self):
        r = self.repo({"docs/A.md": "`docs/p.md`\n"}, allow="docs/p.md  # planned: a\ndocs/p.md  # planned: b\n")
        self.assertEqual(r.kinds(), ["bad-allow"])

    def test_allowlist_does_not_cover_other_paths(self):
        r = self.repo({"docs/A.md": "`docs/p.md` `docs/q.md`\n"}, allow="docs/p.md  # planned: M1-01\n")
        (p,) = r.check()
        self.assertEqual(p.target, "docs/q.md")

    def test_no_allowlist_file_is_fine(self):
        self.assertEqual(self.repo({"docs/A.md": "ok\n"}).check(), [])

    def test_each_problem_is_reported_once_per_occurrence(self):
        r = self.repo({"docs/A.md": "`docs/x.md`\n`docs/x.md`\n"})
        self.assertEqual(r.kinds(), ["missing-path", "missing-path"])


class Cli(Base):
    def run_cli(self, repo):
        return subprocess.run([sys.executable, "-I", str(SCRIPT), "--root", str(repo.root)],
                              capture_output=True, text=True, check=False)

    def test_exit_zero_when_clean(self):
        res = self.run_cli(self.repo({"docs/A.md": "ok\n"}))
        self.assertEqual((res.returncode, res.stdout), (0, ""))

    def test_exit_one_and_one_line_per_problem(self):
        res = self.run_cli(self.repo({"docs/A.md": "[b](B.md)\n`docs/x.md`\n"}))
        self.assertEqual(res.returncode, 1)
        lines = res.stdout.strip().splitlines()
        self.assertEqual(len(lines), 2)
        self.assertIn("docs/A.md:1", lines[0])
        self.assertIn("broken-link", lines[0])
        self.assertIn("docs/A.md:2", lines[1])
        self.assertIn("missing-path", lines[1])

    def test_exit_two_on_bad_usage(self):
        res = subprocess.run([sys.executable, "-I", str(SCRIPT), "--nope"], capture_output=True, text=True, check=False)
        self.assertEqual(res.returncode, 2)


class RealRepo(unittest.TestCase):
    def test_real_docs_have_no_findings(self):
        problems = docs_check.check(ROOT, ROOT / "scripts" / "docs_check_allowlist.txt")
        self.assertEqual([], [str(p) for p in problems])

    def test_verify_and_ci_run_the_check_and_its_tests(self):
        verify = (ROOT / "scripts" / "verify.sh").read_text(encoding="utf-8")
        ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        for name, text in (("verify.sh", verify), ("ci.yml", ci)):
            self.assertIn("scripts/test_docs_check.py", text, name)
            self.assertIn("scripts/docs_check.py", text, name)


if __name__ == "__main__":
    unittest.main()
