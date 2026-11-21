"""Round 4 and the escalation of #252: main's verdict is a floor (R4-16, R4-09, R4-10, R4-11 b, R3-02), R4-07 (a protected name split by an
unparseable expansion), R4-11 a (IFS fields as bash makes them), R4-12 (a case on the line), R4-13 (a nameref without a target), R4-14 (IFS set by
let, ((...)), ${IFS:=}, a name from a variable, a for loop after a reserved word), R4-15 (unset IFS). Run: python3 -I -m unittest discover -s scripts/hooks"""

import unittest

import gitenv  # noqa: F401  # justified: imported for its side effect, drops GIT_DIR and friends (see gitenv.py)
import pretooluse_guard
from test_guard_round1 import PUSH, Base

P = "'core.hooksPath'='/x'"


class Round4(Base):
    def deny_git(self, cmds):
        """A .git form, judged as in a real session (CLAUDE_PROJECT_DIR set), in default and tooling sessions."""
        for c in cmds:
            for env in ({"CLAUDE_PROJECT_DIR": self.d}, {"CLAUDE_PROJECT_DIR": self.d, "LISTICLES_TASK": "tooling"}):
                with self.subTest(c=c, env=env):
                    self.assertEqual(self.bash(c, env), 2)

    def test_r4_16_an_ifs_that_bash_never_applies_does_not_split_a_flag_away(self):
        self.deny(
            [
                "false && IFS=-; P=--force; git push $P origin work",
                "IFS=' '; false && IFS=-; P=--force; git push $P origin work",
                "if false; then IFS=-; fi; P=--force; git push $P origin work",
                "f() { IFS=-; }; P=--force; git push $P origin work",
                "IFS=- | true; P=--force; git push $P origin work",
                "IFS=-; let IFS=0; P=--force; git push $P origin work",
                "IFS=-; N=IFS; unset $N; P=--force; git push $P origin work",
                "IFS=-; if :; then for IFS in ' '; do :; done; fi; P=--force; git push $P origin work",
                "false && IFS=-; P=--no-verify; git commit $P -m x",
                "false && IFS=-; X=--force; git push origin work $X",
                "IFS=-; ((IFS=0)); P=--force; git push $P origin work",
                "IFS=-; P=--force; git push $P origin work",  # bash splits it away here, and main denies it: the floor keeps main's verdict
            ]
        )
        self.deny_git(["false && IFS=.; D=.git/hooks/pre-commit; touch $D"])

    def test_r4_09_export_or_declare_in_a_branch_a_function_or_a_pipeline_keeps_the_old_value(self):
        self.deny(
            [
                "F=--force; false && export F=ok; git push $F origin work",
                "F=--force; if false; then export F=ok; fi; git push $F origin work",
                "F=--force; f() { local F=ok; }; git push $F origin work",
                "F=--force; f() { export F=ok; }; git push $F origin work",
                "F=--force; f() { declare F=ok; }; f; git push $F origin work",
                "F=--force; declare F=ok | cat; git push $F origin work",
                "F=--force; { export F=ok; } | cat; git push $F origin work",
                "F=--force; local F=ok; git push $F origin work",
            ]
        )

    def test_r4_10_an_assignment_name_built_from_an_expansion_is_denied(self):
        self.deny(
            [
                f'env GIT_CONFIG_PARAMETERS$X="{P}" git commit -m x',
                f'env GIT_CONFIG_PARAMETERS${{X}}="{P}" git commit -m x',
                f'sudo GIT_CONFIG_PARAMETERS$X="{P}" git commit -m x',
                "env GIT_CONFIG_GLOBAL$X=/tmp/c git commit -m x",
                f'export GIT_CONFIG_PARAMETERS$X="{P}"; git commit -m x',
                f'declare -x GIT_CONFIG_PARAMETERS${{X}}="{P}"; git commit -m x',
                f'T=$(echo GIT_CONFIG_PARAMETERS); export $T="{P}"; git commit -m x',
            ]
        )
        self.allow(["env FOO=$X git status", "export PATH=$PATH:/x; git status"])

    def test_r3_02_a_case_pattern_after_a_reserved_word_does_not_undo_the_subshell(self):
        push = PUSH.replace("--force", "$F")
        self.deny(
            [
                f"F=--force-with-lease; (F=--force; if :; then case x in x) esac; fi; {push})",
                f"F=--force-with-lease; (F=--force; {{ case x in x) esac; }}; {push})",
                f"F=--force-with-lease; (F=--force; for i in 1; do case x in x) esac; done; {push})",
                f"(F=--force; if :; then case x in x) esac; fi; {push})",
                "(IFS=_; { case x in x) esac; }; P=--force_origin_work; git push $P)",
                "(IFS=_; case x in x) esac; P=--force_origin_work; git push $P)",
            ]
        )
        self.deny_git(["(cd .git; case x in x) esac; echo x >> config)", "(cd .git; case x in x) esac; touch hooks/pre-commit)"])
        self.deny(["(cd docs; case x in x) esac; rm ../CLAUDE.md)"], both=False)
        self.allow(["(F=ok; case x in x) esac); git status", "case x in a) (cd docs);; esac; git status"])

    def test_r4_12_a_case_anywhere_on_the_line_does_not_leak_a_subshell_variable(self):
        self.deny(
            [
                "F=--force; (F=ok); case x in x) esac; git push $F origin work",
                "case x in x) esac; F=--force; (F=ok); git push $F origin work",
                "F=--force; (F=ok) && case $F in *) esac; git push $F origin work",
                "F=--no-verify; (F=-m.x); case x in x) esac; git commit $F -m x",
                "IFS=_; (IFS=' '); case x in x) esac; P=--force_origin_work; git push $P",
            ]
        )

    def test_r4_07_a_protected_name_split_by_an_expansion_the_guard_cannot_strip(self):
        self.deny(["rm CLAU${x#{}DE.md", "rm CLAU$(: '(')DE.md", "rm scripts/${x#{}guards.sh", "rm notes${x#{}.md"], both=False)
        self.deny_git(["echo x >> .git/${x#{}config", "touch .git/hoo${x#{}ks/pre-commit", "echo x >> .git/$(: '(')config"])
        self.allow(["rm notes.md"])

    def test_r4_11_an_empty_field_at_a_leading_ifs_character_joins_the_text_before_it(self):
        self.deny(["IFS=,; A=,core.hooksPath=/x; git -c$A commit -m x", "IFS=,; A=,alias.st=push; git -c$A st --force origin work",
                   'E=; M="a -- b"; git commit -m "$M"$E$(git branch --show-current) --no-verify'])
        self.allow(["IFS=,; A=,b; echo x$A"])

    def test_r4_11_the_splitter_gives_the_fields_bash_gives(self):
        # bash 5.2: IFS=<ifs>; A=<value>; printf '[%s]' <word>
        table = [
            (",", ",y", "x$A", ["x", "y"]),
            (",", ",,y", "x$A", ["x", "", "y"]),
            (",", ",y", "$A", ["", "y"]),
            (",", ",", 'x$A"z"', ["x", "z"]),
            (",", "y,", '$A"z"', ["y", "z"]),
            (",", "y,,", '$A"z"', ["y", "", "z"]),
            (" ,", " ,y", "x$A", ["x", "y"]),
            (" ,", "y, ", '$A"z"', ["y", "z"]),
            (None, " y", "x$A", ["x", "y"]),
        ]
        for ifs, val, word, want in table:
            w = pretooluse_guard.lex("echo " + word)[0].words[1]
            with self.subTest(ifs=ifs, val=val, word=word):
                self.assertEqual(pretooluse_guard.expand_fields(w, {"cwd": self.d, "vars": {"A": val}, "ifs": ifs}), want)

    def test_r4_13_a_nameref_without_a_literal_target_is_denied(self):
        self.deny([f'declare -n R; R=GIT_CONFIG_PARAMETERS; export R="{P}"; git commit -m x', "declare -n R; R=IFS; R=_; P=--force_origin_work; git push $P",
                   f'declare -n R=$X; export R="{P}"; git commit -m x'])
        self.allow(["declare -n r=x; git status"])

    def test_r4_14_ifs_set_by_let_arithmetic_a_default_expansion_a_name_variable_or_a_late_for_loop(self):
        self.deny(
            [
                "IFS=; : ${IFS:=_}; P=--force_origin_work; git push $P",
                "IFS=; : ${IFS=_}; P=--force_origin_work; git push $P",
                "((IFS=1)); P=--force1origin1work; git push $P",
                ": $((IFS=1)); P=--force1origin1work; git push $P",
                "let IFS=1; P=--force1origin1work; git push $P",
                "N=IFS; read -r $N <<< _; P=--force_origin_work; git push $P",
                "if :; then for IFS in _; do P=--force_origin_work; git push $P; done; fi",
                "{ for IFS in _; do P=--force_origin_work; git push $P; done; }",
            ]
        )

    def test_r4_15_unset_ifs_export_ifs_and_a_message_that_names_ifs_are_allowed(self):
        self.allow(["unset IFS; git status", "IFS=,; set -- a,b; unset IFS; git status", "unset IFS; git commit -m x", "export IFS; git status",
                    "printf 'the IFS\\n'; git status", "unset IFS; D=docs; ls $D", "OLDIFS=$IFS; IFS=,; IFS=$OLDIFS; git status", "unset -v IFS; git status",
                    "readonly IFS; git status"])
        self.deny(["IFS=_; unset IFS; P='--force origin'; git push $P work"])  # unset gives the default IFS, which splits on blanks
        self.deny(["IFS=_; unset -f IFS; P=--force_origin_work; git push $P", "IFS=_; declare IFS; P=--force_origin_work; git push $P"])

    def test_r4_08_witnesses_of_the_twenty_three_mutants(self):
        # each line kills one or more of round 4's 23 mutants (now judged with the floor): main's verdict alone allows the IFS forms
        quoted = ("\\$D", "'$D'", '"\\$D"', '"$(echo $D)"', '"`echo $D`"', "$'$D'")  # bash: [commit][-m][x][$D][--no-verify]
        self.deny([f"IFS=_; D=_--_; P=_--no-verify; git commit -m x {q}$P" for q in quoted])
        self.deny(
            [
                "Q=; P=\" --no-verify\"; git commit -m 'x'$P\"$Q\"",
                "X=x; P='--force work'; git push origin \"$X\" $P",
                'env -S"`echo git push` --force origin work"',
                "watch echo `printf '%s' 'x; git push --force origin work'`",
                "X='true; git push --force origin work'; watch $X",
                "P=$'--force\\torigin'; git push $P work",
                "P=$'--force\\norigin'; git push $P work",
                "P=$'\\t\\tcore.hooksPath=/x'; git -c$P commit -m x",
                "read -r IFS <<< _; false && IFS=' '; P=--force_origin_work; git push $P",
                "typeset -n R=IFS; R=_; P=--force_origin_work; git push $P",
                "f() { local -n R=IFS; R=_; P=--force_origin_work; git push $P; }; f",
                "X=echo; read X <<< git; $X -C . push --force origin work",
                "X=echo; read X <<< git; $X --no-pager push --force origin work",
                f'declare -gn R=GIT_CONFIG_PARAMETERS; export R="{P}"; git commit -m x',
                f'typeset -n R=GIT_CONFIG_PARAMETERS; export R="{P}"; git commit -m x',
                "`echo git` push --force origin work",
                "`printf git` commit --no-verify -m x",
            ]
        )
        self.deny(["rm `echo \\`echo\\``CLAUDE.md"], both=False)

    def test_main_s_command_name_check_also_runs_in_the_model_pass(self):
        # an assignment only the model reads as one (NAME+=v, A.B=v after env) leaves a substituted command name for the model to judge (5e56935 denied these)
        self.deny(["A+=x `echo git` push --force origin work", "env A.B=1 `echo git` push --force origin work", "env A.B=1 $X push --force origin work"])
        self.deny(["FOO+=/usr/bin/git push --force origin work"])  # main reads FOO+=... as the program, so the floor denies it

    def test_a_subshell_that_leaves_ifs_as_it_was_does_not_make_it_unknown(self):
        self.allow(["case x in a) ;; esac; (unset IFS); git status", "((i = 1)); (unset IFS); git status"])

    def test_export_readonly_and_mapfile_never_change_how_bash_splits(self):
        self.allow(["export $N; git status", "readonly $N; git status", "mapfile -t $N < f; git status", "readarray -t IFS < f; git status"])

    def test_witnesses_of_this_round_s_mutants(self):
        # one-line mutants of the lines this round added; each command below flips under one of them (deny tests in both sessions)
        names = ("p", "_p", "p1", "p_q", "Pq")  # main's assignment rule in the floor pass: every character class of the name
        self.deny([f"false && IFS=-; {v}=--force; git push ${v} origin work" for v in names])
        self.deny(
            [
                ": $((IFS=1)); false && IFS=' '; P=--force1origin1work; git push $P",
                f'declare -ng R=GIT_CONFIG_PARAMETERS; export R="{P}"; git commit -m x',
                "printf -vIFS %s _; P=--force_origin_work; git push $P",
                "IFS=_; f() { declare IFS; P='--force origin'; git push $P work; }; f",
                "read -r `echo IFS` <<< _; P=--force_origin_work; git push $P",
                "OLDIFS=$IFS; IFS=,; IFS=$OLDIFS; P=$'--force\\torigin'; git push $P work",
                "IFS=,; OLDIFS=$IFS; IFS=' '; IFS=$OLDIFS; P=--force,origin,work; git push $P",
                "read -r IFS <<< _; false && unset IFS; P=--force_origin_work; git push $P",
                f'export `echo GIT_CONFIG_PARAMETERS`="{P}"; git commit -m x',
                "F=ok; env F=--force; git push $F origin work",  # main records an env assignment, so the floor denies; bash leaves F=ok
                "OLDIFS=$IFS; git push origin $OLDIFS",  # main's refspec check: the floor never reads $IFS
            ]
        )
        self.deny_git(["touch .git/$y${x#{}config"])
        self.deny(["rm notes$(: '(').md"], both=False)
        self.deny_git(["echo case; (cd .git); touch hooks/pre-commit"])  # deny-only: a line that names case is read as one with a case statement
        self.allow(
            [
                "(IFS=,); git status",
                "case x in a) ;; esac; (true); touch notes.md",
                "(cd docs); touch notes.md",
                "(: $((IFS=1))); git status",
                "X=$(echo IFS); git status",
                ": $((1 + 1)); git status",
                "read -$O line <<< y; git status",
                "OLDIFS=${IFS}; IFS=,; IFS=$OLDIFS; git status",
                "IFS=' '; read -r IFS <<< x; O=$IFS; echo $O",
                "(read -r IFS <<< x); git status",
                "$X a b c push --force",
                "declare X=$Y; git status",  # a NAME=v argument is no name for sets_ifs, and its value no nameref target
                "declare X=IFS; git status",
            ]
        )

    def test_the_floor_keeps_main_s_denials_that_the_model_alone_would_allow(self):
        # main denies these; bash would not run them as the guard fears, but main's verdict is the floor (escalation of #252)
        self.deny([f"nice FOO=1 {PUSH}", "F=--force-with-lease; (F=--force); git push $F origin work"])
        self.deny(['P="-m "; git commit $P -n', 'E=""; git commit -m $E -n'])


if __name__ == "__main__":
    unittest.main()
