"""Tests for scripts/check_gradle_wrapper.py. Run: python3 -I scripts/test_check_gradle_wrapper.py"""

import contextlib
import io
import re
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_gradle_wrapper as c  # noqa: E402  # justified: must follow the sys.path insert above
import merge_ready  # noqa: E402  # justified: must follow the sys.path insert above

ROOT = Path(__file__).resolve().parent.parent
PROPS = ROOT / "gradle" / "wrapper" / "gradle-wrapper.properties"
SUM = "d8a18a7a841dd5df825d35a685fad6f2d7f12ac0c280e57b67c27b4a520ba228"
URL = "distributionUrl=https\\://services.gradle.org/distributions/gradle-9.9.1-bin.zip"
GOOD = f"distributionBase=GRADLE_USER_HOME\n{URL}\ndistributionSha256Sum={SUM}\nvalidateDistributionUrl=true\n"
CHECK_CMD = "python3 -I scripts/check_gradle_wrapper.py"
TEST_CMD = "python3 -I scripts/test_check_gradle_wrapper.py"


def sum_problems(text):
    return [p for p in c.check_properties(text) if "distributionSha256Sum" in p]


class Properties(unittest.TestCase):
    def test_good_properties_pass(self):
        self.assertEqual(c.check_properties(GOOD), [])

    def test_sum_missing(self):
        got = c.check_properties(GOOD.replace(f"distributionSha256Sum={SUM}\n", ""))
        self.assertEqual(got, ["distributionSha256Sum is missing"])

    def test_sum_only_in_a_comment(self):
        for mark in ("#", "!", "  # "):
            with self.subTest(mark=mark):
                got = c.check_properties(GOOD.replace("distributionSha256Sum=", f"{mark}distributionSha256Sum="))
                self.assertEqual(got, ["distributionSha256Sum is missing"])

    def test_sum_empty_or_keyless(self):
        for line in ("distributionSha256Sum=", "distributionSha256Sum", "distributionSha256Sum=   "):
            with self.subTest(line=line):
                got = c.check_properties(GOOD.replace(f"distributionSha256Sum={SUM}", line))
                self.assertEqual(got, ["distributionSha256Sum must be 64 lowercase hex characters (sha256), got an empty value"])

    def test_sum_malformed(self):
        bad = {
            "too short": SUM[:63],
            "too long": SUM + "0",
            "md5 length": SUM[:32],
            "uppercase": SUM.upper(),
            "non hex": SUM[:-1] + "g",
            "trailing space": SUM + " ",
            "quoted": f'"{SUM}"',
            "sha256 prefix": f"sha256:{SUM}",
        }
        for name, value in bad.items():
            with self.subTest(name=name):
                got = sum_problems(GOOD.replace(f"distributionSha256Sum={SUM}", f"distributionSha256Sum={value}"))
                self.assertEqual(len(got), 1, got)
                self.assertIn("64 lowercase hex characters", got[0])

    def test_sum_placeholder_is_refused(self):
        for digit in "0123456789abcdef":
            with self.subTest(digit=digit):
                got = sum_problems(GOOD.replace(SUM, digit * 64))
                self.assertEqual(got, ["distributionSha256Sum is a placeholder (one repeated digit), not a real checksum"])

    def test_sum_twice(self):
        other = "1a" * 32
        got = c.check_properties(GOOD + f"distributionSha256Sum={other}\n")
        self.assertEqual(got, ["distributionSha256Sum is set more than once"])

    def test_properties_separator_forms_are_read(self):
        for line in (f"distributionSha256Sum = {SUM}", f"distributionSha256Sum:{SUM}", f"distributionSha256Sum {SUM}"):
            with self.subTest(line=line):
                self.assertEqual(c.check_properties(GOOD.replace(f"distributionSha256Sum={SUM}", line)), [])
        bad = GOOD.replace(f"distributionSha256Sum={SUM}", f"distributionSha256Sum = {SUM[:10]}")
        self.assertEqual(len(sum_problems(bad)), 1)

    def test_similar_key_is_not_the_sum(self):
        got = c.check_properties(GOOD.replace("distributionSha256Sum=", "distributionSha256SumX="))
        self.assertEqual(got, ["distributionSha256Sum is missing"])

    def test_url_missing_or_foreign_host(self):
        self.assertEqual(c.check_properties(GOOD.replace(URL + "\n", "")), ["distributionUrl is missing"])
        other = "distributionUrl=https\\://example.com/distributions/gradle-9.9.1-bin.zip"
        self.assertEqual(
            c.check_properties(GOOD.replace(URL, other)),
            ["distributionUrl must be a https://services.gradle.org/distributions/ zip (the checksum is the one published there)"],
        )
        http = URL.replace("https", "http")
        self.assertEqual(len(c.check_properties(GOOD.replace(URL, http))), 1)


class LineContinuation(unittest.TestCase):
    """java.util.Properties joins a line ending in an odd number of backslashes with the next line (R1-01)."""

    SUM_LINE = f"distributionSha256Sum={SUM}"

    def props(self, *lines):
        return "\n".join(lines) + "\n"

    def test_continued_line_before_the_sum_folds_it_away(self):
        for name, folded in {
            "one backslash": "networkTimeout=10000\\",
            "three backslashes": "networkTimeout=10000\\\\\\",
            "empty value then backslash": "zipStorePath=\\",
        }.items():
            with self.subTest(name=name):
                text = self.props(URL, folded, self.SUM_LINE, "validateDistributionUrl=true")
                self.assertEqual(c.check_properties(text), ["distributionSha256Sum is missing"])

    def test_continued_line_before_the_url_folds_it_away(self):
        text = self.props("distributionPath=wrapper/dists\\", URL, self.SUM_LINE)
        self.assertEqual(c.check_properties(text), ["distributionUrl is missing"])

    def test_continuation_line_leading_blanks_do_not_unfold_it(self):
        text = self.props(URL, "networkTimeout=10000\\", "    " + self.SUM_LINE)
        self.assertEqual(c.check_properties(text), ["distributionSha256Sum is missing"])

    def test_the_sum_line_itself_continued_into_the_next_line_is_malformed(self):
        text = self.props(URL, self.SUM_LINE + "\\", "validateDistributionUrl=true")
        got = sum_problems(text)
        self.assertEqual(len(got), 1, got)
        self.assertIn("64 lowercase hex characters", got[0])

    def test_continued_line_swallows_a_following_comment_marker_line(self):
        text = self.props(URL, "networkTimeout=10000\\", "#" + self.SUM_LINE)
        self.assertEqual(c.check_properties(text), ["distributionSha256Sum is missing"])

    def test_escaped_backslash_does_not_continue(self):
        for slashes in ("\\\\", "\\\\\\\\"):
            with self.subTest(slashes=slashes):
                text = self.props(URL, "networkTimeout=10000" + slashes, self.SUM_LINE)
                self.assertEqual(c.check_properties(text), [])

    def test_comment_line_ending_in_a_backslash_does_not_continue(self):
        for mark in ("#", "!"):
            with self.subTest(mark=mark):
                text = self.props(URL, f"{mark} note\\", self.SUM_LINE)
                self.assertEqual(c.check_properties(text), [])

    def test_the_real_file_has_no_continued_line(self):
        for number, line in enumerate(PROPS.read_text(encoding="utf-8").splitlines(), 1):
            slashes = len(line) - len(line.rstrip("\\"))
            self.assertEqual(slashes % 2, 0, f"gradle-wrapper.properties line {number} ends in a line continuation")


class RealRepo(unittest.TestCase):
    def test_repo_wrapper_properties_pass(self):
        self.assertEqual(c.main(ROOT), 0)

    def test_repo_wrapper_pins_a_sum(self):
        self.assertRegex(PROPS.read_text(encoding="utf-8"), r"(?m)^distributionSha256Sum=[0-9a-f]{64}$")

    def test_main_fails_on_properties_without_a_sum(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "gradle" / "wrapper").mkdir(parents=True)
            (Path(tmp) / "gradle" / "wrapper" / "gradle-wrapper.properties").write_text(
                GOOD.replace(f"distributionSha256Sum={SUM}\n", ""), encoding="utf-8"
            )
            with contextlib.redirect_stdout(io.StringIO()) as out:
                self.assertEqual(c.main(tmp), 1)
                self.assertEqual(c.main(Path(tmp) / "nowhere"), 1)
            self.assertIn("distributionSha256Sum is missing", out.getvalue())

    def test_merge_ready_accepts_the_sum_line_as_a_wrapper_bump_line(self):
        sum_line = next(ln for ln in PROPS.read_text(encoding="utf-8").splitlines() if ln.startswith("distributionSha256Sum="))
        url_line = next(ln for ln in PROPS.read_text(encoding="utf-8").splitlines() if ln.startswith("distributionUrl="))
        patch = f"@@ -1,2 +1,2 @@\n-{url_line}\n+{url_line}\n-{sum_line}\n+distributionSha256Sum={'a' * 64}"
        self.assertTrue(merge_ready.wrapper_only(patch))
        self.assertFalse(merge_ready.wrapper_only(patch + "\n+validateDistributionUrl=false"))


def runs(text, cmd):
    """True if an active line is exactly the command as a top-level verify.sh `step <name> <cmd>` (not indented, not in an if)."""
    return any(re.fullmatch(rf"step \S+ {re.escape(cmd)}", ln) for ln in text.splitlines())


def wiring_problems(verify):
    return [f"verify.sh does not run `{cmd}` as a top-level step" for cmd in (CHECK_CMD, TEST_CMD) if not runs(verify, cmd)]


class Wiring(unittest.TestCase):
    good = f"step wrapper-checksum {CHECK_CMD}\nstep wrapper-checksum-tests {TEST_CMD}\n"

    def test_repo_verify_sh_runs_both(self):
        self.assertEqual(wiring_problems((ROOT / "scripts" / "verify.sh").read_text(encoding="utf-8")), [])

    def test_wiring_negative_cases(self):
        self.assertEqual(wiring_problems(self.good), [])
        for name, text in {
            "missing check": self.good.replace(f"step wrapper-checksum {CHECK_CMD}\n", ""),
            "missing tests": self.good.replace(f"step wrapper-checksum-tests {TEST_CMD}\n", ""),
            "commented": self.good.replace("step wrapper-checksum ", "# step wrapper-checksum "),
            "inside an if (skipped by --fast)": f"if [ x ]; then\n  step a {CHECK_CMD}\n  step b {TEST_CMD}\nfi\n",
            "with || true": self.good.replace(CHECK_CMD, CHECK_CMD + " || true"),
        }.items():
            with self.subTest(name=name):
                self.assertNotEqual(wiring_problems(text), [])


if __name__ == "__main__":
    unittest.main()
