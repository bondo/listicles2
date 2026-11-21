"""Round 3 of #252: R3-12 (13 mutants of new lines), R3-01 (a cd applied twice), R3-02 (case pattern in a subshell), R3-03 (watch --, -dx, expansions),
R3-09 (stale command-name value), R3-11 (empty IFS fields), R3-06 (IFS set by other statements), R3-04 (env -S), R3-05 (protected name after quoted or
special expansions), R3-07 (mixed quoted and expanded word), R3-08 (printf -vNAME, nameref). Run: python3 -I -m unittest discover -s scripts/hooks"""

import unittest

import gitenv  # noqa: F401  # justified: imported for its side effect, drops GIT_DIR and friends (see gitenv.py)
from test_guard_round1 import PUSH, Base

P = "'core.hooksPath'='/x'"


class Round3(Base):
    def test_r3_12_the_thirteen_mutants_of_round_2_lines(self):
        self.deny(
            [
                f"watch --equexit 3 {PUSH}",
                "set -a; read GIT_CONFIG_GLOBAL <<< /tmp/c; git commit -m x",
                "set -a; read GIT_CONFIG_SYSTEM <<< /tmp/c; git commit -m x",
                "set -a; read GIT_CONFIG_KEY_1 <<< core.hooksPath; git commit -m x",
                f'set -a; read -r GIT_CONFIG_PARAMETERS <<< "{P}"; git commit -m x',
                f'set -a; printf -v GIT_CONFIG_PARAMETERS %s "{P}"; git commit -m x',
                'A1=--for; git push "$A1"ce origin work',
                "IFS=$(printf '\\137'); (:); P=--force_origin_work; git push $P",
                "IFS=$(printf '\\137'); (IFS=_); P=--force_origin_work; git push $P",
                "IFS=_; (:); P=--force_origin_work; git push $P",
                "IFS=`printf _`; P=--force_origin_work; git push $P",
                "F=--force-with-lease; time F=--force; git push $F origin work",
            ]
        )
        self.deny(["rm ${x#{}CLAUDE.md"], both=False)

    def test_r3_01_a_cd_with_a_mixed_word_is_applied_once(self):
        self.deny(['A=; cd "docs"$A; rm ../CLAUDE.md', 'A=; cd "scripts"$A; rm guards.sh'], both=False)
        for c in ('A=; cd ".git"$A; echo x >> config', 'A=; cd ".git"$A; touch hooks/pre-commit'):  # CLAUDE_PROJECT_DIR is set in a real session
            for env in ({"CLAUDE_PROJECT_DIR": self.d}, {"CLAUDE_PROJECT_DIR": self.d, "LISTICLES_TASK": "tooling"}):
                self.assertEqual(self.bash(c, env), 2, (c, env))
        self.allow(['A=; cd "docs"$A; rm notes.md'])

    def test_r3_02_a_case_pattern_does_not_end_the_subshell(self):
        self.deny(
            [
                f"F=--force-with-lease; (F=--force; case x in x) ;; esac; {PUSH.replace('--force', '$F')})",
                "(F=--force; case x in x) esac; git push $F origin work)",
                "(IFS=_; case x in x) esac; P=--force_origin_work; git push $P)",
            ]
        )
        self.allow(["(F=ok; case x in x) esac); git status"])

    def test_r3_03_watch_after_dashes_with_clusters_and_expansions(self):
        self.deny([f"watch -- {PUSH}", f"watch -n 1 -- {PUSH}", f"watch -dx '{PUSH}'", f"X='x; {PUSH}'; watch echo \"$X\"", f"X=';{PUSH}'; watch true $X"])
        self.allow(["watch -n 5 -- git status", "watch -d git status", "watch -x git status", "watch -xn 5 git status"])

    def test_r3_09_a_command_name_variable_that_bash_changed_is_not_trusted(self):
        self.deny(
            [f"X=echo; {c}; $X push --force origin work" for c in ("export X=git", "read X <<< git", "printf -v X git", "eval X=git", "unset X; : ${X:=git}")]
        )
        self.deny(
            [
                'X=echo; declare X=git; "$X" push --force origin work',
                "X=echo; for X in git; do $X push --force origin work; done",
                "declare -n X=Y; X=echo; Y=git; $X push --force origin work",
            ]
        )
        self.deny(["X=echo; export X=rm; $X CLAUDE.md"], both=False)
        self.allow(["X=echo; $X hello", "X=ls; $X -la"])

    def test_r3_11_empty_fields_of_a_non_blank_ifs_are_kept(self):
        self.deny(["IFS=,; P=,; git commit -m $P -n", "IFS=,; P=,; git commit --allow-empty-message -m $P -n", "IFS=,; P=,,; git commit -m $P -n"])
        self.allow(["IFS=,; P=a,b; git commit -m $P", "IFS=,; P=,x; git commit -m $P"])

    def test_r3_06_ifs_set_by_a_statement_the_guard_does_not_follow(self):
        self.deny(
            [
                "IFS=-; unset IFS; P=--force; git push $P origin work",
                "IFS=-; read -r IFS <<< ' '; P=--force; git push $P origin work",
                "IFS=-; printf -v IFS ' '; P=--force; git push $P origin work",
                "IFS=-; declare -n R=IFS; R=' '; P=--force; git push $P origin work",
                "IFS=-; eval \"IFS=' '\"; P=--force; git push $P origin work",
                "IFS=-; for IFS in ' '; do P=--force; git push $P origin work; done",
                "IFS=-; unset IFS; P=-n; git commit -m x $P",
                "printf -v IFS _; P=--force_origin_work; git push $P",
                "read -r IFS <<< _; P=--force_origin_work; git push $P",
                "IFS=; unset IFS; P='--force origin'; git push $P work",
                "for IFS in _; do P=--force_origin_work; git push $P; done",
                "eval IFS=_; P=--force_origin_work; git push $P",
                "IFS=$(printf _); X=git_push; $X --force origin work",
            ]
        )
        self.allow(['while IFS= read -r line; do echo "$line"; done < f', "IFS=_; P=a_b; echo $P",
                'git commit -m "handle IFS in the guard"',
                "git log --grep=IFS"])

    def test_r3_04_env_split_string_with_expansions_comments_and_blanks_env_knows(self):
        self.deny(
            [
                "F=--force env -S'git push ${F} origin work'",
                "export F=--force; env -S'git push ${F}' origin work",
                "env -S'git #x' push --force origin work",
                "X='push --force origin work'; env -S\"git $X\"",
                "X='git push --force origin work'; env -S \"$X\"",
                r"env -S$'git\vpush\vorigin work'",
                r"env -S$'git\fpush --force origin work'",
            ]
        )
        self.allow(["env -S'git status'", "env -S'git log --oneline'"])

    def test_r3_05_a_protected_name_after_quoted_or_special_expansions(self):
        self.deny(
            [
                r"rm $(: \))CLAUDE.md",
                "rm $(: ')')CLAUDE.md",
                'rm $(: ")")CLAUDE.md',
                r"rm ${x#\}}CLAUDE.md",
                "rm $1CLAUDE.md",
                "rm $@CLAUDE.md",
                "rm $*CLAUDE.md",
                "rm $!CLAUDE.md",
                "rm -rf $1.claude",
            ],
            both=False,
        )
        self.deny(["echo x >> $1.git/config", "touch $1.git/hooks/pre-commit", "cp /tmp/x $@.git/hooks/pre-push", r"echo x > $(: \)).git/config"])
        self.allow([r"rm $(: \))notes.md", "rm $1notes.md"])

    def test_the_field_rules_of_the_splitter_lead_trail_and_empty_values(self):
        self.deny(['P="x "; git commit -m $P-n'])  # a trailing blank ends the word: the literal -n is a flag of its own
        self.allow(['P=" -n"; git commit -m $P', 'P="-m "; git commit $P -n', 'E=""; git commit -m $E -n', "export IFS=_; P=a; git status $P",
                    'P="--force origin"; git push "$P"$Q work'])  # a quoted $P in a mixed word stays one word

    def test_r3_07_only_the_expanded_text_splits_and_it_joins_the_literal_text_next_to_it(self):
        self.deny(['A=" --no-verify"; git commit -m "a -- b"$A', 'A=" --force"; git push -o "x -- y"$A origin work'])
        self.allow(['A=y; git commit -m "a -- b"$A', 'A=" y"; git commit -m "a -- b"$A', 'A="b c"; git commit -m a$A'])

    def test_r3_08_printf_v_attached_and_a_nameref_to_a_git_variable(self):
        self.deny([f'set -a; printf -vGIT_CONFIG_PARAMETERS %s "{P}"; git commit -m x', f'declare -n R=GIT_CONFIG_PARAMETERS; export R="{P}"; git commit -m x'])
        self.allow(["printf -vx %s ok", "declare -n r=x"])


if __name__ == "__main__":
    unittest.main()
