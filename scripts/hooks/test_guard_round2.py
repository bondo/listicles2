"""PreToolUse guard tests for review round 2 (R10-01..R10-09): interpreter stdin, untested branches, push/config/alias forms,
expansions, subshells, wrappers, false positives. Run: python3 -I -m unittest discover -s scripts/hooks"""

import json
import os
import subprocess
import sys
import tempfile
import unittest

from test_pretooluse_guard import GUARD, repo, run

import gitenv  # noqa: F401  # justified: imported for its side effect, drops GIT_DIR and friends (see gitenv.py)

TOOLING = {"LISTICLES_TASK": "tooling"}


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = repo()

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


class InterpreterStdin(Base):
    """R10-01: code fed to an interpreter or shell through a heredoc, here-string or pipe is checked like -c code."""

    def test_denied_forms(self):
        self.denied([
            "python3 - <<'PY'\nopen('CLAUDE.md','w').write('x')\nPY",
            "python3 <<'PY'\nimport subprocess; subprocess.run(['git','push','--force'])\nPY",
            "bash <<< 'git push --force'",
            "echo 'git push --force' | bash",
            "printf 'git push origin main\\n' | sh",
            "echo \"open('CLAUDE.md','w')\" | python3",
            "cat <<'EOF' | bash\ngit push --force\nEOF",
            "python3 -c \"import subprocess; subprocess.run(['git','push','--force'])\"",
            "node -e \"require('child_process').execSync('git push origin main')\"",
        ])

    def test_allowed_forms(self):
        self.allowed([
            "python3 - <<'PY'\nopen('/tmp/x','w').write('x')\nPY",
            "echo hi | bash",
            "bash <<< 'echo hi'",
            "python3 -c \"import subprocess; subprocess.run(['git','status'])\"",
            "cat <<'EOF' | python3\nprint(1)\nEOF",
        ])

    def test_tooling_may_write_process_files_but_never_git_internals(self):
        self.assertEqual(self.bash("python3 - <<'PY'\nopen('CLAUDE.md','w').write('x')\nPY", env=TOOLING), 0)
        self.assertEqual(self.bash("python3 - <<'PY'\nopen('.git/config','w').write('x')\nPY", env=TOOLING), 2)


class UntestedBranches(Base):
    """R10-02: each of these survived a mutation run (the branch could be deleted with the suite still green)."""

    def test_internal_error_fails_closed(self):
        code = (f"import sys; sys.path.insert(0, {os.path.dirname(GUARD)!r}); import pretooluse_guard as g\n"
                "g.check_bash = lambda *a: 1 / 0\ng.run_guarded()")
        r = subprocess.run([sys.executable, "-I", "-c", code], input=json.dumps({"tool_name": "Bash", "tool_input": {"command": "ls"}, "cwd": self.d}),
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("internal error", r.stderr)

    def test_claude_project_dir_is_a_root_even_when_not_a_git_repo(self):
        proj, out = tempfile.mkdtemp(), tempfile.mkdtemp()
        f = os.path.join(proj, "CLAUDE.md")
        self.assertEqual(run("Edit", {"file_path": f}, out, {"CLAUDE_PROJECT_DIR": proj}), 2)
        self.assertEqual(run("Edit", {"file_path": f}, out), 0)  # nothing marks proj as the project without it
        self.assertEqual(run("Edit", {"file_path": os.path.join(proj, "README.md")}, out, {"CLAUDE_PROJECT_DIR": proj}), 0)

    def test_bare_push_of_a_branch_tracking_main_is_denied(self):
        d = repo("work")
        subprocess.run(["git", "config", "branch.work.remote", "origin"], cwd=d, check=True)
        subprocess.run(["git", "config", "branch.work.merge", "refs/heads/main"], cwd=d, check=True)
        self.assertEqual(run("Bash", {"command": "git push"}, d), 2)
        subprocess.run(["git", "config", "branch.work.merge", "refs/heads/work"], cwd=d, check=True)
        self.assertEqual(run("Bash", {"command": "git push"}, d), 0)

    def test_custom_git_dir_counts_as_dirty(self):
        self.denied(["git --git-dir=.git --work-tree=. reset --hard", "git --git-dir .git reset --hard"])
        self.allowed(["git --no-pager reset --hard", "git reset --hard"])  # clean tree, plain forms

    def test_update_ref_delete_and_read_tree_reset_when_dirty(self):
        self.allowed(["git update-ref -d refs/heads/x", "git read-tree --reset HEAD"])
        self.dirty(True)
        self.denied(["git update-ref -d refs/heads/x", "git read-tree --reset HEAD"])

    def test_attached_c_option_for_hooks_path(self):
        self.denied(["git -ccore.hooksPath=/x commit -m x", "git --config-env=core.hooksPath=FOO commit -m x"])

    def test_inline_code_tooling_exemption_is_only_for_process_files(self):
        self.denied(["python3 -c \"open('CLAUDE.md','w')\"", "python3 -c \"open('.git/hooks/pre-commit','w')\""])
        self.assertEqual(self.bash("python3 -c \"open('CLAUDE.md','w')\"", env=TOOLING), 0)
        self.assertEqual(self.bash("python3 -c \"open('.git/hooks/pre-commit','w')\"", env=TOOLING), 2)

    def test_deep_nesting_is_denied(self):
        cmd = "ls"
        for _ in range(10):
            cmd = "bash -c '" + cmd.replace("'", "'\\''") + "'"
        self.denied([cmd])
        self.allowed(["bash -c 'bash -c ls'"])

    def test_ansi_c_quoting_is_decoded(self):
        self.denied(["git push $'--force'", "git push $'\\x2d\\x2dforce'"])

    def test_checkout_theirs_and_clean_x_when_dirty(self):
        self.allowed(["git checkout --theirs f.txt", "git clean -x"])
        self.dirty(True)
        self.denied(["git checkout --theirs f.txt", "git checkout --ours f.txt", "git clean -x", "git clean -fd"])

    def test_process_substitution_is_checked(self):
        self.denied(["cat <(git push --force)", "diff <(echo a) >(git push origin main)"])
        self.allowed(["diff <(echo a) <(echo b)"])


class PushConfigAliasForms(Base):
    """R10-03, R10-04."""

    def test_push_forms_that_reach_main(self):
        self.denied(["git push origin :", "git push origin +:", "git push origin 'refs/heads/ma*:refs/heads/ma*'",
                     "git push origin 'HEAD:refs/heads/mas*'", "git -c remote.origin.push=HEAD:refs/heads/main push origin",
                     "git -c push.default=matching push origin", "git config remote.origin.push HEAD:refs/heads/main",
                     "git push --delete origin main", "git push origin work:main"])

    def test_push_option_values_are_not_the_remote(self):
        d = repo("main")
        self.assertEqual(run("Bash", {"command": "git push -o ci.skip origin"}, d), 2)
        self.assertEqual(run("Bash", {"command": "git push --push-option=ci.skip"}, d), 2)
        self.allowed(["git push -o ci.skip origin work", "git push origin work", "git push -u origin work", "git config --get remote.origin.push"])

    def test_include_path_and_config_file_overrides_are_denied(self):
        self.denied(["git -c include.path=/tmp/x.cfg commit -m x",
                     "GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=include.path GIT_CONFIG_VALUE_0=/tmp/x.cfg git commit -m x",
                     "git config include.path /tmp/x.cfg", "git config --global includeIf.gitdir:/.path /tmp/x",
                     "GIT_CONFIG_GLOBAL=/tmp/g git commit -m x", "GIT_CONFIG_SYSTEM=/tmp/g git push origin work",
                     "export GIT_CONFIG_GLOBAL=/tmp/g", "printf x >> ~/.gitconfig", "echo x > ~/.config/git/config"])
        self.allowed(["git config --get include.path", "git config user.name x"])

    def test_aliases_in_config_are_resolved(self):
        d = repo()
        for k, v in (("alias.pf", "push --force"), ("alias.st", "status"), ("alias.nuke", "!git reset --hard"), ("alias.up", "push origin main")):
            subprocess.run(["git", "config", k, v], cwd=d, check=True)
        with open(os.path.join(d, "f.txt"), "w") as f:
            f.write("x")
        for c in ("git pf origin work", "git nuke", "git up"):
            self.assertEqual(run("Bash", {"command": c}, d), 2, c)
        for c in ("git st", "git status"):
            self.assertEqual(run("Bash", {"command": c}, d), 0, c)


class Expansions(Base):
    """R10-05, R10-06."""

    def test_variables_and_substitutions_in_arguments(self):
        self.dirty(True)
        self.denied(["H=--hard; git reset $H", "git reset $(echo --hard)", "B=main; git push origin \"HEAD:$B\"",
                     "echo --hard | xargs git reset", "echo main | xargs git push origin", "D=agents; cd $D && rm roles.yaml",
                     "cd $UNKNOWN && echo x > roles.yaml", "git push origin \"HEAD:$UNKNOWN\""])
        self.dirty(False)
        self.allowed(["git log $REV", "git push origin work", "git commit -m \"$(cat <<'EOF'\nmsg\nEOF\n)\"", "D=/tmp; cd $D && echo x > y",
                      "cd \"$(git rev-parse --show-toplevel)\" && echo x > /tmp/y", "git push -u origin $(git branch --show-current)",
                      "git reset $REV", "git checkout $BRANCH"])

    def test_subshell_cd_does_not_leak(self):
        self.denied(["(cd /tmp); rm CLAUDE.md", "(cd /tmp) && echo x > CLAUDE.md", "(cd /tmp && true); sed -i s/a/b/ REVIEW.md"])
        self.allowed(["(cd /tmp && echo x > y)", "(cd agents && ls); echo hi"])
        self.denied(["cd agents; rm roles.yaml"])

    def test_substitutions_inside_parameter_expansion_and_case_patterns(self):
        self.denied(["echo ${X:-$(git push --force)}", "echo $(case x in x) git push --force;; esac)"])
        self.allowed(["echo ${X:-fallback}", "echo $(echo hi)"])


class RoundThree(Base):
    """R11-01 (major false positive), R11-02 (branches without a killing test), R11-03, R11-08(3)."""

    def test_case_word_in_message_text_is_not_a_case_statement(self):
        self.allowed([
            "git commit -m \"$(cat <<'EOF'\nfix: handle the edge case in the parser\nEOF\n)\"",
            "git commit -m \"$(cat <<'EOF'\ntest: add a case for push in guard\nEOF\n)\"",
            "git commit -m \"$(echo 'a case in point')\"",
            "echo $(echo edge case in parser)", "git log --grep=$(echo edge case in parser)",
            "gh pr create --title x --body \"$(cat <<'EOF'\nCovers the case in .github/workflows\nEOF\n)\"",
        ])
        self.denied(["echo $(case x in x) git push --force;; esac)", "echo $(true; case x in x) git push --force;; esac)"])
        # R12-01: '!' and 'time' (with -p) also put the next word in command position
        self.denied(["echo $(! case x in x) git push origin main;; esac)", "echo \"$(! case x in x) git push --force;; esac)\"",
                     "echo $(time case x in x) git reset --hard;; esac)", "echo $(time -p case x in x) git push --force;; esac)",
                     "echo $(! ! case x in x) git push --force;; esac)"])
        self.allowed(["git log --grep=$(echo time case in point)", "git commit -m \"$(echo ! a case in point)\""])

    def test_alias_chain_depth_and_unknown_expansion_to_git_config(self):
        d = repo()
        for k, v in (("alias.a1", "a2"), ("alias.a2", "a3"), ("alias.a3", "a4"), ("alias.a4", "status")):
            subprocess.run(["git", "config", k, v], cwd=d, check=True)
        self.assertEqual(run("Bash", {"command": "git a1"}, d), 2)  # four deep is too deep to check
        subprocess.run(["git", "config", "alias.a3", "status"], cwd=d, check=True)
        self.assertEqual(run("Bash", {"command": "git a1"}, d), 0)
        self.denied(["echo x > $H/.gitconfig", "echo x > ${H}/.config/git/config"])

    def test_cd_to_the_repo_root_and_config_reads(self):
        self.allowed(["cd \"$(git rev-parse --show-toplevel)\" && echo x > notes.txt", "git config alias.st", "git config user.name"])
        self.denied(["git config alias.st status", "git config --add alias.st status"])

    def test_mirror_config_and_glob_refspecs_that_shorten(self):
        self.denied(["git -c remote.origin.mirror=true push origin", "git config remote.origin.mirror true",
                     "GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=remote.origin.mirror git push origin",
                     "git push origin 'refs/h*:refs/h*'", "git push origin 'r*:r*'", "git push origin 'refs/heads/mast*:refs/heads/mast*'"])
        self.allowed(["git push origin 'refs/heads/work*:refs/heads/work*'", "git config --get remote.origin.mirror"])

    def test_branch_variable_from_show_current_is_resolved(self):
        self.allowed(["BR=$(git branch --show-current); git push -u origin \"$BR\""])
        d = repo("main")
        self.assertEqual(run("Bash", {"command": "BR=$(git branch --show-current); git push -u origin \"$BR\""}, d), 2)


class Wrappers(Base):
    """R10-07."""

    def test_time_and_tracing_wrappers(self):
        self.denied(["time -p git push --force", "/usr/bin/time git push origin main", "/usr/bin/time -f %e git push --force",
                     "strace -f git push origin main", "strace -o /tmp/t -e trace=network git push --force", "ltrace git push --force",
                     "chrt 10 git push --force", "taskset -c 0 git push --force", "taskset 1 git push origin main",
                     "caffeinate git push --force", "script -qc 'git push --force' /dev/null", "time git push origin main"])
        self.allowed(["time -p git status", "/usr/bin/time git log", "strace -f ls", "chrt 10 ls", "script -qc 'echo hi' /dev/null"])


class CheckoutPathspecFile(Base):
    """R10-08."""

    def test_pathspec_from_file_is_destructive(self):
        self.allowed(["git checkout --pathspec-from-file=/tmp/list"])
        self.dirty(True)
        self.denied(["git checkout --pathspec-from-file=/tmp/list", "git checkout HEAD --pathspec-from-file=/tmp/list",
                     "git checkout --pathspec-f=/tmp/list"])
        self.allowed(["git checkout -b new-branch"])


class FalsePositives(Base):
    """R10-09."""

    def test_read_only_interpreter_one_liners_on_process_files(self):
        self.allowed([
            "python3 -c \"print(open('agents/roles.yaml').read())\"",
            "python3 -c \"import yaml; print(yaml.safe_load(open('agents/roles.yaml')))\"",
            "python3 -c \"import sys; sys.stdout.write(open('CLAUDE.md').read())\"",
            "node -e \"process.stdout.write(require('fs').readFileSync('CLAUDE.md','utf8'))\"",
            "git commit -m \"$(cat <<\\EOF\nfix: don't push\nEOF\n)\"",
            "git commit -m \"$(cat <<-'EOF'\n\tfix: x\n\tEOF\n)\"",
        ])
        self.denied(["python3 -c \"open('agents/roles.yaml', 'w')\"", "python3 -c \"open('agents/x', mode='a')\"",
                     "python3 -c \"open('CLAUDE.md','r+')\"", "python3 -c \"from pathlib import Path; Path('CLAUDE.md').write_text('x')\""])


if __name__ == "__main__":
    unittest.main()
