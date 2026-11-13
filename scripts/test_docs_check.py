"""Tests for scripts/docs_check.py (M0.5-12). Run: python3 -I scripts/test_docs_check.py

The checker must pass on good docs, fail on each kind of bad input, and pass on the real repository docs.
"""

import os
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

    def __init__(self, files, allow=None, git=False):
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
        if git:  # stage everything: existence then follows `git ls-files`, so ignored files do not count
            env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
            subprocess.run(["git", "init", "-q"], cwd=self.root, env=env, check=True)
            subprocess.run(["git", "add", "-A"], cwd=self.root, env=env, check=True)

    def check(self):
        return docs_check.check(self.root, self.allow)

    def kinds(self):
        return sorted(p.kind for p in self.check())

    def close(self):
        self.tmp.cleanup()


class Base(unittest.TestCase):
    def repo(self, files, allow=None, git=False):
        r = Repo(files, allow, git)
        self.addCleanup(r.close)
        return r


class GoodDocs(Base):
    def test_existing_relative_link_and_path(self):
        r = self.repo({"docs/A.md": "See [b](B.md) and `scripts/x.py`.\n", "docs/B.md": "", "scripts/x.py": ""})
        self.assertEqual(r.check(), [])

    def test_link_with_anchor_and_title(self):
        r = self.repo({"docs/A.md": '[b](B.md#section "title") [c](sub/C.md?x=1#y)\n', "docs/B.md": "", "docs/sub/C.md": ""})
        self.assertEqual(r.check(), [])

    def test_external_and_anchor_links_ignored(self):
        text = "[w](https://example.com/nope.md) [m](mailto:a@b.c) [a](#here) [h](http://x/y/z.md)\n"
        self.assertEqual(self.repo({"docs/A.md": text}).check(), [])

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


class AllMarkdown(Base):
    """R1-01: every tracked *.md is scanned, not only docs/."""

    def test_root_and_prompt_files_are_scanned(self):
        r = self.repo({"README.md": "`docs/gone.md`\n", "agents/prompts/p.md": "`docs/gone.md`\n", "docs/A.md": ""})
        self.assertEqual(sorted((p.file, p.target) for p in r.check()), [("README.md", "docs/gone.md"), ("agents/prompts/p.md", "docs/gone.md")])

    def test_link_in_root_file_is_relative_to_that_file(self):
        self.assertEqual(self.repo({"README.md": "[a](docs/A.md)\n", "docs/A.md": ""}).check(), [])
        (p,) = self.repo({"agents/p.md": "[a](docs/A.md)\n", "docs/A.md": ""}).check()
        self.assertEqual((p.kind, p.file), ("broken-link", "agents/p.md"))

    def test_ignored_markdown_is_not_scanned(self):
        r = self.repo({".gitignore": "node_modules/\n", "node_modules/pkg/R.md": "`docs/gone.md`\n", "docs/A.md": ""}, git=True)
        self.assertEqual(r.check(), [])


class ScopedAllowlist(Base):
    """R1-01: an entry can be limited to the files that may mention the path."""

    def test_scoped_entry_covers_listed_file(self):
        r = self.repo({"docs/A.md": "`docs/old.md`\n"}, allow="docs/old.md @docs/A.md  # absent on purpose\n")
        self.assertEqual(r.check(), [])

    def test_same_path_in_another_file_still_fails(self):
        r = self.repo({"docs/A.md": "`docs/old.md`\n", "agents/p.md": "write `docs/old.md`\n"}, allow="docs/old.md @docs/A.md  # absent on purpose\n")
        (p,) = r.check()
        self.assertEqual((p.kind, p.file, p.target), ("missing-path", "agents/p.md", "docs/old.md"))

    def test_scoped_file_that_no_longer_mentions_the_path_is_stale(self):
        r = self.repo({"docs/A.md": "`docs/old.md`\n", "docs/B.md": "clean\n"}, allow="docs/old.md @docs/A.md @docs/B.md  # absent on purpose\n")
        (p,) = r.check()
        self.assertEqual((p.kind, p.target), ("stale-allow", "docs/old.md"))
        self.assertIn("docs/B.md", p.note)

    def test_scope_without_at_sign_is_bad(self):
        r = self.repo({"docs/A.md": "`docs/old.md`\n"}, allow="docs/old.md docs/A.md  # reason\n")
        self.assertIn("bad-allow", r.kinds())


class Fences(Base):
    """R1-02: a fence closes only on the same character with at least the same length (CommonMark)."""

    def test_other_fence_character_inside_a_fence_does_not_close_it(self):
        self.assertEqual(self.repo({"docs/A.md": "```\n`nope/a.md`\n~~~\n`nope/b.md`\n```\n"}).check(), [])

    def test_longer_fence_may_contain_a_shorter_one(self):
        self.assertEqual(self.repo({"docs/A.md": "````\n```\n`docs/nope.md`\n```\n`docs/nope2.md`\n````\n"}).check(), [])

    def test_checking_resumes_after_the_fence_closes(self):
        (p,) = self.repo({"docs/A.md": "```\n`docs/nope.md`\n```\n`docs/after.md`\n"}).check()
        self.assertEqual((p.line, p.target), (4, "docs/after.md"))


class TrackedFiles(Base):
    """R1-03: existence follows git (tracked or untracked-but-not-ignored), so a local pass matches CI."""

    def test_ignored_file_does_not_count_as_existing(self):
        r = self.repo({".gitignore": "build/\n", "build/x.txt": "", "docs/A.md": "`build/x.txt`\n"}, git=True)
        (p,) = r.check()
        self.assertEqual((p.kind, p.target), ("missing-path", "build/x.txt"))

    def test_ignored_link_target_does_not_count_as_existing(self):
        r = self.repo({".gitignore": "out.md\n", "out.md": "", "docs/A.md": "[o](../out.md)\n"}, git=True)
        self.assertEqual(r.kinds(), ["broken-link"])

    def test_ignored_top_level_directory_is_not_a_repo_directory(self):
        r = self.repo({".gitignore": "build/\n", "build/x.txt": "", "docs/A.md": "`build/out` and `build/`\n"}, git=True)
        self.assertEqual(r.check(), [])

    def test_allowlist_entry_for_an_ignored_existing_file_is_not_stale(self):
        files = {".gitignore": "build/\n", "build/x.txt": "", "docs/A.md": "`build/x.txt`\n"}
        r = self.repo(files, allow="build/x.txt  # generated, never tracked\n", git=True)
        self.assertEqual(r.check(), [])

    def test_untracked_but_not_ignored_file_counts(self):
        r = self.repo({"docs/A.md": "`docs/new.md`\n"}, git=True)
        (r.root / "docs" / "new.md").write_text("", encoding="utf-8")
        self.assertEqual(r.check(), [])

    def test_directory_of_tracked_files_exists(self):
        r = self.repo({"docs/A.md": "`scripts/hooks/` [d](../scripts/hooks)\n", "scripts/hooks/h.py": ""}, git=True)
        self.assertEqual(r.check(), [])


class ReferenceDefinitions(Base):
    """R1-04: `[label]: target` definitions are checked like inline links."""

    def test_broken_reference_definition(self):
        (p,) = self.repo({"docs/A.md": "see [x]\n\n[x]: ../gone.md\n"}).check()
        self.assertEqual((p.kind, p.line, p.target), ("broken-link", 3, "../gone.md"))

    def test_good_and_external_reference_definitions(self):
        text = "[a]: B.md#s\n[b]: <B.md>\n[c]: https://example.com/x.md\n[d]: #here\n"
        self.assertEqual(self.repo({"docs/A.md": text, "docs/B.md": ""}).check(), [])

    def test_definition_inside_a_fence_is_ignored(self):
        self.assertEqual(self.repo({"docs/A.md": "```\n[x]: gone.md\n```\n"}).check(), [])


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
