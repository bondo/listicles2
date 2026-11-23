"""Tests for scripts/repo_slug.py (M1-85): the GitHub repository slug from one place, so a repo rename needs no script change.
Every fixture is a temporary git checkout with its own `origin`; no test reads the real remote or the network.
Run: python3 -I scripts/test_repo_slug.py"""

import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import repo_slug  # noqa: E402  # justified: must follow the sys.path insert above

ROOT = Path(__file__).resolve().parent.parent
OLD = "bondo/listicles2"  # fixtures only: the scripts never name the repository
NEW = "octo-org/renamed.repo"

PARSED = {
    "https://github.com/bondo/listicles2": OLD, "https://github.com/bondo/listicles2.git": OLD, "https://github.com/bondo/listicles2/": OLD,
    "http://github.com/bondo/listicles2": OLD, "https://www.github.com/bondo/listicles2": OLD,
    "https://x-access-token:t0k@github.com/bondo/listicles2.git": OLD,
    "git@github.com:bondo/listicles2.git": OLD, "git@github.com:bondo/listicles2": OLD, "ssh://git@github.com/bondo/listicles2.git": OLD,
    "ssh://git@github.com:22/bondo/listicles2": OLD, "http://local_proxy@127.0.0.1:43123/git/bondo/listicles2": OLD,
    "http://local_proxy@127.0.0.1:43123/git/bondo/listicles2.git": OLD, "http://localhost:8080/git/bondo/listicles2": OLD,
    "https://a\u00a0b@github.com/bondo/x": "bondo/x",  # \s is ASCII here (re.ASCII), as [:space:] is in the wrappers (LC_ALL=C)
    "https://github.com/octo-org/renamed.repo": NEW, "git@github.com:octo-org/renamed.repo.git": NEW, "https://github.com/a/b_c-d.e": "a/b_c-d.e",
}
UNPARSABLE = [
    "", "bondo/listicles2", "https://gitlab.com/bondo/listicles2", "https://github.com/bondo", "https://github.com/bondo/listicles2/tree/main",
    "https://github.com/bondo/listicles2?x=1", "https://github.com/bondo/listicles2#x", "https://github.com/-bondo/listicles2",
    "https://github.com/bondo/..", "https://github.com/bondo/.", "https://github.com/bondo/.git", "https://github.com.evil.example/bondo/listicles2",
    "https://evil.example/github.com/bondo/listicles2", "http://127.0.0.1:1/bondo/listicles2", "http://evil.example/git/bondo/listicles2",
    "file:///srv/git/listicles2.git", "/srv/git/listicles2.git", "https://github.com/bondo/listicles2\n", " https://github.com/bondo/listicles2",
    "https://github.com/bon do/listicles2", "https://github.com/bondo/list icles2", "https://github.com//listicles2", "git@gitlab.com:bondo/listicles2.git",
    "host:x@github.com:bondo/listicles2", "ssh://git@github.com:\u0662\u0662/bondo/x",  # an Arabic-Indic port: \d is ASCII only
]


def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True, env=clean_env()).stdout


def clean_env(**extra):
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_") and k != "GITHUB_REPOSITORY"}
    return {**env, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1", **extra}


def checkout(tmp, remote=None):
    """A git checkout holding a copy of scripts/repo_slug.py, with `origin` set to `remote` (no remote when None)."""
    root = Path(tmp) / "checkout"
    (root / "scripts").mkdir(parents=True)
    shutil.copy(ROOT / "scripts" / "repo_slug.py", root / "scripts" / "repo_slug.py")
    git(root, "init", "-q")
    if remote is not None:
        git(root, "remote", "add", "origin", remote)
    return root


class ParseTests(unittest.TestCase):
    def test_every_supported_remote_form_parses(self):
        for url, slug in PARSED.items():
            self.assertEqual(repo_slug.slug_from_url(url), slug, url)

    def test_anything_else_is_not_a_slug(self):
        for url in UNPARSABLE:
            self.assertIsNone(repo_slug.slug_from_url(url), repr(url))


class ResolveTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)

    def resolve(self, remote=None, environ=None, **kw):
        return repo_slug.resolve(environ=environ or {}, root=checkout(tempfile.mkdtemp(dir=self.tmp), remote), **kw)

    def test_the_origin_remote_names_the_repository_before_and_after_a_rename(self):
        self.assertEqual(self.resolve("https://github.com/bondo/listicles2.git"), OLD)
        self.assertEqual(self.resolve("git@github.com:octo-org/renamed.repo.git"), NEW)

    def test_github_repository_wins_over_the_remote_even_for_a_different_owner(self):
        self.assertEqual(self.resolve("https://github.com/bondo/listicles2", {"GITHUB_REPOSITORY": "mallory/widgets"}), "mallory/widgets")

    def test_an_empty_github_repository_counts_as_unset(self):
        self.assertEqual(self.resolve("https://github.com/bondo/listicles2", {"GITHUB_REPOSITORY": ""}), OLD)

    def test_an_invalid_github_repository_fails_instead_of_falling_back(self):
        for bad in ("bondo", "bondo/listicles2/x", "../x", "bondo/..", "-x/y", "a b/c"):
            with self.assertRaisesRegex(repo_slug.RepoSlugError, "GITHUB_REPOSITORY"):
                self.resolve("https://github.com/bondo/listicles2", {"GITHUB_REPOSITORY": bad})

    def test_an_owner_pin_refuses_a_repository_of_another_owner_from_either_source(self):
        self.assertEqual(self.resolve("https://github.com/bondo/listicles2", owner="bondo"), OLD)
        self.assertEqual(self.resolve(None, {"GITHUB_REPOSITORY": "bondo/tally"}, owner="bondo"), "bondo/tally")
        for remote, environ in (("https://github.com/mallory/widgets", {}), ("https://github.com/bondo/x", {"GITHUB_REPOSITORY": "mallory/widgets"}),
                                ("https://github.com/Bondo/x", {}), ("https://github.com/bondo-evil/x", {})):
            with self.subTest(remote=remote, environ=environ), self.assertRaisesRegex(repo_slug.RepoSlugError, "owner"):
                self.resolve(remote, environ, owner="bondo")

    def test_no_remote_and_no_github_repository_fails_loudly(self):
        with self.assertRaisesRegex(repo_slug.RepoSlugError, "origin"):
            self.resolve(None)

    def test_an_unparsable_remote_fails_and_never_prints_credentials(self):
        with self.assertRaisesRegex(repo_slug.RepoSlugError, "origin") as cm:
            self.resolve("https://user:s3cret@gitlab.com/bondo/listicles2.git")
        self.assertNotIn("s3cret", str(cm.exception))

    def test_not_a_git_checkout_fails(self):
        with self.assertRaises(repo_slug.RepoSlugError):
            repo_slug.resolve(environ={}, root=Path(self.tmp))

    def test_git_variables_and_global_insteadof_cannot_redirect_the_remote(self):
        root = checkout(self.tmp, "https://github.com/bondo/listicles2")
        other = checkout(Path(self.tmp) / "other", "https://github.com/mallory/widgets")
        gitconfig = Path(self.tmp) / "gitconfig"
        gitconfig.write_text('[url "https://github.com/mallory/"]\n\tinsteadOf = https://github.com/bondo/\n')
        hostile = {"GIT_DIR": str(other / ".git"), "GIT_CONFIG_GLOBAL": str(gitconfig), "GIT_CONFIG_COUNT": "1",
                   "GIT_CONFIG_KEY_0": "remote.origin.url", "GIT_CONFIG_VALUE_0": "https://github.com/mallory/widgets"}
        with mock.patch.dict(os.environ, hostile):
            self.assertEqual(repo_slug.resolve(environ={}, root=root), OLD)


class CliTests(unittest.TestCase):
    def run_cli(self, remote, *args, **env):
        with tempfile.TemporaryDirectory() as tmp:
            root = checkout(tmp, remote)
            return subprocess.run([sys.executable, "-I", str(root / "scripts" / "repo_slug.py"), *args], capture_output=True, text=True,
                                  env=clean_env(**env), cwd=tmp, timeout=30)

    def test_prints_the_slug_of_its_own_checkout_from_any_directory(self):
        p = self.run_cli("git@github.com:octo-org/renamed.repo.git")
        self.assertEqual((p.returncode, p.stdout), (0, NEW + "\n"), p.stderr)

    def test_the_environment_comes_first(self):
        self.assertEqual(self.run_cli(None, GITHUB_REPOSITORY="mallory/widgets").stdout, "mallory/widgets\n")

    def test_failure_exits_1_with_a_reason_and_bad_usage_exits_2(self):
        p = self.run_cli("https://gitlab.com/x/y")
        self.assertEqual((p.returncode, p.stdout), (1, ""))
        self.assertIn("repo_slug: ", p.stderr)
        self.assertIn("origin", p.stderr)
        self.assertEqual(self.run_cli("https://github.com/bondo/listicles2", "--bogus").returncode, 2)


class NoHardCodedRepositoryTests(unittest.TestCase):
    def test_no_script_names_the_repository_or_the_checkout_path(self):
        """Tests may build fixtures from a constant; scripts take the slug from repo_slug.py and paths from the checkout root."""
        files = subprocess.run(["git", "ls-files", "scripts"], cwd=ROOT, capture_output=True, text=True, check=True, env=clean_env()).stdout.split()
        bad = []
        for name in files:
            if Path(name).name.startswith("test_") or not (ROOT / name).is_file():
                continue
            for i, line in enumerate((ROOT / name).read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                if re.search(r"bondo/|listicles2|/home/user/", line):
                    bad.append(f"{name}:{i}: {line.strip()}")
        self.assertEqual(bad, [])


if __name__ == "__main__":
    unittest.main()
