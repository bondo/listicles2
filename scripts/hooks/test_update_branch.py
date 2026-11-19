"""scripts/update-branch.sh is the only thing the project permission rule lets the merge agent run to update a PR branch (owner decision, #15
comment 7008033864). It must accept exactly `<PR number> <40-hex head sha>` and make exactly one fixed PUT to the update-branch route with
`expected_head_sha` (a moved head is refused by GitHub). Same shape as test_mark_ready.py: a fake `gh` in the wrapper's fixed directory, a decoy in PATH.
Run: python3 -I -m unittest discover -s scripts/hooks"""

import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gitenv  # noqa: E402, F401  # justified: after the sys.path insert, imported for its side effect, drops GIT_DIR and friends (see gitenv.py)
from test_mark_ready import FAKE_GH, GH_DIRS_LINE  # noqa: E402  # justified: shares the fake gh with the sibling wrapper test

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

    def run_wrapper(self, *args, env=None, dirs=None):
        src = read_wrapper()
        self.assertEqual(len(GH_DIRS_LINE.findall(src)), 1, 'scripts/update-branch.sh needs exactly one line: gh_dirs="<absolute dirs>"')
        copy = os.path.join(self.tmp.name, "copy.sh")
        with open(copy, "w", encoding="utf-8") as f:
            f.write(GH_DIRS_LINE.sub(lambda _: f'gh_dirs="{self.fixed if dirs is None else dirs}"', src))
        e = {"PATH": self.decoy + os.pathsep + "/usr/bin:/bin", "FAKE_GH_OUT": self.out, **(env or {})}
        p = subprocess.run(["bash", copy, *args], capture_output=True, text=True, env=e, cwd=ROOT, timeout=30)
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
            self.assertEqual(lines[:6], ["api", "-X", "PUT", f"repos/bondo/listicles2/pulls/{n}/update-branch", "-f", f"expected_head_sha={SHA}"])
            self.assertEqual(lines[6:], ["GH_HOST=unset", "GH_REPO=unset"], "no env-driven host or repo")

    def test_env_cannot_redirect_the_call(self):
        p, called = self.run_wrapper("5", SHA, env={"GH_HOST": "evil.example", "GH_REPO": "other/repo"})
        self.assertEqual((p.returncode, called), (0, True), p.stderr)
        with open(self.out, encoding="utf-8") as f:
            self.assertIn("GH_HOST=unset\nGH_REPO=unset", f.read())

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

    def test_source_has_one_fixed_route_no_passthrough_and_a_fixed_interpreter(self):
        src = read_wrapper()
        self.assertEqual(src.splitlines()[0], "#!/bin/bash")
        for bad in ['"$@"', "$*", "merge", "POST", "DELETE", "--input", "--hostname", "eval ", "-H ", "command -v", "which ", "env bash"]:
            self.assertNotIn(bad, src, bad)
        self.assertEqual(src.count("api -X PUT"), 1)
        self.assertEqual(src.count('"repos/bondo/listicles2/pulls/${n}/update-branch" -f "expected_head_sha=${sha}"'), 1)


if __name__ == "__main__":
    unittest.main()
