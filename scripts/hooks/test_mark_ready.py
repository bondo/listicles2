"""scripts/mark-ready.sh is the only thing the project permission rule lets agents run to mark a PR ready.
It must accept exactly one PR number and make exactly one fixed call. The wrapper finds `gh` only in the directories on its `gh_dirs=` line (never
through PATH, R5-03), so a fake `gh` records the call through a copy of the real file whose `gh_dirs=` line is replaced. A decoy `gh` in PATH must never run.
Run: python3 -I -m unittest discover -s scripts/hooks"""

import os
import re
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
    'printf "%s" "$PATH" > "$FAKE_GH_OUT.path"\n'
)
GH_DIRS_LINE = re.compile(r'(?m)^gh_dirs="[^"\n]*"$')


def read_wrapper():
    with open(WRAPPER, encoding="utf-8") as f:
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

    def copy_with_gh_dirs(self, dirs):
        """A copy of the real wrapper whose gh_dirs line is replaced; fails if the real file has no such single line."""
        src = read_wrapper()
        self.assertEqual(len(GH_DIRS_LINE.findall(src)), 1, 'scripts/mark-ready.sh needs exactly one line: gh_dirs="<absolute dirs>"')
        path = os.path.join(self.tmp.name, "mark-ready-copy.sh")
        with open(path, "w", encoding="utf-8") as f:
            f.write(GH_DIRS_LINE.sub(lambda _: f'gh_dirs="{dirs}"', src))
        return path

    def run_wrapper(self, *args, env=None, dirs=None):
        e = {"PATH": self.decoy + os.pathsep + "/usr/bin:/bin", "FAKE_GH_OUT": self.out}
        e.update(env or {})
        script = self.copy_with_gh_dirs(self.fixed if dirs is None else dirs)
        p = subprocess.run(["bash", script, *args], capture_output=True, text=True, env=e, cwd=ROOT, timeout=30)
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
        src = read_wrapper()
        for bad in ['"$@"', "$*", "merge", "PUT", "DELETE", "--input", "--hostname", "eval ", "-H "]:
            self.assertNotIn(bad, src, bad)
        self.assertEqual(src.count("api -X POST"), 1)
        self.assertEqual(len(re.findall(r'exec "\$d/gh" api -X POST "repos/bondo/listicles2/pulls/\$\{n\}/ccr/ready_for_review"', src)), 1)

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
