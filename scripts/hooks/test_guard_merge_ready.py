"""The project allow rule `Bash(python3 -I scripts/merge_ready.py *)` (owner request, orchestrator chat 2026-11-24) approves any command that starts
with that text, so the guard narrows it as it does the wrappers (test_guard_update_branch.py): a command that runs a merge_ready.py is allowed only
as the whole command, exactly `python3 -I scripts/merge_ready.py [--wait] [--approval <comment id>] <PR number> <40-hex sha> <kind>` (--approval
with kind owner-batch and only with it), from the project root, while scripts/merge_ready.py and scripts/repo_slug.py (which it imports) are
regular files with their pinned SHA-256 and no name in scripts/ shadows a standard library module (merge_ready.py puts scripts/ first on sys.path).
Run: python3 -I -m unittest discover -s scripts/hooks"""

import ast
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
FILES = ("merge_ready.py", "repo_slug.py")
SHA = "0123456789abcdef0123456789abcdef01234567"
PRE = "python3 -I scripts/merge_ready.py"
CALL = f"{PRE} 12 {SHA} general"
BATCH = f"{PRE} --approval 7085221356 12 {SHA} owner-batch"


def read_bytes(path):
    with open(path, "rb") as f:
        return f.read()


def fresh(**content):
    """A repo copy with the real merge_ready.py and repo_slug.py, or the given bytes for a name (merge_ready=b"...")."""
    d = repo()
    os.makedirs(os.path.join(d, "app", "scripts"))
    os.makedirs(os.path.join(d, "scripts"), exist_ok=True)
    for name in FILES:
        data = content.get(name[:-3], read_bytes(os.path.join(ROOT, "scripts", name)))
        if data is not None:
            with open(os.path.join(d, "scripts", name), "wb") as f:
                f.write(data)
    return d


class MergeReadyGuard(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = fresh()

    def bash(self, c, cwd=None, env=None):
        return run("Bash", {"command": c}, cwd or self.d, env)

    def test_exact_calls_from_the_project_root_are_allowed(self):
        ok = [CALL, CALL + "\n", " " + CALL + " ", BATCH, f"{PRE} --wait 12 {SHA} general", f"{PRE} --wait --approval 1 9 {'f' * 40} owner-batch",
              f"{PRE} 123456 {SHA} tasks-sync", f"{PRE} 1 {SHA} dependabot", f"{PRE} --wait 1 {SHA} working-draft-docs"]
        for c in ok:
            self.assertEqual(self.bash(c), 0, c)
            self.assertEqual(self.bash(c, env=TOOLING), 0, c + " (tooling)")

    def test_other_arguments_are_denied_even_in_a_tooling_session(self):
        self.denied([
            PRE, f"{PRE} 12 {SHA}", f"{PRE} 12 general", f"{PRE} 0 {SHA} general", f"{PRE} 012 {SHA} general", f"{PRE} 1234567 {SHA} general",
            f"{PRE} 12 {SHA[:39]} general", f"{PRE} 12 {SHA}0 general", f"{PRE} 12 {SHA.upper()} general", f"{PRE} 12 {SHA[:30]}* general",
            f"{PRE} 12 {SHA} merge", f"{PRE} 12 {SHA} General", f"{PRE} 12 {SHA} general,owner-batch", f"{PRE} 12 {SHA} owner-batch",
            f"{PRE} --approval 7 12 {SHA} general", f"{PRE} --approval 07 12 {SHA} owner-batch", f"{PRE} --approval abc 12 {SHA} owner-batch",
            f"{PRE} --approval=7 12 {SHA} owner-batch", f"{PRE} --approval 12 {SHA} owner-batch", f"{PRE} --approval 7 --wait 12 {SHA} owner-batch",
            f"{PRE} --wait --wait 12 {SHA} general", f"{PRE} 12 {SHA} general --wait", f"{PRE} 12 --wait {SHA} general", f"{PRE} --help",
            CALL + " extra", CALL + " general", f"{PRE} $PR {SHA} general", f"{PRE} 12 $(git rev-parse HEAD) general", f"{PRE} 12 {SHA} `id`",
            f"{PRE} 12 {SHA} {{general,dependabot}}", f"{PRE}  12 {SHA} general", f"{PRE}\t12 {SHA} general",
        ])

    def test_other_interpreter_and_path_forms_are_denied(self):
        args = f"12 {SHA} general"
        self.denied([
            f"python3 scripts/merge_ready.py {args}", f"python3 -I -u scripts/merge_ready.py {args}", f"python3 -IS scripts/merge_ready.py {args}",
            f"python3 -I -W ignore scripts/merge_ready.py {args}", f"python3.13 -I scripts/merge_ready.py {args}", f"python -I scripts/merge_ready.py {args}",
            f"/usr/bin/python3 -I scripts/merge_ready.py {args}", f"python3 -I ./scripts/merge_ready.py {args}",
            f"python3 -I app/scripts/merge_ready.py {args}", f"python3 -I {self.d}/scripts/merge_ready.py {args}", f"scripts/merge_ready.py {args}",
            f"./scripts/merge_ready.py {args}", f"python3 -I 'scripts/merge_ready.py' {args}", f'"{CALL}"', f"python3 -I scripts/merge_ready.py\\ {args}",
            f'python3 -I scripts/merge_ready.py""\\\n{args}', f"python3 -I scripts/merge_ready.py\\\n{args}",
            f"python3 -I scripts/merge_ready.py12 {SHA} general",
        ])
        self.assertEqual(self.bash(CALL, os.path.join(self.d, "app")), 2, "from a subdirectory")

    def test_only_the_whole_command_is_allowed(self):
        """The guard hashes the files before any part of the line runs, so nothing may run before, after or beside the call."""
        self.denied([
            "PYTHONPATH=/tmp/x " + CALL, "FOO=1 " + CALL, "env " + CALL, "timeout 5 " + CALL, "nohup " + CALL, "noglob " + CALL, "command " + CALL,
            "time " + CALL, "nice " + CALL, "sudo " + CALL, "xargs " + CALL, "cd . && " + CALL, "true || " + CALL, "true; " + CALL,
            "sed -i 's/a/b/' scripts/repo_slug.py && " + CALL, "cp /tmp/x scripts/merge_ready.py; " + CALL, "echo 'x' > scripts/pathlib.py && " + CALL,
            CALL + " && true", CALL + " ; true", CALL + " | cat", CALL + " &", CALL + " > /tmp/out", CALL + " 2>&1", CALL + " # c", CALL + "\nrm -rf x",
            CALL + " <<< x", "{ " + CALL + "; }", "( " + CALL + " )", "coproc " + CALL, "trap '" + CALL + "' EXIT", "f() { " + CALL + "; }; f",
            "bash -c '" + CALL + "'", "echo '" + CALL + "' | sh", "eval '" + CALL + "'", "$(" + CALL + ")",
        ])

    def test_harmless_mentions_stay_allowed(self):
        for c in ("cat scripts/merge_ready.py", "git add scripts/merge_ready.py", "python3 -I scripts/test_merge_ready.py",
                  "python3 -I -m unittest discover -s scripts/hooks", "grep -n KINDS scripts/merge_ready.py", "python3 -I scripts/repo_slug.py",
                  "python3 -I scripts/xmerge_ready.py 12", "python3 -c 'print(1)'"):
            self.assertEqual(self.bash(c), 0, c)

    def test_content_pins(self):
        for name, const in (("merge_ready.py", "MERGE_READY_SHA256"), ("repo_slug.py", "REPO_SLUG_SHA256")):
            pin = getattr(pretooluse_guard, const, "")
            self.assertRegex(pin, r"^[0-9a-f]{64}$", const)
            self.assertEqual(pin, hashlib.sha256(read_bytes(os.path.join(ROOT, "scripts", name))).hexdigest(),
                             f"a legitimate edit of scripts/{name} updates {const} in the same PR")
            src = read_bytes(os.path.join(os.path.dirname(os.path.abspath(__file__)), "pretooluse_guard.py")).decode("utf-8")
            self.assertEqual(len(re.findall(rf'(?m)^{const} = "[0-9a-f]{{64}}"', src)), 1, const)
        for key in ("merge_ready", "repo_slug"):
            real = read_bytes(os.path.join(ROOT, "scripts", key + ".py"))
            for what, content in (("appended", real + b"\nimport os; os.system('gh pr merge 5')\n"), ("crlf", real.replace(b"\n", b"\r\n")),
                                  ("empty", b""), ("truncated", real[:-5]), ("missing", None)):
                d = fresh(**{key: content})
                self.assertEqual(run("Bash", {"command": CALL}, d), 2, (key, what))
                self.assertEqual(run("Bash", {"command": BATCH}, d, TOOLING), 2, (key, what, "tooling"))

    def test_symlinks_and_directories_are_denied_even_with_the_exact_content(self):
        for name in FILES:
            d = fresh()
            copy = os.path.join(d, "copy.py")
            shutil.copy(os.path.join(d, "scripts", name), copy)
            os.remove(os.path.join(d, "scripts", name))
            os.symlink(copy, os.path.join(d, "scripts", name))
            self.assertEqual(run("Bash", {"command": CALL}, d), 2, "symlinked " + name)
        d = fresh()
        shutil.move(os.path.join(d, "scripts"), os.path.join(d, "scripts.real"))
        os.symlink(os.path.join(d, "scripts.real"), os.path.join(d, "scripts"))
        self.assertEqual(run("Bash", {"command": CALL}, d), 2, "symlinked scripts dir")
        d = fresh(merge_ready=None)
        os.makedirs(os.path.join(d, "scripts", "merge_ready.py"))
        self.assertEqual(run("Bash", {"command": CALL}, d), 2, "directory")

    def test_a_name_in_scripts_that_shadows_the_standard_library_is_denied(self):
        """merge_ready.py inserts scripts/ at the front of sys.path, so scripts/pathlib.py would run in place of the module repo_slug imports."""
        for planted in ("pathlib.py", "json.py", "_strptime.pyc", "subprocess.cpython-313-x86_64-linux-gnu.so", "collections/__init__.py", "selectors"):
            d = fresh()
            path = os.path.join(d, "scripts", planted)
            if "." in planted:  # a module file, or a package's __init__.py
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "w", encoding="utf-8") as f:
                    f.write("import os\n")
            else:  # a directory without __init__.py (a namespace package)
                os.makedirs(path)
            self.assertEqual(run("Bash", {"command": CALL}, d), 2, planted)
            self.assertEqual(run("Bash", {"command": CALL}, d, TOOLING), 2, planted + " (tooling)")
        d = fresh()
        for harmless in ("tasks.py", "status_page.py", "linters.pins", "test_merge_ready.py"):
            with open(os.path.join(d, "scripts", harmless), "w", encoding="utf-8") as f:
                f.write("x = 1\n")
        os.makedirs(os.path.join(d, "scripts", "hooks"))
        self.assertEqual(run("Bash", {"command": CALL}, d), 0, "names that are not standard library modules")

    def test_the_real_scripts_directory_shadows_nothing(self):
        self.assertEqual(run("Bash", {"command": CALL}, ROOT), 0, "the checkout itself passes the guard")

    def test_kinds_match_merge_ready(self):
        """The guard's kind list is merge_ready.py's KINDS (owner-batch is the one that takes --approval)."""
        src = read_bytes(os.path.join(ROOT, "scripts", "merge_ready.py")).decode("utf-8")
        kinds = ast.literal_eval(re.search(r"(?m)^KINDS = (\{.*\})$", src).group(1))
        self.assertEqual(set(pretooluse_guard.MERGE_KINDS) | {"owner-batch"}, kinds)
        self.assertNotIn("owner-batch", pretooluse_guard.MERGE_KINDS)

    def denied(self, forms):
        for c in forms:
            self.assertEqual(self.bash(c), 2, c)
            self.assertEqual(self.bash(c, env=TOOLING), 2, c + " (tooling)")


if __name__ == "__main__":
    unittest.main()
