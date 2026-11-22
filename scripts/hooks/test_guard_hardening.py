"""Guard hardening after #237 (R4-03..R4-06, R4-01 exact append and word splitting, R5-01, R5-02, R3-02 and R3-04 guard-wide, see #229).
Each deny form also has an allowed neighbour. Run: python3 -I -m unittest discover -s scripts/hooks"""

import os
import shutil
import unittest

import gitenv  # noqa: F401  # justified: imported for its side effect, drops GIT_DIR and friends (see gitenv.py)
import pretooluse_guard
from test_guard_wrapper_forms import ROOT, WRAPPERS, dirty_repo
from test_pretooluse_guard import repo, run

TOOLING = {"LISTICLES_TASK": "tooling"}
ESC = "\\"
PUSH = "git push --force origin work"


class Hardening(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = repo()
        cls.dirty = dirty_repo()
        os.makedirs(os.path.join(cls.d, "scripts"))
        for name, _ in WRAPPERS:
            shutil.copy(os.path.join(ROOT, "scripts", name), os.path.join(cls.d, "scripts", name))

    def bash(self, c, env=None, d=None):
        return run("Bash", {"command": c}, d or self.d, env)

    def deny(self, cmds, both=True, d=None):
        for c in cmds:
            for env in (None, TOOLING) if both else (None,):
                with self.subTest(c=c, env=env):
                    self.assertEqual(self.bash(c, env, d), 2)

    def allow(self, cmds, d=None):
        for c in cmds:
            with self.subTest(c=c):
                self.assertEqual(self.bash(c, d=d), 0)

    # R4-03
    def test_an_abbreviated_long_option_of_a_wrapper_takes_its_value_like_the_full_name(self):
        prefixes = ("stdbuf --out L", "stdbuf --outp L", "stdbuf --in 0", "stdbuf --e 0", "timeout --sig KILL 5", "timeout --kill 1 5", "nice --adj 5")
        for name, args in WRAPPERS:
            self.deny([f"{p} scripts/{name} {args}" for p in prefixes])
        self.deny([f"env --s '{PUSH}'", f"env --split '{PUSH}'", f"stdbuf --out L {PUSH}", f"timeout --sig KILL 5 {PUSH}",
                   "nice --adj 5 git commit --no-verify -m x", f"xargs --max-args 1 {PUSH}", f"xargs --delimiter x {PUSH}", f"xargs --max-p 2 {PUSH}"])
        self.deny([f"timeout --sig=KILL 5 {PUSH}", f"stdbuf --out=L {PUSH}"])
        self.allow(["stdbuf --out L git status", "timeout --sig KILL 5 git status", "nice --adj 5 git status", "xargs --max-args 1 git status",
                    "timeout --foreground 5 git status", "xargs --no-run-if-empty git status", "timeout --signal KILL 5 git status"])
        for name, args in WRAPPERS:
            self.assertEqual(self.bash(f"scripts/{name} {args}"), 0, name)

    # self-review: env, sudo and the like read any NAME=v argument as an assignment, however the shell quoted it (main denies these)
    def test_a_quoted_assignment_word_after_a_wrapper_is_still_an_assignment(self):
        self.deny([f'env "FOO=1" {PUSH}', f"env 'FOO=1' {PUSH}", f"env FOO{ESC}=1 {PUSH}", 'env -i "FOO=1" git commit --no-verify -m x',
                   f'sudo "FOO=1" {PUSH}', f'nice env "A=1" {PUSH}', f'xargs env "A=1" {PUSH}', f'env FOO=1 "BAR=2" {PUSH}',
                   'env "GIT_CONFIG_GLOBAL=/tmp/x" git commit -m x', f"env $'FOO=1' {PUSH}"])
        self.deny(["$'FOO=/usr/bin/git' push --force origin work", f'FOO=1 env "BAR+=2" {PUSH}'])
        self.allow(['env "FOO=1" git status', "env 'FOO=1 2' git status"])

    # R4-04
    def test_an_indexed_assignment_word_before_a_command_is_denied(self):
        prefixes = ("FOO[a[1]]=1", 'FOO["]"]=1', "FOO[']']=1", f"FOO[{ESC}]]=1", "FOO[ x ]=1", "FOO[a b]=1", "FOO[0]=1")
        self.deny([f"{p} {c}" for p in prefixes for c in (PUSH, "git commit --no-verify -m x", "git push origin main")])
        self.deny([f"{p} {c}" for p in prefixes for c in ("rm CLAUDE.md", "cp /tmp/x .claude/settings.json")], both=False)
        self.allow(["FOO[1]=x", "arr[0]=x; echo ok", 'echo "FOO[1]=x"', "echo FOO[1]", "FOO=1 git status"])

    # R4-05
    def test_ansi_c_gives_bash_text_for_an_out_of_range_code_point(self):
        for src in (r"\U110000", r"\UFFFFFFFF", r"\U00110000x"):
            self.assertEqual(pretooluse_guard.ansi_c(src)[:2], "\\U", src)  # no ValueError
        self.assertEqual(pretooluse_guard.ansi_c(r"\U0041"), "A")

    def test_a_name_spelled_with_escapes_is_denied_when_the_rest_of_the_line_does_not_lex(self):
        for name, args in WRAPPERS:
            spelled = f"scrip$'{ESC}x74's/$'{ESC}x{ord(name[0]):x}'{name[1:]}\"\"{ESC}\n{args}"
            for tail in (f" $'{ESC}U110000'", " $(case a in a) :;; esac)"):
                with self.subTest(name=name, tail=tail):
                    self.deny([spelled + tail])
            self.deny([f"scrip$'{ESC}x74's/$'{ESC}x{ord(name[0]):x}'{name[1:]} {args}; : $(case a in a) :;; esac)"])
            with self.assertRaises(ValueError, msg="the test must reach the fallback"):
                pretooluse_guard.lex(spelled + " $(case a in a) :;; esac)")
        self.deny([f"$'{ESC}x67'it push --force origin work; : $'{ESC}U110000'", "g${x}it push --force origin work; echo $(case a in a) :;; esac)",
                   "echo $(case a in a) :;; esac)"])
        self.allow(["echo 'unterminated", "echo done"])

    # R4-06
    def test_git_config_variables_built_with_plus_equals_are_denied(self):
        self.deny(["GIT_CONFIG_PARAMETERS=\"'core.hooks\" GIT_CONFIG_PARAMETERS+=\"Path'='/nonexistent'\" git commit -m x",
                   "GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=core.hooks GIT_CONFIG_KEY_0+=Path GIT_CONFIG_VALUE_0=/nonexistent git commit -m x",
                   "GIT_CONFIG_GLOBAL+=/x git status", "GIT_CONFIG_COUNT+=1 git status", "export GIT_CONFIG_KEY_0+=Path"])
        self.allow(["GIT_CONFIG_COUNT=0 git status", "FOO+=1 ls", "export FOO+=1"])

    # R3-04 (guard-wide) and R5-02
    def test_a_name_plus_equals_prefix_no_longer_hides_the_command(self):
        self.deny([f"FOO+=1 {c}" for c in (PUSH, "git push origin main", "git commit --no-verify -m x")])
        self.deny(["FOO+=1 rm CLAUDE.md", "FOO+=1 cp /tmp/x .claude/settings.json"], both=False)
        self.deny(["FOO+=1 git reset --hard"], d=self.dirty)
        for name, args in WRAPPERS:
            self.deny([f"{p}+=test scripts/{name} {args}" for p in ("NODE_ENV", "LD_PRELOAD", "FOO[0]")])
        self.allow(["FOO+=1 ls", "FOO+=1 git status", 'echo "FOO+=1"', "FOO='a b' git status", "FOO=$'x' git status", "FOO='' git status"])

    def test_a_quoted_or_escaped_equals_word_is_a_command_not_an_assignment(self):
        git = "/usr/bin/git"
        self.deny([f'"FOO={git}" push --force origin work', f"'FOO={git}' push --force origin work", f"FOO{ESC}={git} push --force origin work",
                   f'FOO""={git} push --force origin work', f'"FOO+={git}" push --force origin work', f'FOO{ESC}+={git} push --force origin work'])
        self.allow(['FOO="x y" git status', "FOO+='x y' git status"])

    # R4-01, exact
    def test_plus_equals_appends_to_the_tracked_value_and_an_unquoted_expansion_splits(self):
        self.deny(["R=ma; R+=in; git push origin $R", "A=-; A+=-force; git push $A origin work", "F=--no-; F+=verify; git commit $F -m x",
                   'P="--force origin"; git push $P work', "P=--force; P+=' origin'; git push $P work", "MSG='x --no-verify'; git commit -m $MSG",
                   "P='--force origin'; git push ${P} work"])
        self.deny(["H=--; H+=hard; git reset $H HEAD", 'O="--hard HEAD"; git reset $O', "OPTS=--hard; OPTS+=' HEAD'; git reset $OPTS"], d=self.dirty)
        self.allow(["FOO=ok; FOO+=1; git push $FOO origin work", "A=--force-; A+=with-lease; git push $A origin work", 'P="--force origin"; git push "$P" work',
                    "MSG='x --no-verify'; git commit -m \"$MSG\"", "FOO+=x; git push $FOO origin work"])
        self.allow(["H=--; H+=soft; git reset $H HEAD"], d=self.dirty)

    # R5-01, R3-02
    def test_a_translated_string_word_is_denied_in_any_command(self):
        self.deny(['git push $"--force" origin work', 'X=$"--no-verify"; git commit $X -m x', 'git $"y" --force origin work',
                   'git -C . $"y" --force origin work', '$"g" push --force origin work', 'git push origin $"z"', 'git push origin HEAD:$"z"',
                   'git push origin $"w"', 'echo $"x"'])
        self.deny(['rm $"CLAUDE.md"', 'touch $"CLAUDE.md"'], both=False)
        self.deny(['touch $".git/hooks/pre-commit"', 'rm $".git/config"'])
        self.deny([f'git {c} $"x"' for c in ("reset", "checkout", "clean", "restore --staged")], d=self.dirty)
        for name, args in WRAPPERS:
            self.deny([f'scripts/$""{name} {args}', f'scripts/$"{name}" {args}', f'$"scripts/{name}" {args}', f'scripts/{name}$"" {args}'])
        self.allow(["echo '$\"x\"'", 'echo "$"', 'git commit -m "price in $"', "echo $x", 'echo "a $x b"'])


if __name__ == "__main__":
    unittest.main()
