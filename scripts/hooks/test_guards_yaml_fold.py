"""Tests for the YAML joined-line check of guards.sh check 2c (issue 164 item 2, task M1-64). Run: python3 -I -m unittest discover -s scripts/hooks

A YAML value that goes on over several lines (a folded block `run: >`, a plain or quoted scalar, a flow collection) is one shell line
for the runner. The guard checks it as one line IN ADDITION to the per-line check of main, never instead of it (escalation ruling on
PR 309, comment 7084379032): every input that fails on main still fails (Y1, Y3, Y5 of the ruling), and a reason waives a joined
value only when every line of it has one.
"""

import os
import stat
import unittest

import test_guards_sh as base

MARK = "guard: unjustified CLI flag"
WF = ".github/workflows/ci.yml"
PC = ".pre-commit-config.yaml"
STEPS = "jobs:\n  a:\n    steps:\n"
HOOKS = "repos:\n  - repo: local\n    hooks:\n"
R = " # justified: three words here"


class FoldCase(base.GuardsCase):
    def write(self, rel, text):
        self.repo.write(rel, text, raw=True)
        self.repo.commit()

    def fails_at(self, cases):
        for path, text, n in cases:
            with self.subTest(text=text):
                self.write(path, text)
                self.assertFails(f"{MARK}: {path}:{n}:")

    def passes(self, cases):
        for path, text in cases:
            with self.subTest(ok=text):
                self.write(path, text)
                self.assertPasses()


class RulingTests(FoldCase):
    """Y1, Y3 and Y5 of the ruling: a reason on another line of the value never waives a flag the per-line check finds."""

    def test_y1_y3_y5_still_fail(self):
        self.fails_at([
            (WF, STEPS + "      - run: ruff check --ignore E501 .\n          --fix" + R + "\n", 4),
            (WF, STEPS + "      - run: >\n          ruff check --ignore E501 .\n          && echo ok" + R + "\n", 5),
            (PC, HOOKS + "      - id: x\n        entry: ruff check --ignore E501\n          --fix" + R + "\n", 5),
        ])

    def test_a_reason_on_a_comment_line_or_on_one_line_of_the_value_waives_nothing(self):
        self.fails_at([
            (WF, STEPS + "      - run: ruff check --ignore E501 .\n          # justified: three words here\n", 4),
            (WF, STEPS + "      - run: ruff check\n          --ignore E501 ." + R + "\n", 4),
            (WF, STEPS + '      - run: "ruff check $(: justified: three words here)\n          --ignore E501 ."\n', 4),
            (WF, STEPS + "      - run: >\n          ruff check \"justified: three words here\"\n          --ignore E501 .\n", 5),
        ])


class JoinedValueTests(FoldCase):
    """Forms main reads line by line, so the tool and its flag are on different lines and main passes them."""

    def test_folded_blocks(self):
        self.fails_at([
            (WF, STEPS + "      - run: >\n          ruff check\n          --ignore E501 .\n", 5),
            (WF, STEPS + "      - run: >-\n          eslint\n          --quiet .\n", 5),
            (WF, STEPS + "      - run: &r >\n          ruff check\n          --ignore E501 .\n", 5),
            (WF, STEPS + "      - run: !!str >\n          ruff check\n          --ignore E501 .\n", 5),
            (WF, STEPS + "      - run:\n          >\n            ruff check\n            --ignore E501 .\n", 6),
            # R2-04: an indentation indicator, the first line more indented than the folded ones.
            (WF, STEPS + "      - run: >2\n            echo start\n          ruff check\n          --ignore E501 .\n", 6),
            # A blank line or a more-indented line is a line break, so an install before it does not hide the run after it.
            (WF, STEPS + "      - run: >\n          pip install ruff\n\n          ruff check\n          --ignore E501 .\n", 7),
            (WF, STEPS + "      - run: >\n          pip install ruff\n            x\n          ruff check\n          --ignore E501 .\n", 7),
        ])

    def test_plain_and_quoted_scalars(self):
        self.fails_at([
            (WF, STEPS + "      - run: ruff check\n          --ignore E501 .\n", 4),
            (WF, STEPS + '      - run: "ruff check\n          --ignore E501 ."\n', 4),
            (WF, STEPS + "      - run: 'ruff check\n          --ignore E501 .'\n", 4),
            (WF, "jobs:\n  a:\n    steps:\n      - run: \"ruff check\n   --ignore E501 .\"\n", 4),
            # R2-05: the value starts on the line after the key, also after an anchor or a tag.
            (WF, STEPS + "      - name: x\n        run:\n          ruff check\n          --ignore E501 .\n", 6),
            (WF, STEPS + '      - run:\n          "ruff check\n          --ignore E501 ."\n', 5),
            (WF, STEPS + "      - run: !!str\n          ruff check\n          --ignore E501 .\n", 5),
            (PC, HOOKS + "      - id: x\n        entry: ruff check\n          --ignore E501\n", 5),
        ])

    def test_double_quoted_escapes_are_read_as_yaml_reads_them(self):
        self.fails_at([
            (WF, STEPS + '      - run: "ru\\\n          ff check --ignore E501 ."\n', 4),
            (WF, STEPS + '      - run: "ruff check \\x2d-fix ."\n', 4),
            (WF, STEPS + '      - run: "ruff check \\u002d-fix ."\n', 4),
            (WF, STEPS + '      - run: "ruff check\\t--fix ."\n', 4),
            (WF, STEPS + '      - run: "pip install ruff\\nruff check --fix ."\n', 4),
            (WF, STEPS + '      - run: "ruff check\n          \\x2d-ignore E501 ."\n', 4),
            (WF, STEPS + '      - run: "ruff check \\"--fix\\" ."\n', 4),
        ])

    def test_a_pre_commit_entry_block_is_one_word_list(self):
        self.fails_at([
            (PC, HOOKS + "      - id: x\n        entry: >\n          ruff check\n        args: [--fix]\n", 7),
            (PC, HOOKS + "      - id: x\n        entry: |\n          ruff check\n          --fix\n", 5),
            (PC, HOOKS + "      - id: x\n        entry: |\n          ruff check\n          # x\n          --fix\n", 5),
            (PC, HOOKS + "      - id: x\n        entry:\n          >-\n            ruff check\n            --fix\n", 5),
        ])
        self.passes([(PC, HOOKS + "      - id: x\n        entry: |\n          ruff check\n          --no-cache\n")])

    def test_flow_collections_and_args_keys(self):
        self.fails_at([
            (WF, STEPS + "      - {name: a, run: ruff check\n          --ignore E501 .}\n", 4),
            (WF, STEPS + "      - {run: pip install ruff\n\n          ruff check\n          --ignore E501 .}\n", 6),
            (WF, STEPS + "      - uses: astral-sh/ruff-action@v3\n        with: {args:\n          check --fix}\n", 5),
            (PC, HOOKS + "      - {id: ruff,\n         args: [\n           --fix]}\n", 4),
        ])

    def test_the_staged_scan_joins_too(self):
        self.repo.write(WF, STEPS + "      - run: >\n          ruff check\n          --ignore E501 .\n", raw=True)
        self.repo.git("add", "-A")
        self.assertFails(f"{MARK}: {WF}:5:", "--staged")


class SelfReviewTests(FoldCase):
    """Self-review (verifier): a node property or a JSON-style `"key":"value"` before a quoted value in a flow collection, a composite
    action, and a fold scan that cannot run (it must fail, not go quiet)."""

    def test_properties_and_json_style_keys_in_a_flow(self):
        ent = "      - {id: x, name: x, language: system, entry: &e \"ruff check \\x2d-fix\"}\n"
        self.fails_at([
            (WF, STEPS + '      - {run: &a "ruff check \\x2d-fix ."}\n', 4),
            (WF, STEPS + '      - {run: !!str "ruff check \\x2d-fix ."}\n', 4),
            (WF, STEPS + '      - {run: &a "echo }; ruff check\n          --ignore E501 ."}\n', 4),
            (WF, STEPS + '      - {run: &a "echo ]; ruff check\n          --ignore E501 ."}\n', 4),
            (WF, STEPS + '      - {"run":"echo }; ruff check\n          --ignore E501 ."}\n', 4),
            (WF, STEPS + '      - {"run":"ruff check \\x2d-fix ."}\n', 4),
            (WF, STEPS + '      - {run: !!str &a\n          "ruff check \\x2d-fix ."}\n', 4),
            (WF, STEPS + '      - uses: astral-sh/ruff-action@v3\n        with: {args: &a "check \\x2d-fix"}\n', 5),
            (PC, HOOKS + ent, 4),
            (PC, HOOKS + '      - {"id":"x","name":"x","language":"system","entry":"ruff check \\x2d-fix"}\n', 4),
        ])

    def test_a_composite_action_is_joined_too(self):
        self.fails_at([(".github/actions/lint/action.yml",
                        "runs:\n  using: composite\n  steps:\n    - run: >\n        ruff check\n        --ignore E501 .\n      shell: bash\n", 5)])

    def test_a_fold_scan_that_fails_fails_the_guard(self):
        d = os.path.join(self.repo.dir, ".fakebin")
        os.makedirs(d)
        real = base.shutil.which("awk")
        with open(os.path.join(d, "awk"), "w") as f:
            f.write(f'#!/bin/sh\ncase "$*" in *"function yent"*) exit 2 ;; esac\nexec "{real}" "$@"\n')
        os.chmod(os.path.join(d, "awk"), stat.S_IRWXU)
        self.write(WF, STEPS + "      - run: echo ok\n")
        self.assertFails(f"{MARK}: {WF}:0: the YAML fold scan failed", PATH=d + os.pathsep + os.environ["PATH"])


class ReviewRound1Tests(FoldCase):
    """PR 325 review round 1: R1-01 an item with nothing after its dash (or only an anchor) holds a block mapping, R1-02 a tracked
    YAML file missing from the working tree has nothing to scan, R1-03 the per-line scan of YAML files still runs beside the joined one."""

    def fake_awk(self, fold_body):
        d = os.path.join(self.repo.dir, ".fakebin")
        os.makedirs(d, exist_ok=True)
        real = base.shutil.which("awk")
        with open(os.path.join(d, "awk"), "w") as f:
            f.write(f'#!/bin/sh\ncase "$*" in *"function yent"*) {fold_body} ;; esac\nexec "{real}" "$@"\n')
        os.chmod(os.path.join(d, "awk"), stat.S_IRWXU)
        return d + os.pathsep + os.environ["PATH"]

    def test_a_bare_dash_item_holds_a_mapping(self):
        self.passes([
            (WF, STEPS + "      -\n        run: |\n          ruff check .\n          echo --fix\n"),
            (WF, STEPS + "      -\n        name: ruff check\n        run: echo --fix\n"),
            (WF, STEPS + "      - &x\n        run: |\n          ruff check .\n          echo --fix\n"),
        ])
        self.fails_at([
            (WF, STEPS + "      -\n        run: ruff check\n          --ignore E501 .\n", 5),
            (WF, STEPS + "      - &x\n        run: ruff check\n          --ignore E501 .\n", 5),
            (WF, STEPS + "      -\n        ruff check\n        --ignore E501 .\n", 5),
        ])

    def test_a_tracked_yaml_file_missing_from_the_tree_passes(self):
        self.write(WF, STEPS + "      - run: echo ok\n")
        os.remove(os.path.join(self.repo.dir, WF))
        self.assertPasses()

    def test_the_per_line_scan_still_runs_when_the_joined_one_finds_nothing(self):
        self.write(WF, STEPS + "      - run: ruff check --ignore E501 .\n")
        self.assertFails(f"{MARK}: {WF}:4:", PATH=self.fake_awk("cat >/dev/null; exit 0"))


class NeighbourTests(FoldCase):
    def test_allowed_or_separate_lines_pass(self):
        self.passes([
            (WF, STEPS + "      - run: >\n          ruff check\n          --config ruff.toml .\n"),
            (WF, STEPS + "      - run: ruff check\n          --no-cache .\n"),
            (WF, STEPS + "      - run: >\n          ruff check .\n\n          mypy --strict .\n"),
            (WF, STEPS + "      - run: >\n          ruff check .\n            && mypy --strict .\n"),
            (WF, STEPS + "      - run: |\n          ruff check .\n          echo --fix\n"),
            (WF, STEPS + "      - run: |\n          echo \"x: >\"\n          ruff check .\n          echo --ignore\n"),
            (WF, STEPS + "      - name: ruff\n        run: echo done\n      - run: echo --fix\n"),
            (WF, STEPS + "      - uses: astral-sh/ruff-action@v3\n        with:\n          args: check\n          version: 0.5\n"),
            (WF, STEPS + '      - run: "ruff check \\"a b\\" --no-cache ."\n'),
            (WF, "on:\n  push:\n    paths:\n      - a\n      - b\n" + STEPS + "      - run: ruff check .\r\n"),
        ])

    def test_a_reason_on_every_line_waives_the_value(self):
        self.passes([
            (WF, STEPS + "      - run: >\n          ruff check" + R + "\n          --ignore E501 ." + R + "\n"),
            (WF, STEPS + '      - run: "ruff check' + R + '\n          --ignore E501 .' + R + '"\n'),
        ])


if __name__ == "__main__":
    unittest.main()
