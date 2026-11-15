"""R2-01 and R2-02 of PR #86: the project allow rule `Bash(scripts/mark-ready.sh *)` approves any command that starts with that text, so the
guard must (a) treat every file named mark-ready.sh as a process file and (b) deny any command that runs a mark-ready.sh in any form except
exactly `scripts/mark-ready.sh <PR number>` from the project root. Run: python3 -I -m unittest discover -s scripts/hooks"""

import os
import unittest

import gitenv  # noqa: F401  # justified: imported for its side effect, drops GIT_DIR and friends (see gitenv.py)
from test_pretooluse_guard import repo, run

TOOLING = {"LISTICLES_TASK": "tooling"}


class MarkReadyGuard(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = repo()
        os.makedirs(os.path.join(cls.d, "app", "scripts"))

    def bash(self, c, cwd=None, env=None):
        return run("Bash", {"command": c}, cwd or self.d, env)

    def test_exact_call_from_the_project_root_is_allowed(self):
        for c in ["scripts/mark-ready.sh 1", "scripts/mark-ready.sh 86", "scripts/mark-ready.sh 123456", "cd . && scripts/mark-ready.sh 7"]:
            self.assertEqual(self.bash(c), 0, c)

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


if __name__ == "__main__":
    unittest.main()
