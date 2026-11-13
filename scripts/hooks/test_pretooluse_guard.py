"""Tests for pretooluse_guard.py. Run: python3 -m unittest discover -s scripts/hooks"""

import json
import os
import subprocess
import sys
import tempfile
import unittest

import gitenv  # noqa: F401  # justified: imported for its side effect, drops GIT_DIR and friends (see gitenv.py)

GUARD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pretooluse_guard.py")


def run(tool, tool_input, cwd, env=None):
    e = {k: v for k, v in os.environ.items() if k not in ("LISTICLES_TASK", "CLAUDE_PROJECT_DIR")}
    e.update(env or {})
    r = subprocess.run(
        [sys.executable, "-I", GUARD],
        input=json.dumps({"tool_name": tool, "tool_input": tool_input, "cwd": cwd}),
        capture_output=True, text=True, env=e,
    )
    return r.returncode


def sh(cwd, *a):
    subprocess.run(a, cwd=cwd, check=True, capture_output=True)


def repo(branch="work"):
    d = tempfile.mkdtemp()
    sh(d, "git", "init", "-q", "-b", branch)
    sh(d, "git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "i")
    return d


class Guard(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = tempfile.mkdtemp()
        sh(cls.d, "git", "init", "-q", "-b", "work")
        sh(cls.d, "git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "i")

    def bash(self, c, **kw):
        return run("Bash", {"command": c}, self.d, **kw)

    def dirty(self, on):
        p = os.path.join(self.d, "f.txt")
        if on:
            open(p, "w").write("x")
        elif os.path.exists(p):
            os.remove(p)

    def test_allows_normal_git(self):
        self.dirty(False)
        for c in ["git status", "git commit -m x", "git push -u origin work", "git push --force-with-lease origin work",
                  "git log --oneline | head", "git reset --hard HEAD~1", "git diff -n"]:
            self.assertEqual(self.bash(c), 0, c)

    def test_denies_no_verify(self):
        for c in ["git commit --no-verify -m x", "git commit -n -m x", "git commit -an -m x", "git push --no-verify",
                  "git -c core.hooksPath=/dev/null commit -m x", "git config core.hooksPath /x",
                  "cd /tmp && git commit --no-verify"]:
            self.assertEqual(self.bash(c), 2, c)

    def test_denies_force_and_main(self):
        for c in ["git push --force", "git push -f origin work", "git push origin +work", "git push origin HEAD:main",
                  "git push origin main", "git push origin refs/heads/main", "git push --delete origin main",
                  "git push --all", "git push origin :main"]:
            self.assertEqual(self.bash(c), 2, c)

    def test_denies_bare_push_on_main(self):
        d = tempfile.mkdtemp()
        sh(d, "git", "init", "-q", "-b", "main")
        self.assertEqual(run("Bash", {"command": "git push"}, d), 2)

    def test_destructive_only_when_dirty(self):
        cmds = ["git reset --hard", "git checkout .", "git checkout -- a", "git checkout -f x", "git restore a", "git clean -fd",
                "git stash", "git stash -u", "git switch -f x"]
        self.dirty(True)
        for c in cmds:
            self.assertEqual(self.bash(c), 2, c)
        self.assertEqual(self.bash("git restore --staged a"), 0)
        self.assertEqual(self.bash("git stash list"), 0)
        self.dirty(False)
        for c in ["git reset --hard", "git restore a"]:
            self.assertEqual(self.bash(c), 0, c)
        self.assertEqual(self.bash("git stash drop"), 2)

    def test_hard_reset_on_main_always_denied(self):
        d = tempfile.mkdtemp()
        sh(d, "git", "init", "-q", "-b", "main")
        self.assertEqual(run("Bash", {"command": "git reset --hard origin/main"}, d), 2)

    def test_evasions(self):
        self.dirty(True)
        for c in ["bash -c 'git reset --hard'", "FOO=1 git reset --hard", "env git reset --hard", "true; git reset --hard",
                  "git -C . reset --hard", "git reset --hard && echo hi", "sudo git reset --hard",
                  "git 'reset --hard", "echo $(git reset --hard)"]:
            self.assertEqual(self.bash(c), 2, c)
        self.dirty(False)

    def test_process_files(self):
        for t in ["Edit", "Write"]:
            for p in ["CLAUDE.md", "REVIEW.md", "agents/roles.yaml", ".claude/settings.json", ".github/workflows/ci.yml",
                      "scripts/guards.sh", "scripts/hooks/pretooluse_guard.py", "sub/../CLAUDE.md", os.path.join(self.d, "CLAUDE.md")]:
                self.assertEqual(run(t, {"file_path": p}, self.d), 2, (t, p))
            for p in ["README.md", "app/src/Main.kt", "docs/PLAN.md", "scripts/verify.sh", "/tmp/x"]:
                self.assertEqual(run(t, {"file_path": p}, self.d), 0, (t, p))

    def test_tooling_flag_allows_edits(self):
        self.assertEqual(run("Edit", {"file_path": "CLAUDE.md"}, self.d, {"LISTICLES_TASK": "tooling"}), 0)
        self.assertEqual(self.bash("sed -i s/a/b/ CLAUDE.md", env={"LISTICLES_TASK": "tooling"}), 0)

    def test_bash_writes_to_process_files(self):
        for c in ["sed -i s/a/b/ CLAUDE.md", "echo x > .claude/settings.json", "cp x agents/roles.yaml", "rm -rf .github",
                  "tee REVIEW.md < x", "git checkout origin/main -- CLAUDE.md"]:
            self.assertEqual(self.bash(c), 2, c)
        for c in ["cat CLAUDE.md", "grep -n x REVIEW.md", "ls .claude", "git log -- agents/"]:
            self.assertEqual(self.bash(c), 0, c)

    def test_m011_harmless_mentions_are_allowed(self):
        """M0-11 item 5: a harmless command that merely names a protected path, or says git inside quotes or a heredoc."""
        self.dirty(False)
        for c in ["ls .github", "wc -l REVIEW.md", "find .github -name '*.yml'", "tar czf /tmp/a.tgz agents/", "diff REVIEW.md /tmp/x",
                  "cp REVIEW.md /tmp/x", "echo x > /tmp/CLAUDE.md", "echo x | tee /tmp/REVIEW.md", "git add CLAUDE.md",
                  "git commit -m 'edit REVIEW.md and git push rules'", "echo 'use git push --force on main'", "grep -rn 'git stash' docs/",
                  "cat <<'EOF' > /tmp/n.md\nit's the git workflow, \"unbalanced\nEOF",
                  "git commit -m \"$(cat <<'EOF'\nUpdate REVIEW.md (git push rules)\nEOF\n)\"",
                  "cd agents && ls", "for f in agents/prompts/*.md; do wc -l \"$f\"; done"]:
            self.assertEqual(self.bash(c), 0, c)

    def test_m011_harmful_forms_stay_blocked(self):
        """The same paths and words, used to write or to run a forbidden git command, are still denied."""
        self.dirty(False)
        for c in ["perl -pi -e s/a/b/ REVIEW.md", "sed -i.bak s/a/b/ agents/prompts/reviewer.md", "dd if=/tmp/x of=CLAUDE.md",
                  "echo x >> agents/roles.yaml", "bash -c 'echo x > REVIEW.md'", "cd agents && echo x > roles.yaml", "cd .github && touch x",
                  "ln -sf /tmp/x CLAUDE.md", "git checkout main -- REVIEW.md", "git restore REVIEW.md",
                  "python3 -c \"open('REVIEW.md','w').write('x')\"", "git push --force origin work", "git commit --no-verify -m x"]:
            self.assertEqual(self.bash(c), 2, c)

    def test_other_tools_and_garbage(self):
        self.assertEqual(run("Read", {"file_path": "CLAUDE.md"}, self.d), 0)
        r = subprocess.run([sys.executable, "-I", GUARD], input="not json", capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)


if __name__ == "__main__":
    unittest.main()
