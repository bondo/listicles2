"""scripts/mark-ready.sh is the only thing the project permission rule lets agents run to mark a PR ready.
It must accept exactly one PR number and make exactly one fixed call. A fake `gh` on PATH records what the wrapper would run.
Run: python3 -I -m unittest discover -s scripts/hooks"""

import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gitenv  # noqa: E402, F401  # justified: after the sys.path insert, imported for its side effect, drops GIT_DIR and friends (see gitenv.py)

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
WRAPPER = os.path.join(ROOT, "scripts", "mark-ready.sh")
FAKE_GH = (
    "#!/bin/sh\n"
    '{ for a in "$@"; do printf "%s\\n" "$a"; done;\n'
    '  printf "GH_HOST=%s\\nGH_REPO=%s\\n" "${GH_HOST-unset}" "${GH_REPO-unset}"; } > "$FAKE_GH_OUT"\n'
)


class MarkReady(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.out = os.path.join(self.tmp.name, "gh.out")
        gh = os.path.join(self.tmp.name, "gh")
        with open(gh, "w", encoding="utf-8") as f:
            f.write(FAKE_GH)
        os.chmod(gh, 0o755)

    def run_wrapper(self, *args, env=None):
        e = {"PATH": self.tmp.name + os.pathsep + "/usr/bin:/bin", "FAKE_GH_OUT": self.out}
        e.update(env or {})
        p = subprocess.run(["bash", WRAPPER, *args], capture_output=True, text=True, env=e, cwd=ROOT, timeout=30)
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
            self.assertEqual(lines[:4], ["api", "-X", "POST", f"repos/bondo/listicles2/pulls/{n}/ccr/ready_for_review"], n)
            self.assertEqual(lines[4:], ["GH_HOST=unset", "GH_REPO=unset"], "no env-driven host or repo")

    def test_env_cannot_redirect_the_call(self):
        p, called = self.run_wrapper("5", env={"GH_HOST": "evil.example", "GH_REPO": "other/repo"})
        self.assertEqual(p.returncode, 0, p.stderr)
        with open(self.out, encoding="utf-8") as f:
            self.assertIn("GH_HOST=unset\nGH_REPO=unset", f.read())

    def test_rejects_bad_input_without_calling_gh(self):
        bad = ["", "abc", "0", "012", "-1", "+1", "1.5", "1234567", "12 13", "12/merge", "12/../../x", "1;rm -rf x", "1&&id", "1|id",
               "$(id)", "`id`", "12\n", "\n12", "12\n13", "1\n; gh api -X PUT x", "٣", "１２", "12 -X PUT", "-X", "--input", "--hostname=x",
               "12/ccr/ready_for_review", "repos/bondo/listicles2/pulls/12/merge"]
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
        with open(WRAPPER, encoding="utf-8") as f:
            src = f.read()
        for bad in ['"$@"', "$*", "merge", "PUT", "DELETE", "--input", "--hostname", "eval ", "-H "]:
            self.assertNotIn(bad, src, bad)
        self.assertEqual(src.count("gh api"), 1)
        self.assertIn("repos/bondo/listicles2/pulls/", src)


if __name__ == "__main__":
    unittest.main()
