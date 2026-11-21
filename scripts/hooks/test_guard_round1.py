"""Round 1 of #252: R1-01 (NAME+= program word after a wrapper), R1-02 (untested lines), R1-03 (computed +=), R1-04 (protected name after an
expansion), R1-05 (env and sudo assignments), R1-06 (option clusters, env -S attached), R1-07 ($ in GIT_CONFIG keys), R1-08 (IFS, a command-name
variable, a quote right after $NAME), R1-11 ($$"x"). Run: python3 -I -m unittest discover -s scripts/hooks"""

import os
import shutil
import unittest

import gitenv  # noqa: F401  # justified: imported for its side effect, drops GIT_DIR and friends (see gitenv.py)
from test_guard_wrapper_forms import ROOT, WRAPPERS, dirty_repo
from test_pretooluse_guard import repo, run

TOOLING = {"LISTICLES_TASK": "tooling"}
ESC = "\\"
PUSH = "git push --force origin work"
GIT = "/usr/bin/git"


class Round1(unittest.TestCase):
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

    def test_r1_01_a_name_plus_equals_word_after_a_wrapper_other_than_env_is_the_program(self):
        self.deny([f"{w} FOO+={GIT} push --force origin work" for w in ("nice", "timeout 5", "command", "exec", "xargs", "nohup", "stdbuf -oL", "setsid")])
        self.deny([f'nice "FOO+={GIT}" push --force origin work', f'time "FOO+={GIT}" push --force origin work',
                   f"nohup FOO+={GIT} commit --no-verify -m x", f"find . -exec FOO+={GIT} push --force origin work {ESC};",
                   'timeout 5 "FOO+=/../../../../../../../../../../usr/bin/git" push origin main'])
        self.allow(["nice env FOO+=1 git status", "FOO+=1 nice git status", "env FOO+=1 git status", "find . -name x -exec echo FOO+=1 {} " + ESC + ";"])

    def test_r1_02_computed_plus_equals_and_the_glob_flag_of_a_split_part_change_a_verdict(self):
        self.deny(["H=--hard; H+=$X; git reset $H"], d=self.dirty)  # was: a computed += forgot the name
        self.deny(["X=--shell; actionlint $X*"])  # a split part keeps the glob flag of its word
        self.allow(["X=a.yml; actionlint $X", "H=--soft; H+=$X; git reset $H HEAD"], d=self.dirty)

    def test_r1_03_a_computed_plus_equals_keeps_the_known_value_and_a_flag_with_a_suffix_counts_by_its_literal_part(self):
        self.deny(["F=--force; F+=$X; git push $F origin work", "F=--force; F+=$(true); git push $F origin work", "F=--no-verify; F+=$X; git commit $F -m x",
                   "F=--for; X=ce; F+=$X; git push $F origin work",
                   "F=--; X=force; F+=$X; git push $F origin work", "D=.git/hooks; D+=/$X; touch $D/pre-commit", "git push --force$Q origin work",
                   "git commit --no-verify$Q -m x"])
        self.deny(["D=.claude; D+=/$X; rm -rf $D"], both=False)
        self.allow(["F=--force-with-lease; F+=$X; git push $F origin work", "git push --force-with-lease$Q origin work", "git commit -m x$Q"])

    def test_r1_04_a_protected_name_right_after_an_expansion_is_still_protected(self):
        self.deny(["rm ${x}CLAUDE.md", "rm $(echo)CLAUDE.md", "rm -rf ${x}.claude", "echo x > ${x}CLAUDE.md", "cp /tmp/x ${x}.claude/settings.json",
                   "sed -i s/a/b/ ${x}scripts/hooks/pretooluse_guard.py", "rm CLAUDE${x}.md"], both=False)
        self.deny(["touch ${x}.git/hooks/pre-commit", "rm -rf ${x}.git/hooks", "echo x > ${x}.git/config"])
        self.allow(["rm ${x}foo.txt", "rm $x/foo", "touch ${x}notes.md"])
        self.assertEqual(self.bash("rm ${x}CLAUDE.md", TOOLING), 0)  # a tooling session may edit process files, as with the plain name

    def test_r1_05_every_word_with_an_equals_sign_after_env_or_sudo_is_an_assignment(self):
        self.deny([f"env A.B=1 {PUSH}", f"env 'A B=1' {PUSH}", f"env 1A=1 {PUSH}", "env =x git commit --no-verify -m x", "env -i A.B=1 git push origin main",
                   f"sudo A.B=1 {PUSH}"])
        self.allow(["env A.B=1 git status", "sudo A.B=1 git status"])

    def test_r1_06_option_clusters_and_attached_split_strings(self):
        git = [f"{p} {PUSH}" for p in ("env -vu FOO", "timeout -vs KILL 5", "exec -ca x", "ionice -tc 3", "sudo -Eu root", "xargs -rn 1")]
        git += ["env -iu FOO git commit --no-verify -m x", f"env -S'{PUSH}'", f"env --split-string='{PUSH}'", f"env -vS '{PUSH}'", f"env --sp='{PUSH}'"]
        self.deny(git)
        for name, args in WRAPPERS:
            self.deny([f"timeout -vs KILL 5 scripts/{name} {args}", f"exec -ca x scripts/{name} {args}"])
            self.assertEqual(self.bash(f"scripts/{name} {args}"), 0)
        self.allow(["timeout -v 5 git status", "env -iu FOO git status", "xargs -rn 1 git status", "env -S'git status'"])

    def test_r1_07_an_expansion_in_a_git_config_key_hides_core_hookspath(self):
        self.deny(["GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=core.hooks${x}Path GIT_CONFIG_VALUE_0=/nonexistent git commit -m x",
                   "git -c core.hooks${x}Path=/nonexistent commit -m x", 'git -c "$(printf core.hooksPath)=/nonexistent" commit -m x',
                   "X=core.hooksPath; GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=$X GIT_CONFIG_VALUE_0=/nonexistent git commit -m x",
                   "GIT_CONFIG_PARAMETERS=\"'core.hooks${x}Path'='/x'\" git commit -m x"])
        self.allow(['git -c user.name="$N" commit -m x', "git -c user.name=$N commit -m x",
                    "GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=user.name GIT_CONFIG_VALUE_0=$N git status"])

    def test_r1_08_ifs_a_command_name_variable_and_a_quote_right_after_a_name(self):
        self.deny(["IFS=_; P=--force_origin_work; git push $P", "IFS=,; P=--force,origin; git push $P work", 'X="git push"; $X --force origin work',
                   'X="git commit --no-verify"; $X -m x', 'A=--for; git push $A"ce" origin work', "A=--for; git push $A'ce' origin work",
                   f"A=--for; git push $A{ESC}ce origin work", "IFS=$X; git status",
                   f"X='FOO+={GIT}'; $X push --force origin work"])
        self.allow(["while IFS= read -r l; do echo $l; done < f", "X=ls; $X -la", "IFS=,; echo a", "IFS=_; P=a_b; git status $P", 'A=x; echo $A"y"'])

    def test_r1_11_a_double_dollar_before_a_quote_is_the_pid_not_a_translated_string(self):
        self.allow(['echo $$"x"'])
        self.deny(['echo $"x"', 'echo $$$"x"', "echo '$'$\"x\""])


if __name__ == "__main__":
    unittest.main()
