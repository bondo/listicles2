"""Tests for scripts/agent_metrics.py. Run: python3 -I scripts/test_agent_metrics.py"""

import csv
import io
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import agent_metrics as am  # noqa: E402  # justified: must follow the sys.path insert above

ROOT = Path(__file__).resolve().parent.parent

SESSION_HDR = (
    "date,batch,pr,tasks,role,session_id,model,effort,env,result,cost_usd,input_tokens,output_tokens,"
    "cache_read_tokens,cache_write_tokens,handoffs,verify_fails_before_push,ci_red_runs,"
    "post_cap_commits,owner_interventions"
)
OLD_SESSION_HDR = (  # ORCHESTRATION 6.1 before the three new columns
    "date,batch,pr,tasks,role,session_id,model,effort,result,cost_usd,input_tokens,output_tokens,"
    "cache_read_tokens,cache_write_tokens,handoffs,verify_fails_before_push,ci_red_runs"
)
ROUND_HDR = (
    "date,batch,pr,round,reviewer_session,base_sha,head_sha,blocker,major,minor,nit,disputed,withdrawn,"
    "deferred,verdict"
)
INCIDENT_HDR = "date,batch,session_id,kind,impact,recovery,prevention"
S1 = "2026-11-12,M0.5-13,60,M0.5-13,implementer,session_a,claude-sonnet-5-5,medium,tooling,done,1.25,10,20,30,40,0,1,0,0,0"
R1 = "2026-11-12,M0.5-13,60,1,session_r,abc1234,def5678,0,1,2,3,0,0,0,changes_requested"
I1 = "2026-11-10,M0-1,session_a,destructive-git,work lost,reflog,deny hook"


def block(kind, header, *rows):
    return f"# metrics:{kind}\n{header}\n" + "\n".join(rows) + "\n"


def run(*texts):
    return am.build(list(texts))


class ParseTests(unittest.TestCase):
    def test_all_three_kinds(self):
        rows, errors = run(block("session", SESSION_HDR, S1), block("round", ROUND_HDR, R1),
                           block("incident", INCIDENT_HDR, I1))
        self.assertEqual(errors, [])
        self.assertEqual([r["row_type"] for r in rows], ["session", "round", "incident"])
        self.assertEqual(rows[0]["cost_usd"], "1.25")
        self.assertEqual(rows[1]["verdict"], "changes_requested")
        self.assertEqual(rows[2]["incident_kind"], "destructive-git")

    def test_comment_prose_and_code_fence(self):
        text = "Worker done.\n\n```csv\n" + block("session", SESSION_HDR, S1) + "```\n\nThanks.\n"
        rows, errors = run(text)
        self.assertEqual(errors, [])
        self.assertEqual(len(rows), 1)

    def test_old_session_header_without_new_columns(self):
        old = "2026-11-12,B,1,T,reviewer,session_x,m,high,done,0.5,1,2,3,4,0,,"
        rows, errors = run(block("session", OLD_SESSION_HDR, old))
        self.assertEqual(errors, [])
        self.assertEqual(rows[0]["env"], "")
        self.assertEqual(rows[0]["owner_interventions"], "")

    def test_empty_fields_are_allowed(self):
        rows, errors = run(block("session", SESSION_HDR, ",M0-2,,,,,,,,,5.02,,,,,,,,,"))
        self.assertEqual(errors, [])
        self.assertEqual(rows[0]["cost_usd"], "5.02")

    def test_quoted_field_with_comma(self):
        inc = '2026-11-10,M0-1,session_a,destructive-git,"work lost, partly",reflog,hook'
        rows, errors = run(block("incident", INCIDENT_HDR, inc))
        self.assertEqual(errors, [])
        self.assertEqual(rows[0]["impact"], "work lost, partly")

    def test_no_blocks_gives_no_rows(self):
        self.assertEqual(run("just prose\n"), ([], []))

    def test_output_is_deterministic_and_sorted(self):
        s2 = S1.replace("session_a", "session_b").replace("2026-11-12", "2026-11-01")
        a, _ = run(block("session", SESSION_HDR, S1, s2))
        b, _ = run(block("session", SESSION_HDR, s2, S1))
        self.assertEqual(a, b)
        self.assertEqual(a[0]["session_id"], "session_b")
        self.assertEqual(am.render(a), am.render(b))

    def test_render_has_fixed_header_and_roundtrips(self):
        rows, _ = run(block("session", SESSION_HDR, S1), block("round", ROUND_HDR, R1))
        out = am.render(rows)
        reader = csv.DictReader(io.StringIO(out))
        self.assertEqual(reader.fieldnames, am.COLUMNS)
        self.assertEqual(len(list(reader)), 2)


class NegativeTests(unittest.TestCase):
    def assertError(self, texts, needle):
        rows, errors = run(*texts)
        self.assertTrue(any(needle in e for e in errors), f"{needle!r} not in {errors}")
        return rows

    def test_malformed_row_too_few_fields(self):
        self.assertError([block("session", SESSION_HDR, "2026-11-12,B,1")], "fields")

    def test_malformed_row_too_many_fields(self):
        self.assertError([block("session", SESSION_HDR, S1 + ",extra")], "fields")

    def test_missing_required_column(self):
        hdr = SESSION_HDR.replace("session_id,", "")
        row = ",".join(S1.split(",")[:5] + S1.split(",")[6:])
        self.assertError([block("session", hdr, row)], "missing column")

    def test_unknown_column(self):
        self.assertError([block("session", SESSION_HDR + ",bogus", S1 + ",x")], "unknown column")

    def test_duplicate_column(self):
        self.assertError([block("incident", INCIDENT_HDR + ",impact", I1 + ",x")], "duplicate column")

    def test_header_missing_after_marker(self):
        self.assertError(["# metrics:session\n"], "header")

    def test_duplicate_session_ids(self):
        self.assertError([block("session", SESSION_HDR, S1, S1)], "duplicate session_id")

    def test_duplicate_session_ids_across_inputs(self):
        self.assertError([block("session", SESSION_HDR, S1), block("session", SESSION_HDR, S1)],
                         "duplicate session_id")

    def test_duplicate_round(self):
        self.assertError([block("round", ROUND_HDR, R1, R1)], "duplicate round")

    def test_non_numeric_cost(self):
        for bad in ("abc", "~4", "$4.28", "1,5", "-1", "1e3", "4."):
            row = S1.replace(",1.25,", f',"{bad}",')
            self.assertError([block("session", SESSION_HDR, row)], "cost_usd")

    def test_non_numeric_tokens_and_counts(self):
        self.assertError([block("session", SESSION_HDR, S1.replace(",10,20,", ",ten,20,"))], "input_tokens")
        self.assertError([block("round", ROUND_HDR, R1.replace(",0,1,2,3,", ",0,x,2,3,"))], "major")
        self.assertError([block("session", SESSION_HDR, S1.replace(",10,20,", ",1.5,20,"))], "input_tokens")

    def test_bad_date(self):
        self.assertError([block("session", SESSION_HDR, S1.replace("2026-11-12", "12/11/2026"))], "date")
        self.assertError([block("session", SESSION_HDR, S1.replace("2026-11-12", "2026-13-40"))], "date")

    def test_round_needs_pr_and_round_number(self):
        self.assertError([block("round", ROUND_HDR, R1.replace(",60,1,", ",,1,"))], "pr")
        self.assertError([block("round", ROUND_HDR, R1.replace(",60,1,", ",60,,"))], "round")

    def test_errors_name_the_input_and_line(self):
        _, errors = am.build(["# metrics:session\n" + SESSION_HDR + "\nshort\n"], names=["c1.txt"])
        self.assertTrue(errors[0].startswith("c1.txt:3:"), errors)

    def test_all_errors_reported_not_just_first(self):
        _, errors = run(block("session", SESSION_HDR, "bad", "worse"))
        self.assertEqual(len(errors), 2)


class CliTests(unittest.TestCase):
    def cli(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = am.main(argv)
        return code, out.getvalue(), err.getvalue()

    def test_writes_output_file(self):
        with tempfile.TemporaryDirectory() as d:
            src, dst = Path(d, "in.txt"), Path(d, "out.csv")
            src.write_text(block("session", SESSION_HDR, S1))
            code, _, err = self.cli(["-o", str(dst), str(src)])
            self.assertEqual((code, err), (0, ""))
            self.assertIn("session_a", dst.read_text())

    def test_errors_exit_1_and_write_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            src, dst = Path(d, "in.txt"), Path(d, "out.csv")
            src.write_text(block("session", SESSION_HDR, "bad"))
            code, _, err = self.cli(["-o", str(dst), str(src)])
            self.assertEqual(code, 1)
            self.assertIn("in.txt:3", err)
            self.assertFalse(dst.exists())

    def test_check_detects_stale_output(self):
        with tempfile.TemporaryDirectory() as d:
            src, dst = Path(d, "in.txt"), Path(d, "out.csv")
            src.write_text(block("session", SESSION_HDR, S1))
            self.assertEqual(self.cli(["-o", str(dst), str(src)])[0], 0)
            self.assertEqual(self.cli(["--check", "-o", str(dst), str(src)])[0], 0)
            dst.write_text(dst.read_text() + "x\n")
            code, _, err = self.cli(["--check", "-o", str(dst), str(src)])
            self.assertEqual(code, 1)
            self.assertIn("out of date", err)

    def test_check_fails_when_output_missing(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d, "in.txt")
            src.write_text(block("session", SESSION_HDR, S1))
            self.assertEqual(self.cli(["--check", "-o", str(Path(d, "nope.csv")), str(src)])[0], 1)

    def test_missing_input_file(self):
        code, _, err = self.cli(["/nonexistent/in.txt"])
        self.assertEqual(code, 1)
        self.assertIn("in.txt", err)

    def test_no_inputs_is_an_error(self):
        with tempfile.TemporaryDirectory() as d:
            code, _, err = self.cli(["-o", str(Path(d, "o.csv")), str(Path(d, "empty-dir-*.txt"))])
            self.assertEqual(code, 1)


class RepoTests(unittest.TestCase):
    def test_committed_csv_matches_saved_inputs(self):
        code = am.main(["--check", "-o", str(ROOT / "docs/agent-metrics.csv"),
                        *map(str, sorted((ROOT / "docs/metrics").glob("*.txt")))])
        self.assertEqual(code, 0)

    def test_backfill_exact_rows(self):
        text = (ROOT / "docs/metrics/m0-backfill.txt").read_text()
        rows, errors = am.build([text])
        self.assertEqual(errors, [])
        got = sorted((r["row_type"], r["batch"], r["pr"], r["role"], r["cost_usd"], r["incident_kind"],
                      r["recovery"], r["impact"], r["date"]) for r in rows)
        self.assertEqual(got, sorted([
            ("session", "M0-1", "1", "", "4.28", "", "", "", ""),
            ("session", "M0-2", "", "", "5.02", "", "", "", ""),
            ("session", "PR16-merge-review", "16", "reviewer", "2.23", "", "", "", ""),
            ("session", "PR16-merge-review", "16", "implementer", "2.43", "", "", "", ""),
            ("round", "PR16-merge-review", "16", "", "", "", "", "", ""),
            ("incident", "M0-1", "", "", "", "destructive-git", "recovered", "", ""),
        ]))

    def test_backfill_says_batch_totals(self):
        text = (ROOT / "docs/metrics/m0-backfill.txt").read_text()
        self.assertIn("batch totals", text)

    def test_docs_use_the_script_name_and_no_stale_wording(self):
        for f in ("ORCHESTRATION.md", "PLAN.md"):
            text = (ROOT / "docs" / f).read_text()
            self.assertNotIn("scripts/agent-metrics", text, f)
            self.assertNotIn("Until the script exists", text, f)

    def test_per_session_definitions_documented(self):
        text = (ROOT / "docs/ORCHESTRATION.md").read_text()
        self.assertIn("`post_cap_commits` counts commits this session pushed", text)
        self.assertIn("`owner_interventions` counts owner decisions this session", text)


class HardeningTests(unittest.TestCase):
    def one(self, row):
        return run(block("session", SESSION_HDR, row))

    def test_huge_field_is_an_error_not_a_traceback(self):
        _, errors = self.one(S1.replace(",tooling,", "," + "x" * 200000 + ","))
        self.assertEqual(len(errors), 1, errors)
        self.assertRegex(errors[0], r"^input1:3: ")
        self.assertIn("malformed", errors[0])

    def test_formula_injection_rejected(self):
        for bad in ("=HYPERLINK(1)", "+1", "-1", "@SUM(A1)", "\tx", "\rx"):
            quoted = '"' + bad + '"'
            _, errors = self.one(S1.replace(",tooling,", "," + quoted + ","))
            self.assertTrue(any("env" in e for e in errors), (bad, errors))
        _, errors = run(block("incident", INCIDENT_HDR, '2026-11-10,M0-1,s,k,"=1+1",r,p'))
        self.assertTrue(any("impact" in e for e in errors), errors)

    def test_control_characters_rejected(self):
        for bad in ("a\x00b", "a\x07b", "a\x7fb", "a\tb"):
            _, errors = self.one(S1.replace(",tooling,", "," + bad + ","))
            self.assertTrue(any("control" in e for e in errors), (bad, errors))

    def test_surrounding_whitespace_rejected(self):
        for bad in (" session_a", "session_a "):
            _, errors = self.one(S1.replace("session_a", bad))
            self.assertTrue(any("whitespace" in e for e in errors), (bad, errors))

    def test_leading_zero_integers_rejected(self):
        _, errors = self.one(S1.replace(",60,M0.5-13,", ",060,M0.5-13,"))
        self.assertTrue(any("pr" in e for e in errors), errors)
        _, errors = run(block("round", ROUND_HDR, R1, R1.replace(",60,1,", ",060,1,")))
        self.assertTrue(errors, errors)

    def test_zero_is_a_valid_integer(self):
        _, errors = self.one(S1)
        self.assertEqual(errors, [])

    def test_ordinary_text_with_inner_symbols_ok(self):
        inc = "2026-11-10,M0-1,s,k,a = b - c @ d,r,p"
        rows, errors = run(block("incident", INCIDENT_HDR, inc))
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
