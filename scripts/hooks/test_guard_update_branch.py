"""The project allow rule `Bash(scripts/update-branch.sh *)` approves any command that starts with that text (#15 comment 7008033864), so the guard
treats it like mark-ready.sh (test_guard_mark_ready.py): every file named update-branch.sh is a process file, and a command that runs one is allowed
only as exactly `scripts/update-branch.sh <PR number> <40-hex sha>`, as the whole command, from the project root, with the pinned content.
Run: python3 -I -m unittest discover -s scripts/hooks"""

import hashlib
import os
import re
import shutil
import unittest

import gitenv  # noqa: F401  # justified: imported for its side effect, drops GIT_DIR and friends (see gitenv.py)
import pretooluse_guard
from test_pretooluse_guard import repo, run

TOOLING = {"LISTICLES_TASK": "tooling"}
ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
REAL = os.path.join(ROOT, "scripts", "update-branch.sh")
SHA = "0123456789abcdef0123456789abcdef01234567"
CALL = f"scripts/update-branch.sh 12 {SHA}"


def read_bytes(path):
    with open(path, "rb") as f:
        return f.read()


def fresh(content=None):
    d = repo()
    os.makedirs(os.path.join(d, "app", "scripts"))
    os.makedirs(os.path.join(d, "scripts"), exist_ok=True)
    with open(os.path.join(d, "scripts", "update-branch.sh"), "wb") as f:
        f.write(read_bytes(REAL) if content is None else content)
    return d


class UpdateBranchGuard(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = fresh()

    def bash(self, c, cwd=None, env=None):
        return run("Bash", {"command": c}, cwd or self.d, env)

    def test_exact_call_from_the_project_root_is_allowed(self):
        for c in (CALL, CALL + "\n", " " + CALL + " ", f"scripts/update-branch.sh 1 {'f' * 40}"):
            self.assertEqual(self.bash(c), 0, c)
            self.assertEqual(self.bash(c, env=TOOLING), 0, c + " (tooling)")

    def test_every_other_form_is_denied_even_in_a_tooling_session(self):
        cp = "cp /tmp/x/update-branch.sh scripts/"
        forms = [
            "scripts/update-branch.sh", "scripts/update-branch.sh 12", f"scripts/update-branch.sh 0 {SHA}", f"scripts/update-branch.sh 012 {SHA}",
            f"scripts/update-branch.sh 12 {SHA[:39]}", f"scripts/update-branch.sh 12 {SHA}0", f"scripts/update-branch.sh 12 {SHA.upper()}",
            CALL + " extra", CALL + " -f x=y", "scripts/update-branch.sh 12 $(id)", f"scripts/update-branch.sh $PR {SHA}",
            f"scripts/update-branch.sh 12 {SHA[:30]}*",
            "./" + CALL, "app/" + CALL, "/work/" + CALL, "FOO=1 " + CALL, "env " + CALL, "timeout 5 " + CALL, "nohup " + CALL,
            cp + " && " + CALL, cp + " ; " + CALL, "sed -i 's/PUT/DELETE/' scripts/*.sh && " + CALL, "cd . && " + CALL, "true || " + CALL,
            CALL + " && true", CALL + " ; true", CALL + " | cat", CALL + " &", CALL + " > /dev/null", CALL + " # c", CALL + "\nrm -rf x",
            "{ " + CALL + "; }", "( " + CALL + " )", "coproc " + CALL, "trap '" + CALL + "' EXIT", "f() { " + CALL + "; }; f",
            "bash -c '" + CALL + "'", "echo '" + CALL + "' | sh", "eval '" + CALL + "'",
            "scripts/update-branch.sh\\ 12 " + SHA, '"' + CALL + '"', "cd app && " + CALL,
            # R5-02 (as for mark-ready.sh): a backslash-newline right after the name joins to `update-branch.sh12`, a file name nobody protects
            f"scripts/update-branch.sh\\\n12 {SHA}", f"scripts/update-branch.sh\\\r\n12 {SHA}", f"scripts/update-branch.sh\\\n 12 {SHA}",
        ]
        for c in forms:
            self.assertEqual(self.bash(c), 2, c)
            self.assertEqual(self.bash(c, env=TOOLING), 2, c + " (tooling)")
        self.assertEqual(self.bash(CALL, os.path.join(self.d, "app")), 2, "from a subdirectory")

    def test_writes_to_any_file_of_that_name_are_denied_unless_tooling(self):
        for c in ("echo x > scripts/update-branch.sh", "cp /tmp/x app/scripts/update-branch.sh", "sed -i s/a/b/ scripts/update-branch.sh",
                  "rm scripts/update-branch.sh", "printf x > 'scripts/update-branch.sh 1'", "tee scripts/update-branch.sh < /tmp/x"):
            self.assertEqual(self.bash(c), 2, c)
            self.assertEqual(self.bash(c, env=TOOLING), 0, (c, "tooling"))
        for tool in ("Edit", "Write", "MultiEdit"):
            self.assertEqual(run(tool, {"file_path": "app/scripts/update-branch.sh"}, self.d), 2, tool)
            self.assertEqual(run(tool, {"file_path": "app/scripts/update-branch.sh"}, self.d, TOOLING), 0, tool)

    def test_harmless_mentions_stay_allowed(self):
        for c in ("cat scripts/update-branch.sh", "git add scripts/update-branch.sh", "bash -n scripts/update-branch.sh", "ls scripts"):
            self.assertEqual(self.bash(c), 0, c)
        for p in ("scripts/update-branch.sh.md", "scripts/xupdate-branch.sh", "docs/update-branch.md", "scripts/mark-ready.shx"):
            self.assertEqual(run("Write", {"file_path": p}, self.d), 0, p)

    def test_content_pin(self):
        pin = getattr(pretooluse_guard, "UPDATE_BRANCH_SHA256", "")
        self.assertRegex(pin, r"^[0-9a-f]{64}$")
        self.assertEqual(pin, hashlib.sha256(read_bytes(REAL)).hexdigest(), "a legitimate edit of the wrapper updates the pin in the same PR")
        src = read_bytes(os.path.join(os.path.dirname(os.path.abspath(__file__)), "pretooluse_guard.py")).decode("utf-8")
        self.assertEqual(len(re.findall(r'(?m)^UPDATE_BRANCH_SHA256 = "[0-9a-f]{64}"', src)), 1)
        real = read_bytes(REAL)
        for name, content in (("appended", real + b"gh pr merge 5\n"), ("crlf", real.replace(b"\n", b"\r\n")), ("empty", b""), ("truncated", real[:-5])):
            d = fresh(content)
            self.assertEqual(run("Bash", {"command": CALL}, d), 2, name)
            self.assertEqual(run("Bash", {"command": CALL}, d, TOOLING), 2, name + " (tooling)")
        self.assertEqual(run("Bash", {"command": CALL}, repo()), 2, "missing wrapper")

    def test_a_symlinked_wrapper_directory_or_scripts_dir_is_denied_even_with_the_exact_content(self):  # R3-01 as for mark-ready.sh
        call = lambda d: run("Bash", {"command": CALL}, d)  # noqa: E731  # justified: one-use local helper
        d = fresh()  # a symlink to a copy with the exact pinned content
        copy = os.path.join(d, "copy.sh")
        shutil.copy(os.path.join(d, "scripts", "update-branch.sh"), copy)
        os.remove(os.path.join(d, "scripts", "update-branch.sh"))
        os.symlink(copy, os.path.join(d, "scripts", "update-branch.sh"))
        self.assertEqual(call(d), 2, "symlinked file")
        d = fresh()  # scripts/ swapped for a symlink to a directory holding the exact content
        shutil.move(os.path.join(d, "scripts"), os.path.join(d, "scripts.real"))
        os.symlink(os.path.join(d, "scripts.real"), os.path.join(d, "scripts"))
        self.assertEqual(call(d), 2, "symlinked scripts dir")
        d = repo()  # a directory with the right name
        os.makedirs(os.path.join(d, "scripts", "update-branch.sh"))
        self.assertEqual(call(d), 2, "directory")

    def test_the_mark_ready_wrapper_is_not_confused_with_it(self):
        self.assertEqual(self.bash("scripts/mark-ready.sh 12"), 2, "no mark-ready.sh in this repo copy: denied by its own pin, not allowed by this one")
        self.assertEqual(self.bash(f"scripts/mark-ready.sh 12 {SHA}"), 2)


if __name__ == "__main__":
    unittest.main()
