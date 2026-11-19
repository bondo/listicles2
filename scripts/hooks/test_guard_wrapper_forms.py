"""R3 of #237: forms where the guard read a wrapper call differently from bash or from Claude Code's documented matcher. Every form is denied for
both wrappers (mark-ready.sh and update-branch.sh), also in tooling sessions, while the exact calls stay allowed.
Run: python3 -I -m unittest discover -s scripts/hooks"""

import os
import shutil
import subprocess
import unittest

import gitenv  # noqa: F401  # justified: imported for its side effect, drops GIT_DIR and friends (see gitenv.py)
import pretooluse_guard
from test_pretooluse_guard import repo, run

TOOLING = {"LISTICLES_TASK": "tooling"}
ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
SHA = "0123456789abcdef0123456789abcdef01234567"
WRAPPERS = (("update-branch.sh", f"12 {SHA}"), ("mark-ready.sh", "12"))
ESC = "\\"


def forms(name, args):
    call = f"scripts/{name} {args}"
    out = [f"noglob {call}", f"stdbuf --output L {call}", f"stdbuf --input L {call}", f"stdbuf --error 0 {call}"]  # R3-01
    out += [f"{pre} {call}" for pre in ("timeout 5", "time", "nice", "nohup", "stdbuf -oL", "command", "builtin", "xargs")]  # the documented strip list
    out += [f'scripts/$""{name} {args}', f'scripts/$"{name}" {args}', f'scripts/{name[:3]}$""{name[3:]} {args}',  # R3-02: $"..." is a plain string
            f'scripts/$""{name}""{ESC}\n{args}', f'scripts/$"{name}"{ESC}\n{args}']
    out += [f"scrip\"\"ts/{name}\"\"{ESC}\n{args} $'{ESC}E'", f"scripts{ESC}/{name}''{ESC}\n{args} $'{ESC}v'", f"scrip\"\"ts/{name} {args} $'{ESC}E'"]  # R3-03
    out += [f"FOO+=1 {call}", f"FOO[0]=1 {call}", f"NODE_ENV+=test {call}", f"LD_PRELOAD+=/x.so {call}"]  # R3-04
    return out


class WrapperForms(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = repo()
        os.makedirs(os.path.join(cls.d, "scripts"))
        for name, _ in WRAPPERS:
            shutil.copy(os.path.join(ROOT, "scripts", name), os.path.join(cls.d, "scripts", name))

    def bash(self, c, env=None):
        return run("Bash", {"command": c}, self.d, env)

    def test_the_exact_calls_stay_allowed(self):
        for name, args in WRAPPERS:
            self.assertEqual(self.bash(f"scripts/{name} {args}"), 0, name)

    def test_every_form_is_denied_for_both_wrappers_also_in_tooling_sessions(self):
        for name, args in WRAPPERS:
            for c in forms(name, args):
                with self.subTest(c=c):
                    self.assertEqual(self.bash(c), 2)
                    self.assertEqual(self.bash(c, TOOLING), 2, "tooling")

    def test_a_name_plus_equals_or_indexed_assignment_prefix_cannot_hide_any_command(self):  # R3-04, guard-wide
        for c in ("FOO+=1 git push --force origin work", "FOO+=1 git push origin main", "FOO[0]=1 git commit --no-verify -m x", "FOO+=1 rm CLAUDE.md",
                  "FOO+=1 cp /tmp/x .claude/settings.json", "GIT_CONFIG_GLOBAL+=/x git status", "GIT_CONFIG_GLOBAL[0]=/x git status"):
            self.assertEqual(self.bash(c), 2, c)
        for c in ("FOO+=1 ls", "FOO[0]=1 true", "FOO=1 ls"):
            self.assertEqual(self.bash(c), 0, c)

    def test_a_plain_name_plus_equals_or_indexed_statement_keeps_the_tracked_value(self):  # R4-01: behave as main does
        dirty = repo()
        with open(os.path.join(dirty, "f"), "w") as fh:
            fh.write("a")
        subprocess.run(["git", "add", "f"], cwd=dirty, check=True, capture_output=True)
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "f"], cwd=dirty, check=True, capture_output=True)
        with open(os.path.join(dirty, "f"), "w") as fh:
            fh.write("b")
        cases = (
            (self.d, "FOO=--force; FOO+=; git push $FOO origin work"), (self.d, "FOO=--force; FOO+=''; git push $FOO origin work"),
            (self.d, "FOO=--force; FOO[1]=x; git push $FOO origin work"), (self.d, "X=--no-veri; X+=fy; git commit $X -m x"),
            (self.d, "B=--mirr; B+=or; git push $B origin"), (dirty, "OPTS=--hard; OPTS+=' HEAD'; git reset $OPTS"),
            (dirty, "OPTS=--hard; OPTS[1]=HEAD; git reset $OPTS"),
        )
        for d, c in cases:
            for env in (None, TOOLING):
                with self.subTest(c=c, env=env):
                    self.assertEqual(run("Bash", {"command": c}, d, env), 2)
        self.assertEqual(self.bash("FOO=ok; FOO+=1; git push $FOO origin work"), 0)  # a harmless value stays allowed

    def test_the_lexer_failure_fallback_sees_a_wrapper_name_hidden_by_quotes_or_written_without_scripts_slash(self):  # R4-02
        for name, args in WRAPPERS:
            hidden = (f"scrip\"\"ts/{name[:3]}\"\"{name[3:]} {args} 'x", f"cd scripts && ./{name} {args} 'x")
            for c in hidden:
                with self.subTest(c=c):
                    with self.assertRaises(ValueError, msg="the test must reach the fallback"):
                        pretooluse_guard.lex(c)
                    self.assertEqual(self.bash(c), 2)
                    self.assertEqual(self.bash(c, TOOLING), 2, "tooling")
        with self.assertRaises(ValueError):
            pretooluse_guard.lex("echo 'unterminated")
        self.assertEqual(self.bash("echo 'unterminated"), 0)

    def test_ansi_c_follows_bash_for_every_escape(self):  # R3-03: the lexer must fail only where bash fails
        for src, want in ((r"\E", "\x1b"), (r"\v", "\v"), (r"\f", "\f"), (r"\?", "?"), (r"\cA", "\x01"), (r"\8", "\\8"), (r"\q", "\\q"), (r"\n", "\n")):
            self.assertEqual(pretooluse_guard.ansi_c(src), want, src)


if __name__ == "__main__":
    unittest.main()
