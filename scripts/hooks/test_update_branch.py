"""scripts/update-branch.sh is the only thing the project permission rule lets the merge agent run to update a PR branch (owner decision, #15
comment 7008033864). It must accept exactly `<PR number> <40-hex head sha>` and make exactly one fixed PUT to the update-branch route with
`expected_head_sha` (a moved head is refused by GitHub), to the repository of its checkout's `origin` remote (M1-85). Same shape as test_mark_ready.py:
a fixture checkout, a fake `gh` in the wrapper's fixed directory, a decoy in PATH.
Run: python3 -I -m unittest discover -s scripts/hooks"""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gitenv  # noqa: E402, F401  # justified: after the sys.path insert, imported for its side effect, drops GIT_DIR and friends (see gitenv.py)
from test_mark_ready import FAKE_GH, GH_DIRS_LINE, NO_REMOTE, OLD_SLUG, REMOTE, SLUG, fixture_checkout  # noqa: E402  # justified: shares the fake gh and fixture with the sibling wrapper test

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
WRAPPER = os.path.join(ROOT, "scripts", "update-branch.sh")
SHA = "0123456789abcdef0123456789abcdef01234567"


def read_wrapper():
    with open(WRAPPER, encoding="utf-8") as f:
        return f.read()


class UpdateBranch(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.out, self.fixed, self.decoy = (os.path.join(self.tmp.name, n) for n in ("gh.out", "fixed", "decoy"))
        for d, out in ((self.fixed, "$FAKE_GH_OUT"), (self.decoy, os.path.join(self.tmp.name, "decoy.out"))):
            os.makedirs(d)
            with open(os.path.join(d, "gh"), "w", encoding="utf-8") as f:
                f.write(FAKE_GH.replace("$FAKE_GH_OUT", out) if d == self.decoy else FAKE_GH)
            os.chmod(os.path.join(d, "gh"), 0o755)

    def run_wrapper(self, *args, env=None, dirs=None, remote=REMOTE):
        src = read_wrapper()
        self.assertEqual(len(GH_DIRS_LINE.findall(src)), 1, 'scripts/update-branch.sh needs exactly one line: gh_dirs="<absolute dirs>"')
        shutil.rmtree(os.path.join(self.tmp.name, "checkout"), ignore_errors=True)
        root = fixture_checkout(self.tmp.name, {"update-branch.sh": GH_DIRS_LINE.sub(lambda _: f'gh_dirs="{self.fixed if dirs is None else dirs}"', src)}, remote)
        e = {"PATH": self.decoy + os.pathsep + "/usr/bin:/bin", "FAKE_GH_OUT": self.out, **(env or {})}
        p = subprocess.run(["bash", "scripts/update-branch.sh", *args], capture_output=True, text=True, env=e, cwd=root, timeout=30)
        return p, os.path.exists(self.out)

    def test_wrapper_exists_and_is_executable_in_git(self):
        self.assertTrue(os.path.isfile(WRAPPER), "scripts/update-branch.sh must exist")
        mode = subprocess.run(["git", "ls-files", "-s", "scripts/update-branch.sh"], capture_output=True, text=True, cwd=ROOT).stdout.split()
        self.assertTrue(mode and mode[0] == "100755", "scripts/update-branch.sh must be tracked with the executable bit")

    def test_valid_call_makes_exactly_the_fixed_put(self):
        for n in ("1", "86", "123456"):
            if os.path.exists(self.out):
                os.remove(self.out)
            p, called = self.run_wrapper(n, SHA)
            self.assertEqual((p.returncode, called), (0, True), (n, p.stderr))
            with open(self.out, encoding="utf-8") as f:
                lines = f.read().splitlines()
            self.assertEqual(lines[:6], ["api", "-X", "PUT", f"repos/{SLUG}/pulls/{n}/update-branch", "-f", f"expected_head_sha={SHA}"])
            self.assertEqual(lines[6:], ["GH_HOST=unset", "GH_REPO=unset"], "no env-driven host or repo")

    def test_env_cannot_redirect_the_call(self):
        hostile = {"GH_HOST": "evil.example", "GH_REPO": "other/repo", "GITHUB_REPOSITORY": "other/repo", "GIT_DIR": "/nonexistent", "CDPATH": "/tmp"}
        p, called = self.run_wrapper("5", SHA, env=hostile)
        self.assertEqual((p.returncode, called), (0, True), p.stderr)
        with open(self.out, encoding="utf-8") as f:
            text = f.read()
        self.assertIn(f"repos/{SLUG}/pulls/5/update-branch", text)
        self.assertIn("GH_HOST=unset\nGH_REPO=unset", text)

    def test_the_repository_follows_the_origin_remote_and_a_missing_or_unparsable_one_never_reaches_gh(self):
        p, called = self.run_wrapper("9", SHA, remote=f"ssh://git@github.com/{OLD_SLUG}")
        self.assertEqual((p.returncode, called), (0, True), p.stderr)
        with open(self.out, encoding="utf-8") as f:
            self.assertEqual(f.read().splitlines()[3], f"repos/{OLD_SLUG}/pulls/9/update-branch")
        for remote in (NO_REMOTE, "https://gitlab.com/x/y.git"):
            if os.path.exists(self.out):
                os.remove(self.out)
            p, called = self.run_wrapper("9", SHA, remote=remote, env={"GITHUB_REPOSITORY": "other/repo"})
            self.assertEqual((p.returncode, called), (1, False), (remote, p.stderr))
            self.assertIn("origin", p.stderr)

    def test_bad_input_never_reaches_gh(self):
        bad_numbers = ["", "abc", "0", "012", "-1", "+1", "1.5", "1234567", "12 13", "12/merge", "1;id", "$(id)", "12\n", "٣"]
        bad_shas = ["", "abc1234", SHA[:39], SHA + "0", SHA.upper(), "g" * 40, SHA[:39] + " ", SHA + "\n", "-" + SHA[1:], f"{SHA[:20]}/{SHA[21:]}", "$(id)"]
        cases = [(n, SHA) for n in bad_numbers] + [("12", s) for s in bad_shas]
        cases += [(), ("12",), ("12", SHA, "extra"), ("12", SHA, "-f", "x=y"), (SHA, "12"), ("12", "-X", "PUT", SHA), ("--input", "x", SHA)]
        for args in cases:
            if os.path.exists(self.out):
                os.remove(self.out)
            p, called = self.run_wrapper(*args)
            self.assertNotEqual(p.returncode, 0, repr(args))
            self.assertFalse(called, f"gh must not run for {args!r}")

    def test_a_decoy_gh_in_path_is_never_used_and_gh_is_only_looked_up_in_fixed_directories(self):
        p, called = self.run_wrapper("7", SHA)
        self.assertEqual((p.returncode, called), (0, True), p.stderr)
        self.assertFalse(os.path.exists(os.path.join(self.tmp.name, "decoy.out")))
        os.remove(self.out)
        p, called = self.run_wrapper("7", SHA, dirs=self.tmp.name + "/empty")
        self.assertNotEqual(p.returncode, 0)
        self.assertFalse(called or os.path.exists(os.path.join(self.tmp.name, "decoy.out")), "no fallback to a gh found through PATH")

    def test_bash_env_and_exported_functions_cannot_run_code_under_the_allow_rule(self):
        """R1-02 of #237: run each wrapper through its shebang (`bash -p` reads no BASH_ENV and imports no functions) with both injected."""
        for name, args in (("update-branch.sh", ("7", SHA)), ("mark-ready.sh", ("7",))):
            with self.subTest(name):
                marker = os.path.join(self.tmp.name, "pwned-" + name)
                rc = os.path.join(self.tmp.name, "evil.sh")
                with open(rc, "w", encoding="utf-8") as f:
                    f.write(f"touch {marker}\n")
                with open(os.path.join(ROOT, "scripts", name), encoding="utf-8") as f:
                    src = f.read()
                shutil.rmtree(os.path.join(self.tmp.name, "checkout"), ignore_errors=True)
                root = fixture_checkout(self.tmp.name, {name: GH_DIRS_LINE.sub(lambda _: f'gh_dirs="{self.fixed}"', src)})
                if os.path.exists(self.out):
                    os.remove(self.out)
                env = {"PATH": "/usr/bin:/bin", "FAKE_GH_OUT": self.out, "BASH_ENV": rc, "ENV": rc, "BASH_FUNC_exec%%": f"() {{ touch {marker}; }}"}
                p = subprocess.run([os.path.join(root, "scripts", name), *args], capture_output=True, text=True, env=env, cwd=self.tmp.name, timeout=30)
                self.assertFalse(os.path.exists(marker), "injected code ran")
                self.assertEqual((p.returncode, os.path.exists(self.out)), (0, True), p.stderr)

    def test_source_has_one_fixed_route_no_passthrough_and_a_fixed_interpreter(self):
        src = read_wrapper()
        self.assertEqual(src.splitlines()[0], "#!/bin/bash -p")
        for bad in ['"$@"', "$*", "merge", "POST", "DELETE", "--input", "--hostname", "eval ", "-H ", "command -v", "which ", "env bash"]:
            self.assertNotIn(bad, src, bad)
        self.assertEqual(src.count("api -X PUT"), 1)
        self.assertEqual(src.count('"repos/${repo}/pulls/${n}/update-branch" -f "expected_head_sha=${sha}"'), 1)
        self.assertNotIn("python", src, "the pinned wrapper runs no other file of the checkout")


if __name__ == "__main__":
    unittest.main()
