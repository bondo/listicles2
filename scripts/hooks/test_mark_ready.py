"""scripts/mark-ready.sh is the only thing the project permission rule lets agents run to mark a PR ready.
It must accept exactly one PR number and make exactly one call, to the repository of its own checkout's `origin` remote (M1-85: parsed in the pinned
wrapper itself, the same forms as scripts/repo_slug.py, never from the environment), so it works before and after a repo rename.
The wrapper finds `gh` only in the directories on its `gh_dirs=` line (never through PATH, R5-03), so a fake `gh` records the call through
a copy of the real file, in a fixture checkout, whose `gh_dirs=` line is replaced. A decoy `gh` in PATH must never run.
Run: python3 -I -m unittest discover -s scripts/hooks"""

import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(1, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import gitenv  # noqa: E402, F401  # justified: after the sys.path insert, imported for its side effect, drops GIT_DIR and friends (see gitenv.py)

import repo_slug  # noqa: E402  # justified: after the sys.path insert, the parser the wrappers must agree with
import test_repo_slug  # noqa: E402  # justified: after the sys.path insert, its tables of parsable and unparsable remotes

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
WRAPPER = os.path.join(ROOT, "scripts", "mark-ready.sh")
FAKE_GH = (
    "#!/bin/sh\n"
    '{ for a in "$@"; do printf "%s\\n" "$a"; done;\n'
    '  printf "GH_HOST=%s\\nGH_REPO=%s\\n" "${GH_HOST-unset}" "${GH_REPO-unset}"; } > "$FAKE_GH_OUT"\n'
    'printf "%s" "$PATH" > "$FAKE_GH_OUT.path"\n'
)
GH_DIRS_LINE = re.compile(r'(?m)^gh_dirs="[^"\n]*"$')
OLD_SLUG = "bondo/listicles2"  # the name before the rename
SLUG = "bondo/renamed-repo"  # fixtures only: the wrapper takes the name from the checkout's origin remote and pins only the owner
OTHER_OWNER = ["https://github.com/mallory/listicles2.git", "git@github.com:bondo-evil/x.git", "http://p@127.0.0.1:1/git/Bondo/x"]
REMOTE = f"https://github.com/{SLUG}.git"
NO_REMOTE = None


def fixture_checkout(parent, scripts, remote=REMOTE):
    """A git checkout under `parent` with only scripts/<name> = text for each item (no helper next to it) and `origin` = remote."""
    root = os.path.join(parent, "checkout")
    os.makedirs(os.path.join(root, "scripts"))
    for name, text in scripts.items():
        with open(os.path.join(root, "scripts", name), "w", encoding="utf-8") as f:
            f.write(text)
        os.chmod(os.path.join(root, "scripts", name), 0o755)
    subprocess.run(["git", "init", "-q", root], check=True)
    if remote is not None:
        subprocess.run(["git", "-C", root, "remote", "add", "origin", remote], check=True)
    return root


SLUG_BLOCK = re.compile(r"(?ms)^# slug-parse: begin[^\n]*\n(.*?)^# slug-parse: end$")


def read_wrapper(name="mark-ready.sh"):
    with open(os.path.join(ROOT, "scripts", name), encoding="utf-8") as f:
        return f.read()


class MarkReady(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.out = os.path.join(self.tmp.name, "gh.out")
        self.fixed = os.path.join(self.tmp.name, "fixed")  # the only directory the copy looks in for gh
        self.decoy = os.path.join(self.tmp.name, "decoy")  # first in PATH, must never be used
        self.decoy_out = os.path.join(self.tmp.name, "decoy.out")
        self.put_gh(self.fixed, FAKE_GH)
        self.put_gh(self.decoy, FAKE_GH.replace("$FAKE_GH_OUT", self.decoy_out))

    def put_gh(self, d, body):
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "gh"), "w", encoding="utf-8") as f:
            f.write(body)
        os.chmod(os.path.join(d, "gh"), 0o755)

    def copy_with_gh_dirs(self, dirs, remote):
        """A fixture checkout with a copy of the real wrapper whose gh_dirs line is replaced; fails if the real file has no such single line."""
        src = read_wrapper()
        self.assertEqual(len(GH_DIRS_LINE.findall(src)), 1, 'scripts/mark-ready.sh needs exactly one line: gh_dirs="<absolute dirs>"')
        shutil.rmtree(os.path.join(self.tmp.name, "checkout"), ignore_errors=True)
        return fixture_checkout(self.tmp.name, {"mark-ready.sh": GH_DIRS_LINE.sub(lambda _: f'gh_dirs="{dirs}"', src)}, remote)

    def run_wrapper(self, *args, env=None, dirs=None, remote=REMOTE):
        e = {"PATH": self.decoy + os.pathsep + "/usr/bin:/bin", "FAKE_GH_OUT": self.out}
        e.update(env or {})
        root = self.copy_with_gh_dirs(self.fixed if dirs is None else dirs, remote)
        p = subprocess.run(["bash", "scripts/mark-ready.sh", *args], capture_output=True, text=True, env=e, cwd=root, timeout=30)
        called = os.path.exists(self.out)
        return p, called

    def test_wrapper_exists_and_is_executable_in_git(self):
        self.assertTrue(os.path.isfile(WRAPPER), "scripts/mark-ready.sh must exist")
        mode = subprocess.run(["git", "ls-files", "-s", "scripts/mark-ready.sh"], capture_output=True, text=True, cwd=ROOT).stdout.split()
        self.assertTrue(mode and mode[0] == "100755", "scripts/mark-ready.sh must be tracked with the executable bit")

    def test_valid_number_makes_exactly_the_fixed_call(self):
        for n in ["1", "86", "123456"]:
            if os.path.exists(self.out):
                os.remove(self.out)
            p, called = self.run_wrapper(n)
            self.assertEqual(p.returncode, 0, (n, p.stderr))
            self.assertTrue(called, n)
            with open(self.out, encoding="utf-8") as f:
                lines = f.read().splitlines()
            self.assertEqual(lines[:4], ["api", "-X", "POST", f"repos/{SLUG}/pulls/{n}/ccr/ready_for_review"], n)
            self.assertEqual(lines[4:], ["GH_HOST=unset", "GH_REPO=unset"], "no env-driven host or repo")

    def test_env_cannot_redirect_the_call(self):
        hostile = {"GH_HOST": "evil.example", "GH_REPO": "other/repo", "GITHUB_REPOSITORY": "other/repo", "GIT_DIR": "/nonexistent", "CDPATH": "/tmp"}
        p, called = self.run_wrapper("5", env=hostile)
        self.assertEqual(p.returncode, 0, p.stderr)
        with open(self.out, encoding="utf-8") as f:
            text = f.read()
        self.assertIn(f"repos/{SLUG}/pulls/5/", text)
        self.assertIn("GH_HOST=unset\nGH_REPO=unset", text)

    def test_the_repository_follows_the_origin_remote_old_or_new_name(self):
        for remote, slug in ((f"git@github.com:{OLD_SLUG}.git", OLD_SLUG), ("http://local_proxy@127.0.0.1:4711/git/bondo/tally", "bondo/tally")):
            if os.path.exists(self.out):
                os.remove(self.out)
            p, called = self.run_wrapper("9", remote=remote)
            self.assertEqual((p.returncode, called), (0, True), p.stderr)
            with open(self.out, encoding="utf-8") as f:
                self.assertEqual(f.read().splitlines()[3], f"repos/{slug}/pulls/9/ccr/ready_for_review")

    def test_a_remote_of_another_owner_is_refused_without_calling_gh(self):
        """`git remote set-url origin` is not denied by the guard, so the pinned wrapper pins the owner (a rename keeps it)."""
        for remote in OTHER_OWNER:
            p, called = self.run_wrapper("9", remote=remote)
            self.assertEqual((p.returncode, called or os.path.exists(self.decoy_out)), (1, False), (remote, p.stderr))
            self.assertIn("owner", p.stderr)

    def test_git_says_why_the_remote_could_not_be_read(self):
        p, _ = self.run_wrapper("9", remote=NO_REMOTE)
        self.assertIn("origin", p.stderr.splitlines()[0])  # git's own message comes first, then the wrapper's
        self.assertGreaterEqual(len(p.stderr.splitlines()), 2, p.stderr)

    def test_no_or_unparsable_remote_fails_loudly_without_calling_gh(self):
        for remote in (NO_REMOTE, "https://gitlab.com/x/y.git", "/srv/git/x.git"):
            p, called = self.run_wrapper("9", remote=remote, env={"GITHUB_REPOSITORY": "other/repo"})
            self.assertEqual(p.returncode, 1, (remote, p.stderr))
            self.assertFalse(called or os.path.exists(self.decoy_out), remote)
            self.assertIn("origin", p.stderr)

    def test_rejects_bad_input_without_calling_gh(self):
        bad = ["", "abc", "0", "012", "-1", "+1", "1.5", "1234567", "12 13", "12/merge", "12/../../x", "1;rm -rf x", "1&&id", "1|id",
               "$(id)", "`id`", "12\n", "\n12", "12\n13", "1\n; gh api -X PUT x", "٣", "１２", "12 -X PUT", "-X", "--input", "--hostname=x",
               "12/ccr/ready_for_review", f"repos/{OLD_SLUG}/pulls/12/merge"]
        for arg in bad:
            if os.path.exists(self.out):
                os.remove(self.out)
            p, called = self.run_wrapper(arg)
            self.assertNotEqual(p.returncode, 0, repr(arg))
            self.assertFalse(called, f"gh must not run for {arg!r}")

    def test_rejects_wrong_argument_count(self):
        for args in [(), ("12", "13"), ("12", "-X", "PUT"), ("12", "--input", "/etc/passwd"), ("12", ""), ("", "12")]:
            if os.path.exists(self.out):
                os.remove(self.out)
            p, called = self.run_wrapper(*args)
            self.assertNotEqual(p.returncode, 0, args)
            self.assertFalse(called, f"gh must not run for {args!r}")

    def test_source_has_no_passthrough_and_no_other_route(self):
        src = read_wrapper()
        for bad in ['"$@"', "$*", "merge", "PUT", "DELETE", "--input", "--hostname", "eval ", "-H "]:
            self.assertNotIn(bad, src, bad)
        self.assertEqual(src.count("api -X POST"), 1)
        self.assertEqual(len(re.findall(r'exec "\$d/gh" api -X POST "repos/\$\{repo\}/pulls/\$\{n\}/ccr/ready_for_review"', src)), 1)
        self.assertNotIn("python", src, "the pinned wrapper runs no other file of the checkout")

    def test_both_wrappers_parse_the_remote_with_the_same_block_as_repo_slug_py(self):
        blocks = {name: SLUG_BLOCK.findall(read_wrapper(name)) for name in ("mark-ready.sh", "update-branch.sh")}
        self.assertTrue(all(len(b) == 1 for b in blocks.values()), blocks)
        self.assertEqual(blocks["mark-ready.sh"], blocks["update-branch.sh"])
        for url in [*test_repo_slug.PARSED, *test_repo_slug.UNPARSABLE]:
            p = subprocess.run(["bash", "-pc", 'remote="$1"\n' + blocks["mark-ready.sh"][0] + 'printf "%s" "$repo"', "x", url], capture_output=True, text=True,
                               env={"PATH": "/usr/bin:/bin"}, timeout=30)
            self.assertEqual((p.returncode, p.stdout), (0, repo_slug.slug_from_url(url) or ""), repr(url))

    def test_a_gitfile_in_scripts_cannot_swap_the_checkout_whose_remote_names_the_repository(self):
        """git looks for .git upward from where it starts; both wrappers start at the checkout root, so a planted scripts/.git is never read."""
        other = fixture_checkout(os.path.join(self.tmp.name, "other"), {}, "https://github.com/bondo/secret-other.git")
        for name, args, tail in (("mark-ready.sh", ("5",), "ccr/ready_for_review"), ("update-branch.sh", ("5", "a" * 40), "update-branch")):
            with self.subTest(name=name):
                shutil.rmtree(os.path.join(self.tmp.name, "checkout"), ignore_errors=True)
                root = fixture_checkout(self.tmp.name, {name: GH_DIRS_LINE.sub(lambda _: f'gh_dirs="{self.fixed}"', read_wrapper(name))})
                with open(os.path.join(root, "scripts", ".git"), "w", encoding="utf-8") as f:
                    f.write(f"gitdir: {os.path.join(other, '.git')}\n")
                p = subprocess.run(["bash", f"scripts/{name}", *args], capture_output=True, text=True, cwd=root, timeout=30,
                                   env={"PATH": "/usr/bin:/bin", "FAKE_GH_OUT": self.out})
                self.assertEqual(p.returncode, 0, p.stderr)
                with open(self.out, encoding="utf-8") as f:
                    self.assertEqual(f.read().splitlines()[3], f"repos/{SLUG}/pulls/5/{tail}")

    def test_both_wrappers_parse_the_remote_in_the_c_locale(self):
        """Bracket ranges in a bash regex follow the locale; LC_ALL=C makes them ASCII, as repo_slug.py's patterns are (re.ASCII)."""
        for name in ("mark-ready.sh", "update-branch.sh"):
            src = read_wrapper(name)
            self.assertIn("\nLC_ALL=C\n", src, name)
            self.assertLess(src.index("\nLC_ALL=C\n"), src.index("# slug-parse: begin"), name)

    def test_a_decoy_gh_earlier_in_path_is_not_used(self):
        """R5-03: `gh` is resolved in fixed directories, not through PATH, so a shim planted in a PATH directory cannot run."""
        p, called = self.run_wrapper("7")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertTrue(called, "the gh in the fixed directory must run")
        self.assertFalse(os.path.exists(self.decoy_out), "the decoy gh earlier in PATH must not run")
        with open(self.out + ".path", encoding="utf-8") as f:  # and gh itself runs with a fixed, absolute PATH
            path = f.read()
        self.assertTrue(self.decoy not in path and all(os.path.isabs(d) for d in path.split(":")), path)

    def test_without_gh_in_the_fixed_directories_it_fails_and_never_falls_back_to_path(self):
        p, called = self.run_wrapper("7", dirs=self.tmp.name + "/empty")
        self.assertNotEqual(p.returncode, 0)
        self.assertFalse(called or os.path.exists(self.decoy_out), "no fallback to a gh found through PATH")
        self.assertIn("gh", p.stderr)

    def test_source_fixes_the_interpreter_and_the_gh_directories(self):
        src = read_wrapper()
        self.assertEqual(src.splitlines()[0], "#!/bin/bash -p", "no `env` lookup of bash through PATH")
        self.assertEqual(len(GH_DIRS_LINE.findall(src)), 1)
        listed = GH_DIRS_LINE.findall(src)[0].split('"')[1].split()
        self.assertTrue(listed and all(os.path.isabs(d) and not d.startswith(("/home", "/root", "/tmp")) for d in listed), listed)
        for bad in ["command -v", "which ", "type -p", "env bash", "exec gh", "\ngh "]:
            self.assertNotIn(bad, src, bad)


if __name__ == "__main__":
    unittest.main()
