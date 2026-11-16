"""R2-01 and R2-02 of PR #86: the project allow rule `Bash(scripts/mark-ready.sh *)` approves any command that starts with that text, so the
guard must (a) treat every file named mark-ready.sh as a process file and (b) deny any command that runs a mark-ready.sh in any form except
exactly `scripts/mark-ready.sh <PR number>` from the project root. Run: python3 -I -m unittest discover -s scripts/hooks"""

import hashlib
import os
import re
import shutil
import subprocess
import unittest

import gitenv  # noqa: F401  # justified: imported for its side effect, drops GIT_DIR and friends (see gitenv.py)
import pretooluse_guard
from test_pretooluse_guard import repo, run

TOOLING = {"LISTICLES_TASK": "tooling"}
ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
REAL_WRAPPER = os.path.join(ROOT, "scripts", "mark-ready.sh")


def read_bytes(path):
    with open(path, "rb") as f:
        return f.read()


def install_wrapper(d, content=None):
    """Put a copy of the real wrapper (or the given bytes) at <d>/scripts/mark-ready.sh."""
    os.makedirs(os.path.join(d, "scripts"), exist_ok=True)
    with open(os.path.join(d, "scripts", "mark-ready.sh"), "wb") as f:
        f.write(read_bytes(REAL_WRAPPER) if content is None else content)


class MarkReadyGuard(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = repo()
        os.makedirs(os.path.join(cls.d, "app", "scripts"))
        install_wrapper(cls.d)

    def bash(self, c, cwd=None, env=None):
        return run("Bash", {"command": c}, cwd or self.d, env)

    def test_exact_call_from_the_project_root_is_allowed(self):
        for c in ["scripts/mark-ready.sh 1", "scripts/mark-ready.sh 86", "scripts/mark-ready.sh 123456",
                  "scripts/mark-ready.sh 1\n", "  scripts/mark-ready.sh 1  "]:
            self.assertEqual(self.bash(c), 0, c)

    def test_only_the_whole_command_is_allowed_never_a_compound(self):
        """R4-01: the guard hashes the wrapper before any part of the command runs, so anything that could run before (or beside) the call
        could rewrite the wrapper after the hash. The call is allowed only as the entire command."""
        d = repo()
        install_wrapper(d)  # the pinned wrapper is present, so only the compound shape can cause the denial
        call = "scripts/mark-ready.sh 1"
        forms = [  # the review's four forms, then every other way to put something before, after or beside the call
            "cp /tmp/x/mark-ready.sh scripts/ && " + call, "cp /tmp/x/mark-ready.sh scripts/ ; " + call,
            "cp -t scripts /tmp/x/mark-ready.sh && " + call,
            "sed -i 's/^exec gh/echo evil; exec gh/' scripts/*.sh && " + call,
            "git checkout other && " + call, "git switch other; " + call,
            "(sleep 1; cp /tmp/x/mark-ready.sh scripts/) & " + call,
            "tar xf e.tar && " + call, "git apply p.diff && " + call,
            "cd . && " + call, "true || " + call, "true | " + call, "echo x\n" + call, "echo x &\n" + call, "{ " + call + "; }", "( " + call + " )",
            "! " + call, "if true; then " + call + "; fi", "sleep 1 & " + call,
            call + " && cp /tmp/x/mark-ready.sh scripts/", call + " ; true", call + " || true", call + " | cat", call + " &", call + " & sleep 1",
            call + "\nrm -rf x", call + " # comment", call + " $(true)", call + " `true`", call + " > /dev/null",
            "bash -c '" + call + "'", "sh -c \"" + call + "\"", "eval '" + call + "'", "echo '" + call + "' | sh", "time " + call,
        ]
        for c in forms:
            self.assertEqual(run("Bash", {"command": c}, d), 2, c)
            self.assertEqual(run("Bash", {"command": c}, d, TOOLING), 2, c + " (tooling)")
        self.assertEqual(run("Bash", {"command": call}, d), 0)

    def test_reserved_words_and_definitions_cannot_hide_the_call(self):
        """R5-01: `coproc` (and a function body or a trap string) runs the call without the guard seeing it as the first word."""
        d = repo()
        install_wrapper(d)
        call = "scripts/mark-ready.sh 1"
        forms = ["coproc " + call, "coproc X { " + call + "; }", "coproc { " + call + "; }", "coproc X ( " + call + " )",
                 "cp -t scripts /tmp/x/mark-ready.sh && coproc " + call, "cp /tmp/x/mark-ready.sh scripts/; coproc X { " + call + "; }",
                 "function f { " + call + "; }; f", "function f() { " + call + "; }; f", "f() { " + call + "; }; f",
                 "trap '" + call + "' EXIT", "trap -- '" + call + "' EXIT",
                 "time -p " + call, "select x in a; do " + call + "; done", "until false; do " + call + "; done", "[[ -n x ]] && " + call,
                 "case x in x) " + call + ";; esac", "while true; do " + call + "; done", "for i in 1; do " + call + "; done"]
        for c in forms:
            self.assertEqual(run("Bash", {"command": c}, d), 2, c)
            self.assertEqual(run("Bash", {"command": c}, d, TOOLING), 2, c + " (tooling)")
        for c in ["coproc echo hi", "function f { echo hi; }", "trap 'echo bye' EXIT", "trap - EXIT", "trap -p"]:
            self.assertEqual(run("Bash", {"command": c}, d), 0, c + " (other uses stay allowed)")

    def test_any_other_form_is_denied(self):
        for c in ["scripts/mark-ready.sh", "scripts/mark-ready.sh 0", "scripts/mark-ready.sh 012", "scripts/mark-ready.sh 1234567",
                  "scripts/mark-ready.sh -1", "scripts/mark-ready.sh 1 2", "scripts/mark-ready.sh 1 --input x", "scripts/mark-ready.sh ''",
                  "scripts/mark-ready.sh 1x", "scripts/mark-ready.sh 1.5",
                  "./scripts/mark-ready.sh 1", "/work/scripts/mark-ready.sh 1", "app/scripts/mark-ready.sh 1", "x/../scripts/mark-ready.sh 1",
                  "FOO=1 scripts/mark-ready.sh 1", "PATH=/tmp scripts/mark-ready.sh 1", "env scripts/mark-ready.sh 1",
                  "timeout 5 scripts/mark-ready.sh 1", "nohup scripts/mark-ready.sh 1", "command scripts/mark-ready.sh 1",
                  "scripts/mark-ready.sh 1 > out.txt", "scripts/mark-ready.sh 1 <<< x", "scripts/mark-ready.sh 1 2>&1 > scripts/other.sh",
                  "xargs scripts/mark-ready.sh", "echo 1 | xargs scripts/mark-ready.sh"]:
            self.assertEqual(self.bash(c), 2, c)

    def test_substitutions_and_expansions_in_the_argument_are_denied(self):
        """R2-02: the shell runs these before the wrapper can validate anything."""
        for c in ["scripts/mark-ready.sh $(gh pr merge 5)", "scripts/mark-ready.sh `gh pr merge 5`", "scripts/mark-ready.sh $PR",
                  "scripts/mark-ready.sh ${PR}", "scripts/mark-ready.sh <(echo 1)", "scripts/mark-ready.sh $((1+1))", "scripts/mark-ready.sh 1$(id)",
                  "scripts/mark-ready.sh \"$(id)\"", "scripts/mark-ready.sh $'1\\n2'","scripts/mark-ready.sh 1*", "scripts/mark-ready.sh {1,2}"]:
            self.assertEqual(self.bash(c), 2, c)

    def test_wrong_working_directory_is_denied(self):
        app = os.path.join(self.d, "app")
        for c, cwd in [("cd app && scripts/mark-ready.sh 1", None), ("(cd app && scripts/mark-ready.sh 1)", None),
                       ("cd /tmp && scripts/mark-ready.sh 1", None), ("bash -c 'cd app && scripts/mark-ready.sh 1'", None),
                       ("scripts/mark-ready.sh 1", app), ("cd .. && cd app && scripts/mark-ready.sh 1", None),
                       ("cd $HOME && scripts/mark-ready.sh 1", None)]:
            self.assertEqual(self.bash(c, cwd), 2, (c, cwd))

    def test_planted_copy_in_a_subdirectory_cannot_be_run_or_written(self):
        self.assertEqual(self.bash("cd app && scripts/mark-ready.sh 1"), 2)
        for p in ["app/scripts/mark-ready.sh", "scripts/nested/scripts/mark-ready.sh", "scripts/mark-ready.sh",
                  os.path.join("x", "..", "app", "scripts", "mark-ready.sh")]:
            for tool in ["Edit", "Write", "MultiEdit"]:
                self.assertEqual(run(tool, {"file_path": p}, self.d), 2, (tool, p))
                self.assertEqual(run(tool, {"file_path": p}, self.d, TOOLING), 0, (tool, p, "tooling sessions may edit it"))

    def test_bash_writes_to_the_wrapper_are_denied(self):
        for c in ["echo x > scripts/mark-ready.sh", "printf x > app/scripts/mark-ready.sh", "cp /tmp/x scripts/mark-ready.sh",
                  "tee scripts/mark-ready.sh < /tmp/x", "sed -i s/a/b/ scripts/mark-ready.sh", "rm scripts/mark-ready.sh",
                  "mv /tmp/x app/scripts/mark-ready.sh", "echo x >> scripts/mark-ready.sh", "install -m 755 /tmp/x scripts/mark-ready.sh",
                  "python3 -c \"open('scripts/mark-ready.sh','w').write('x')\"", "truncate -s 0 scripts/mark-ready.sh"]:
            self.assertEqual(self.bash(c), 2, c)
            self.assertEqual(self.bash(c, env=TOOLING), 0, (c, "tooling"))

    def test_harmless_mentions_stay_allowed(self):
        for c in ["cat scripts/mark-ready.sh", "git add scripts/mark-ready.sh", "git log -- scripts/mark-ready.sh", "ls scripts",
                  "grep -n gh scripts/mark-ready.sh", "wc -l scripts/mark-ready.sh", "echo x > scripts/other.sh", "cp scripts/mark-ready.sh /tmp/x",
                  "git commit -m 'edit scripts/mark-ready.sh'", "bash -n scripts/mark-ready.sh"]:
            self.assertEqual(self.bash(c), 0, c)
        for p in ["scripts/verify.sh", "scripts/mark-ready.sh.md", "docs/mark-ready.md", "scripts/hooks-other.sh"]:
            self.assertEqual(run("Write", {"file_path": p}, self.d), 0, p)


class MarkReadyContentPin(unittest.TestCase):
    """R3-01: stop listing ways to write the wrapper; check its content when it runs. The guard pins the SHA-256 of the committed wrapper."""

    def fresh(self, content=None):
        d = repo()
        install_wrapper(d, content)
        return d

    def call(self, d, env=None):
        return run("Bash", {"command": "scripts/mark-ready.sh 1"}, d, env)

    def test_pin_matches_the_committed_wrapper(self):
        """A legitimate edit of the wrapper must update the pin in the same reviewed tooling PR."""
        pin = getattr(pretooluse_guard, "MARK_READY_SHA256", "")
        self.assertRegex(pin, r"^[0-9a-f]{64}$")
        self.assertEqual(pin, hashlib.sha256(read_bytes(REAL_WRAPPER)).hexdigest())

    def test_the_pinned_wrapper_is_allowed(self):
        self.assertEqual(self.call(self.fresh()), 0)
        self.assertEqual(self.call(self.fresh(), TOOLING), 0)

    def test_modified_content_is_denied_even_in_a_tooling_session(self):
        real = read_bytes(REAL_WRAPPER)
        for name, content in [("appended line", real + b"gh pr merge 5 --squash\n"), ("one byte", real + b"\n"),
                              ("prepended", b"gh pr merge 5\n" + real), ("crlf", real.replace(b"\n", b"\r\n")),
                              ("empty", b""), ("other script", b"#!/bin/sh\ngh pr merge 5 --squash\n"),
                              ("lowercased", real.lower()), ("truncated", real[:-5])]:
            d = self.fresh(content)
            self.assertEqual(self.call(d), 2, name)
            self.assertEqual(self.call(d, TOOLING), 2, name + " (tooling)")

    def test_rewrite_by_a_command_that_never_names_the_file_is_denied_at_run_time(self):
        """The review's R3-01 examples: the edit step is not caught by name, the run step must be."""
        d = self.fresh()
        subprocess.run(["sed", "-i", "s/^exec gh/gh pr merge 5 --squash; exec gh/"] + [os.path.join(d, "scripts", "mark-ready.sh")],
                       check=True, capture_output=True)
        self.assertEqual(self.call(d), 2)
        d = self.fresh()
        src = os.path.join(d, "x")
        os.makedirs(src)
        with open(os.path.join(src, "mark-ready.sh"), "wb") as f:
            f.write(b"#!/bin/sh\ngh pr merge 5\n")
        shutil.copy(os.path.join(src, "mark-ready.sh"), os.path.join(d, "scripts"))  # what `cp /tmp/x/mark-ready.sh scripts/` does
        self.assertEqual(self.call(d), 2)

    def test_missing_directory_and_symlinked_wrapper_are_denied(self):
        d = repo()  # no wrapper at all
        self.assertEqual(self.call(d), 2)
        d = repo()
        os.makedirs(os.path.join(d, "scripts", "mark-ready.sh"))  # a directory with the right name
        self.assertEqual(self.call(d), 2)
        d = self.fresh()  # symlink to a copy with the exact pinned content: still denied
        copy = os.path.join(d, "copy.sh")
        shutil.copy(os.path.join(d, "scripts", "mark-ready.sh"), copy)
        os.remove(os.path.join(d, "scripts", "mark-ready.sh"))
        os.symlink(copy, os.path.join(d, "scripts", "mark-ready.sh"))
        self.assertEqual(self.call(d), 2)
        d = self.fresh()  # the scripts directory itself swapped for a symlink to a directory holding the exact content
        shutil.move(os.path.join(d, "scripts"), os.path.join(d, "scripts.real"))
        os.symlink(os.path.join(d, "scripts.real"), os.path.join(d, "scripts"))
        self.assertEqual(self.call(d), 2)

    def test_pin_is_a_lowercase_sha256_constant_in_the_guard_source(self):
        src = read_bytes(os.path.join(os.path.dirname(os.path.abspath(__file__)), "pretooluse_guard.py")).decode("utf-8")
        self.assertEqual(len(re.findall(r'(?m)^MARK_READY_SHA256 = "[0-9a-f]{64}"', src)), 1)


if __name__ == "__main__":
    unittest.main()
