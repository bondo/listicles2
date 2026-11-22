"""Round 2 of #252: R2-12 (six untested lines), R2-01 (restore -S$X), R2-02 (split only expanded text), R2-03 (watch), R2-04 (closing quote ends $NAME),
R2-05 (nested expansions in a path), R2-06 (env -S word order, -x=1), R2-07 (IFS), R2-08 (quoted command name), R2-09 (variables that stay out of the
shell), R2-10 (option tables), R2-13 (printf -v, read). Run: python3 -I -m unittest discover -s scripts/hooks"""

import unittest

import gitenv  # noqa: F401  # justified: imported for its side effect, drops GIT_DIR and friends (see gitenv.py)
from pretooluse_guard import Cmd, check_simple
from test_guard_round1 import PUSH, Base

Q = "`"


class Round2(Base):
    def test_r2_12_the_six_lines_the_reviewer_mutated(self):
        self.deny([f"rm {Q}echo{Q}CLAUDE.md", "rm $x.claude/settings.json", "X=Q; IFS=$X; D=CLAUDE.mdQ; rm $D"], both=False)
        self.deny([f"time FOO=1 {PUSH}", "IFS=; A='x -- y'; git commit -m $A --no-verify"])
        self.allow(["X=Q; IFS=$X; D=aQb; echo $D", "IFS=; A='x y'; git commit -m $A"])

    def test_r2_01_a_flag_with_an_expansion_never_makes_a_command_safe(self):
        self.deny(["X=$(printf W); git restore -S$X f.txt", "X=$(printf ' -W'); git restore --staged$X f.txt", "git restore -S$X f.txt"], d=self.dirty)
        self.deny(["git checkout -b$X -- f.txt"], d=self.dirty)
        self.deny(["git config --get$X alias.p '!sh'", "git config -l$X alias.p '!sh'"], both=False)
        self.allow(["git restore -S f.txt", "git restore --staged f.txt"], d=self.dirty)

    def test_r2_02_only_the_text_an_unquoted_expansion_produced_is_split(self):
        self.deny(['A=y; git commit -m "x -- "$A --no-verify', "A=y; git commit -m x\\ --\\ $A --no-verify", 'A=y; git push -o "x -- "$A --force origin work'])
        self.allow(['A=y; git commit -m "x -- "$A', "A=y; git commit -m x\\ --\\ $A"])

    def test_r2_03_watch_runs_its_words_with_sh_c_unless_x(self):
        self.deny([f"watch FOO=1 {PUSH}", f"watch -d {PUSH}", f"watch -q 3 {PUSH}", f"watch --interval 1 {PUSH}", f"watch '{PUSH}'",
                   'watch git commit -m "x; git push --force origin work"'])
        self.allow(["watch -n 5 git status", "watch -x FOO=1 git status", "watch -d git status"])

    def test_r2_04_a_closing_double_quote_ends_the_variable_name(self):
        self.deny(['A=--for; git push "$A"ce origin work', 'A=--no-ver; git commit "$A"ify -m x'])
        self.deny(['rm "$x"CLAUDE.md', 'rm -rf "$x"agents', 'rm "$x"scripts/guards.sh'], both=False)
        self.allow(['A=x; echo "$A"y', 'rm "$x"notes.md'])

    def test_r2_05_nested_expansions_in_a_protected_path(self):
        self.deny(["rm $(echo $(echo))CLAUDE.md", "rm $( (true) )CLAUDE.md", "rm ${x:-${y}}CLAUDE.md"], both=False)
        self.allow(["rm $(echo $(echo))notes.md", "rm ${x:-${y}}notes.md"])

    def test_r2_06_env_split_string_and_assignments_after_dashes(self):
        self.deny([f"env -S {PUSH}", "env -S'git push' --force origin work", "env --split-string='git push' --force origin work",
                   f"env -S '-i {PUSH}'", "env -S'git\\_push\\_--force\\_origin\\_work'", f"env -- -x=1 {PUSH}", f"env A=1 -x=1 {PUSH}"])
        self.deny(["env -S'git status\\cgit push --force'", "env -S \"git 'push\""])  # an escape or quote the guard does not model
        self.allow(["env -S'git status'", "env -S git status", "env -- -x=1 git status"])

    def test_r2_07_ifs_through_export_append_and_nested_shells(self):
        self.deny(["export IFS=_; P=--force_origin_work; git push $P", "declare IFS=_; P=--force_origin_work; git push $P",
                   "IFS=_; IFS+=,; P=--force,origin_work; git push $P", "IFS=; bash -c 'P=\"--force origin\"; git push $P work'",
                   "IFS=+; P=--force+origin; git push $P work",
                   "IFS+=_; P='--force origin'; git push $P work", "IFS=$(printf _); IFS+=,; git status"])
        self.deny(["IFS=$(printf '\\121'); D=CLAUDE.mdQ; rm $D"], both=False)
        self.allow(["IFS+=_; P=a; git status $P", "IFS=; bash -c 'echo $HOME'"])

    def test_r2_08_a_quoted_command_name_variable_is_expanded(self):
        self.deny(['X=git; "$X" --no-pager -C . push --force origin work', 'X=git; "${X}" -C . -C . push --force origin work'])
        self.deny(['X=rm; "$X" CLAUDE.md'], both=False)
        self.allow(['"$HOME/bin/tool" --version', 'X=ls; "$X" -la', f"X='{PUSH.split(' origin')[0]}'; \"$X\" origin work"])

    def test_r2_09_a_variable_the_shell_never_sets_is_not_tracked(self):
        self.deny(["F=--force; env F=ok; git push $F origin work", "F=--force; (F=ok); git push $F origin work",
                   "(IFS=); P='--force origin'; git push $P work"])
        self.allow(["env A.B=1", "sudo A.B=1"])  # the subshell form main denies stays denied: main's verdict is the floor (test_guard_hardening4)

    def test_the_nesting_cap_denies(self):
        with self.assertRaises(SystemExit):
            check_simple(Cmd(), {"cwd": "/", "known": True, "vars": {}}, 9)

    def test_r2_10_long_value_options_of_ionice_and_sudo(self):
        self.deny([f"ionice --class 3 {PUSH}", f"ionice --classdata 7 {PUSH}", f"sudo --chdir /tmp {PUSH}", f"sudo --prompt x {PUSH}", f"sudo -T 10 {PUSH}"])
        for p in ("ionice -P 1", "ionice -u 1", "ionice --pid 1", "ionice --pgid 1", "ionice --uid 1", "sudo --close-from 3", "sudo --chroot /",
                  "sudo --role r", "sudo --type t", "sudo --other-user u", "sudo --command-timeout 1"):
            self.deny([f"{p} {PUSH}"])
        self.allow(["ionice --class 3 git status", "sudo --chdir /tmp git status"])

    def test_r2_13_a_git_config_variable_set_by_printf_v_or_read(self):
        self.deny(["printf -v GIT_CONFIG_KEY_0 core.hooksPath; export GIT_CONFIG_KEY_0; GIT_CONFIG_COUNT=1 GIT_CONFIG_VALUE_0=/x git commit -m x",
                   "read GIT_CONFIG_KEY_0 <<< core.hooksPath; export GIT_CONFIG_KEY_0; git commit -m x",
                   "read -r GIT_CONFIG_PARAMETERS <<< \"'core.hooksPath'='/x'\"; export GIT_CONFIG_PARAMETERS; git commit -m x", "export GIT_CONFIG_KEY_0",
                   "mapfile GIT_CONFIG_KEY_0 < f"])
        self.allow(["read -r line < f", "export GIT_PAGER", "printf -v x ok", "printf GIT_CONFIG_KEY_0"])


if __name__ == "__main__":
    unittest.main()
