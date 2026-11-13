"""More PreToolUse guard tests (review round 1, R9-01..R9-06): multi-line commands, project root, false positives,
equivalent forms. Run: python3 -I -m unittest discover -s scripts/hooks"""

import os
import tempfile
import unittest

from test_pretooluse_guard import repo, run

import gitenv  # noqa: F401  # justified: imported for its side effect, drops GIT_DIR and friends (see gitenv.py)

TOOLING = {"LISTICLES_TASK": "tooling"}


class Forms(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = repo()
        cls.main = repo("main")

    def setUp(self):
        self.dirty(False)

    def dirty(self, on):
        p = os.path.join(self.d, "f.txt")
        if on:
            with open(p, "w") as f:
                f.write("x")
        elif os.path.exists(p):
            os.remove(p)

    def bash(self, c, cwd=None, env=None):
        return run("Bash", {"command": c}, cwd or self.d, env)

    def denied(self, cmds, **kw):
        for c in cmds:
            self.assertEqual(self.bash(c, **kw), 2, c)

    def allowed(self, cmds, **kw):
        for c in cmds:
            self.assertEqual(self.bash(c, **kw), 0, c)

    # R9-01
    def test_multiline_commands_are_checked_per_line(self):
        self.dirty(True)
        self.denied(["echo hi\ngit reset --hard", "git status\ngit commit --no-verify -m x", "git commit -m x \\\n --no-verify",
                     "cat <<EOF\nok\nEOF\ngit push origin main", "echo a;\n\ngit push --force", "true\r\ngit push origin main"])
        self.denied(["cat <<EOF\n$(git reset --hard)\nEOF", "bash <<EOF\ngit push origin main\nEOF"])

    def test_heredoc_and_quoted_text_is_data(self):
        self.dirty(True)
        self.allowed(["cat <<'EOF'\ngit push --force\ngit reset --hard\nEOF", 'git commit -m "docs: say git reset --hard is blocked"',
                      "git commit -m \"$(cat <<'EOF'\nfix: do not git push --force or git reset --hard\nEOF\n)\"",
                      "echo 'git push origin main'", "git commit -m 'edit CLAUDE.md with sed -i'"])

    # R9-02
    def test_process_files_use_project_root_not_cwd(self):
        proj = repo()
        out = tempfile.mkdtemp()  # not a git repo
        f = os.path.join(proj, "CLAUDE.md")
        self.assertEqual(run("Edit", {"file_path": f}, out, {"CLAUDE_PROJECT_DIR": proj}), 2)
        self.assertEqual(run("Edit", {"file_path": f}, out), 2)  # root found from the file's own repo
        self.assertEqual(run("Write", {"file_path": os.path.join(proj, "agents", "x.md")}, out), 2)
        self.assertEqual(run("Edit", {"file_path": os.path.join(proj, "README.md")}, out, {"CLAUDE_PROJECT_DIR": proj}), 0)
        self.assertEqual(run("Edit", {"file_path": f}, out, {"CLAUDE_PROJECT_DIR": proj, **TOOLING}), 0)
        self.assertEqual(self.bash(f"echo x > {f}", cwd=out, env={"CLAUDE_PROJECT_DIR": proj}), 2)
        self.assertEqual(self.bash(f"echo x > {f}", cwd=out), 2)

    def test_process_files_from_subdirectory(self):
        os.makedirs(os.path.join(self.d, "sub"), exist_ok=True)
        self.assertEqual(run("Edit", {"file_path": "../CLAUDE.md"}, os.path.join(self.d, "sub")), 2)
        self.denied(["echo x > ../CLAUDE.md"], cwd=os.path.join(self.d, "sub"))

    # R9-05
    def test_no_false_positives(self):
        self.dirty(True)
        self.allowed(["git status 2>&1", "git log --oneline 2>/dev/null | head", "git diff 2>&1 | head", "git merge -n origin/x",
                      "git push -n origin work", "git log -n 5", "git fetch origin 2>&1 | tail -3", "ls .claude/ 2>&1",
                      "echo 'edit CLAUDE.md' > /tmp/out.txt", "cat CLAUDE.md > /tmp/out.txt", "cp CLAUDE.md /tmp/x", "cp -r agents /tmp/agents2",
                      "grep -rn 'sed -i' CLAUDE.md REVIEW.md", "echo rm CLAUDE.md", "wc -l .github/workflows/ci.yml | tee /tmp/n",
                      "git diff origin/main -- CLAUDE.md agents/", "git show HEAD:CLAUDE.md > /tmp/old", "git checkout -b newbranch",
                      "git checkout -b other origin/main", "git checkout work", "git restore --staged f.txt", "git restore -S f.txt",
                      "gh pr create --body \"$(cat <<'EOF'\nUsed git push --force once; see CLAUDE.md\nEOF\n)\""])

    # R9-06
    def test_abbreviated_options(self):
        self.denied(["git commit --no-verif -m x", "git commit --no-ver -m x", "git push --no-ver", "git push --mirro", "git push --al",
                     "git merge --no-verify"])
        self.dirty(True)
        self.denied(["git reset --har", "git switch --forc x", "git switch --discard x", "git checkout --forc x", "git clean --forc"])

    def test_refspec_forms_for_shared_branches(self):
        self.denied(["git push origin HEAD:heads/main", "git push origin HEAD:refs/heads/main", "git push origin work:master",
                     "git push origin HEAD:refs/heads/master", "git push origin refs/heads/work:refs/heads/main", "git push origin :heads/main"])
        self.assertEqual(self.bash("git push origin HEAD", cwd=self.main), 2)
        self.assertEqual(self.bash("git push origin @", cwd=self.main), 2)
        self.assertEqual(self.bash("git push origin HEAD", cwd=self.d), 0)
        self.assertEqual(self.bash("git push origin work:work2", cwd=self.d), 0)

    def test_checkout_with_tree_and_path_is_destructive(self):
        self.dirty(True)
        self.denied(["git checkout HEAD f.txt", "git checkout work f.txt", "git checkout f.txt", "git checkout -p", "git checkout HEAD *.txt",
                     "git restore --staged --worktree f.txt", "git restore --source=HEAD f.txt", "git rm -f f.txt"])
        self.dirty(False)
        self.allowed(["git checkout HEAD f.txt", "git restore f.txt"])

    def test_wrappers_do_not_hide_git(self):
        self.denied(["timeout 10 git push --force", "timeout -s KILL 5 git push origin main", "nice -n 5 git push origin main",
                     "sudo -u root git push origin main", "env -i git push origin main", "env GIT_X=1 git push origin main",
                     "command git push origin main", "setsid git push origin main", "nohup git push --force", "stdbuf -o L git push origin main",
                     "find . -exec git push origin main \\;", "if true; then git push origin main; fi", "bash -lc 'git push origin main'",
                     "sh -c \"git commit --no-verify\"", 'eval "git push origin main"', "(git push origin main)", "{ git push origin main; }",
                     "time git push origin main", "xargs git push origin main", "env -S 'git push origin main'", "flock /tmp/l git push origin main",
                     "git push origin main 2>&1 | tail"])
        self.dirty(True)
        self.denied(["timeout -s KILL 5 git reset --hard", "nohup git clean -fd", "find . -exec git reset --hard \\;", "$G reset --hard"])

    def test_config_based_bypasses(self):
        self.denied(["GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=core.hooksPath GIT_CONFIG_VALUE_0=/dev/null git commit -m x",
                     "GIT_CONFIG_PARAMETERS=\"'core.hookspath=/x'\" git commit -m x", "export GIT_CONFIG_PARAMETERS=\"'core.hookspath=/x'\"",
                     "git --config-env=core.hooksPath=FOO commit -m x", "git -c alias.x='!git push --force' x",
                     "git config alias.pf '!git push --force'", "git config --global core.hookspath /x", "git config core.hooksPath"])
        self.allowed(["git config --get alias.pf", "git config --list", "git config user.name"])

    def test_git_internals_are_always_protected(self):
        for env in (None, TOOLING):
            self.denied(["echo x >> .git/config", "sed -i s/a/b/ .git/config", "echo x > .git/hooks/pre-commit", "cp /tmp/x .git/hooks/pre-push",
                         "git -C . config core.hooksPath /x"], env=env)
        self.allowed(["cat .git/config", "ls .git/hooks", "grep hooksPath .git/config"])

    def test_bash_write_forms_to_process_files(self):
        self.denied(["git checkout HEAD -- CLAUDE.md", "git checkout HEAD CLAUDE.md", "git restore CLAUDE.md", "git rm -f CLAUDE.md",
                     "mv CLAUDE.md /tmp/x", "cp /tmp/x CLAUDE.md", "printf x | tee -a agents/prompts/reviewer.md", "perl -pi -e s/a/b/ REVIEW.md",
                     "python3 -c \"open('CLAUDE.md','w').write('x')\"", "cat > CLAUDE.md <<EOF\nx\nEOF", "echo x>CLAUDE.md", "cd agents && rm roles.yaml",
                     "dd if=/dev/zero of=CLAUDE.md", "sed -i.bak s/a/b/ .github/workflows/ci.yml", "sed --in-place s/a/b/ CLAUDE.md",
                     "find .github -delete", "ln -sf /tmp/x CLAUDE.md", 'echo x > "$CLAUDE_PROJECT_DIR/CLAUDE.md"', "echo x > $ROOT/CLAUDE.md",
                     "truncate -s 0 REVIEW.md", "touch scripts/hooks/new.py", "install -m 644 /tmp/x .claude/settings.json",
                     "echo a\necho b >> REVIEW.md", "chmod +x scripts/guards.sh", "rm -f ./.githooks/pre-commit"])
        self.allowed(["sed -i s/a/b/ README.md", "echo x > docs/new.md", "rm -f /tmp/CLAUDE.md", "cd /tmp && echo x > CLAUDE.md"])

    def test_tooling_session_may_write_process_files_but_not_bypass_git_rules(self):
        self.allowed(["echo x > CLAUDE.md", "cp /tmp/x agents/roles.yaml", "git checkout HEAD -- CLAUDE.md"], env=TOOLING)
        self.denied(["git push origin main", "git commit --no-verify -m x", "git push --force"], env=TOOLING)

    def test_unparseable_commands_fail_closed(self):
        self.denied(["git commit -m 'unterminated", 'echo "x > CLAUDE.md'])
        self.allowed(["echo 'unterminated"])


if __name__ == "__main__":
    unittest.main()
