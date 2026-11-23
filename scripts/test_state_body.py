"""Tests for scripts/state_body.py (M1-77). Run: python3 -I scripts/test_state_body.py"""

import copy
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import state_body  # noqa: E402  # justified: must follow the sys.path insert above

S1, S2, S0 = "session_01AbC", "session_01XyZ", "session_00Old"
STATE = {
    "schema": 1,
    "orchestrator": {"session": S1, "since": "2026-11-23T05:33Z", "predecessor": S0, "depth": 4},
    "updated": {"at": "2026-11-23T06:10Z", "after": "check-in"},
    "inbox_since": "2026-11-23T05:27:24Z",
    "tasks_ref": "main",
    "usage": {"state": "ok", "read_at": "2026-11-23T05:25Z"},
    "sessions": [
        {"id": S2, "role": "implementer", "tags": ["batch:M1-14", "pr:319"], "branch": "m1/auth-data-14", "pr": 319, "tasks": ["M1-14"],
         "spawned": "2026-11-23T01:00Z", "expects": "WORKER-RESULT + push", "checked": "2026-11-23T06:00Z",
         "status": "running", "note": "fixing the conflict"},
    ],
    "branches": [
        {"name": "tooling/ci-hardening-44", "holder": None, "pr": 331, "in_review": ["M1-44"],
         "reviewed_through": "3bb6976", "unreviewed_since": None, "disposition": "R2 next"},
    ],
    "triggers": [{"id": "trig_01Bak4xL", "fires_into": S1, "purpose": "45-minute check-in", "next_run": "2026-11-23T06:55Z"}],
    "subscriptions": [319],
    "owner_queue": [{"kind": "todo", "task": "M1-O5", "issue": 291, "text": "approve the privacy text",
                     "then": "unblock testers"}],
    "follow_ups": {"open": 41, "blocker": 0, "major": 0, "minor": 29, "nit": 12},
    "next": ["#319 conflict fix, then a new owner approval", "#331 fix push, then R2"],
    "decisions": [{"comment": 7076085601, "what": "structured state body"}],
}
PROSE = "Living state for the Listicles orchestrator. Process: docs/ORCHESTRATION.md.\n\n## Standing rules\n- keep me\n"


def body(data=STATE, prose=PROSE, after=""):
    return f"{prose}\n```json\n{json.dumps(data, indent=2)}\n```\n{after}"


def changed(path, value, data=STATE):
    """A deep copy of `data` with the dotted `path` set to `value` (or deleted when value is DELETE)."""
    out = copy.deepcopy(data)
    *parents, last = path.split(".")
    node = out
    for part in parents:
        node = node[int(part)] if part.isdigit() else node[part]
    if value is DELETE:
        del node[int(last) if last.isdigit() else last]
    elif last.isdigit():
        node[int(last)] = value
    else:
        node[last] = value
    return out


DELETE = object()


def errors(text):
    try:
        state_body.load(text)
    except state_body.StateError as e:
        return "\n".join(e.errors)
    return ""


def run_cli(*args, stdin=None):
    out, err = io.StringIO(), io.StringIO()
    old = sys.stdin
    try:
        if stdin is not None:
            sys.stdin = io.StringIO(stdin)
        with redirect_stdout(out), redirect_stderr(err):
            code = state_body.main(list(args))
    finally:
        sys.stdin = old
    return code, out.getvalue(), err.getvalue()


class ValidTest(unittest.TestCase):
    def test_sample_state_is_valid(self):
        self.assertEqual(errors(body()), "")
        self.assertEqual(state_body.load(body()), STATE)

    def test_nullable_fields_and_empty_lists(self):
        data = changed("orchestrator.predecessor", None)
        data = changed("sessions", [], data)
        data = changed("triggers", [], data)
        data = changed("owner_queue", [{"kind": "question", "task": None, "issue": None,
                                        "text": "rename the repo?", "then": "ask again in M2"}], data)
        self.assertEqual(errors(body(data)), "")

    def test_optional_note_may_be_missing(self):
        self.assertEqual(errors(body(changed("sessions.0.note", DELETE))), "")

    def test_unicode_line_separators_inside_a_text_value_are_not_line_ends(self):
        # CommonMark ends lines only at \n, \r\n and \r; ensure_ascii=False writes U+2028 and U+0085 raw (R1-01)
        for sep in ("\u2028", "\u0085", "\u2029"):
            with self.subTest(sep=repr(sep)):
                data = changed("next", [f"a{sep}b"])
                text = f"{PROSE}\n```json\n{json.dumps(data, indent=2, ensure_ascii=False)}\n```\n"
                self.assertIn(sep, text)
                self.assertEqual(state_body.load(text), data)

    def test_usage_states_from_the_template(self):
        for state in ("ok", "near limit (5-hour)", "near limit (5-hour, forecast)",
                      "near limit (5-hour, rateLimitType unknown)", "near limit (7-day)", "near limit (overage)",
                      "paused until 07:15 UTC"):
            with self.subTest(state=state):
                self.assertEqual(errors(body(changed("usage.state", state))), "")

    def test_crlf_body_from_the_api_is_read(self):
        self.assertEqual(state_body.load(body().replace("\n", "\r\n")), STATE)


class BlockTest(unittest.TestCase):
    def test_no_block(self):
        self.assertIn("no ```json block", errors(PROSE))

    def test_two_blocks(self):
        self.assertIn("2 ```json blocks", errors(body(after="```json\n{}\n```\n")))

    def test_unterminated_block(self):
        self.assertIn("not closed", errors(f"{PROSE}\n```json\n{json.dumps(STATE)}\n"))

    def test_malformed_json(self):
        self.assertIn("malformed JSON", errors(f"```json\n{json.dumps(STATE)[:-1]}\n```\n"))

    def test_top_level_must_be_an_object(self):
        self.assertIn("must be a JSON object", errors("```json\n[1, 2]\n```\n"))

    def test_duplicate_keys_are_rejected(self):
        self.assertIn("duplicate key 'schema'", errors('```json\n{"schema": 1, "schema": 1}\n```\n'))


class SchemaTest(unittest.TestCase):
    def assert_error(self, data, *needles):
        msg = errors(body(data))
        for needle in needles:
            self.assertIn(needle, msg)

    def test_unknown_fields_fail_at_every_level(self):
        self.assert_error(changed("extra", 1), "unknown field 'extra'")
        self.assert_error(changed("sessions.0.colour", "red"), "sessions[0]: unknown field 'colour'")
        self.assert_error(changed("usage.why", "x"), "usage: unknown field 'why'")

    def test_missing_required_fields_fail_at_every_level(self):
        self.assert_error(changed("next", DELETE), "missing field 'next'")
        self.assert_error(changed("branches.0.reviewed_through", DELETE), "branches[0]: missing field 'reviewed_through'")
        self.assert_error(changed("orchestrator.depth", DELETE), "orchestrator: missing field 'depth'")
        self.assert_error(changed("sessions.0.tags", DELETE), "sessions[0]: missing field 'tags'")

    def test_wrong_types(self):
        self.assert_error(changed("orchestrator.depth", "4"), "orchestrator.depth: expected a whole number")
        self.assert_error(changed("sessions.0.pr", True), "sessions[0].pr: expected a PR or issue number")
        self.assert_error(changed("sessions.0.tasks", "M1-14"), "sessions[0].tasks: expected a list")
        self.assert_error(changed("sessions.0.tags", "pr:319"), "sessions[0].tags: expected a list")
        self.assert_error(changed("subscriptions", [319.0]), "subscriptions[0]: expected a PR or issue number")
        self.assert_error(changed("next", "do it"), "next: expected a list")
        self.assert_error(changed("sessions", {}), "sessions: expected a list")
        self.assert_error(changed("sessions.0", "x"), "sessions[0]: expected an object")
        self.assert_error(changed("updated.after", "  "), "updated.after: expected a non-empty string")
        # a line break would let a text value end the summary or open a second ```json block when rendered
        self.assert_error(changed("next", ["a\n```json"]), "next[0]: expected a non-empty string on one line")

    def test_schema_version(self):
        self.assert_error(changed("schema", 2), "schema: expected 1")

    def test_formats(self):
        self.assert_error(changed("updated.at", "2026-11-23 06:10"), "updated.at: expected a UTC time")
        self.assert_error(changed("updated.at", "2026-13-45T99:99Z"), "updated.at: expected a UTC time")
        self.assert_error(changed("sessions.0.tags", ["pr 319"]), "sessions[0].tags[0]: expected a session tag")
        self.assert_error(changed("orchestrator.session", "sess_1"), "orchestrator.session: expected a session id")
        self.assert_error(changed("sessions.0.tasks", ["m1-14"]), "sessions[0].tasks[0]: expected a task id")
        self.assert_error(changed("branches.0.reviewed_through", "zzz"), "reviewed_through: expected a commit SHA")
        self.assert_error(changed("triggers.0.id", "t_1"), "triggers[0].id: expected a trigger id")
        self.assert_error(changed("usage.state", "fine"), "usage.state: expected one of")
        self.assert_error(changed("usage.state", "paused until 99:99 UTC"), "usage.state: expected one of")
        self.assert_error(changed("updated.at", "\u0662\u0660\u0662\u0666-11-23T05:33Z"), "updated.at: expected a UTC time")
        self.assert_error(changed("sessions.0.tasks", ["M\u0661-14"]), "sessions[0].tasks[0]: expected a task id")
        self.assert_error(changed("branches.0.reviewed_through", "\u0661" * 7), "reviewed_through: expected a commit SHA")
        self.assert_error(changed("sessions.0.status", "parked"), "sessions[0].status: expected one of")
        self.assert_error(changed("owner_queue.0.kind", "chore"), "owner_queue[0].kind: expected one of")
        self.assert_error(changed("sessions.0.role", "Implementer!"), "sessions[0].role: expected a role")

    def test_next_holds_one_to_three_actions(self):
        self.assertEqual(errors(body(changed("next", ["a", "b", "c"]))), "")
        self.assert_error(changed("next", []), "next: expected 1 to 3 items")
        self.assert_error(changed("next", ["a", "b", "c", "d"]), "next: expected 1 to 3 items")

    def test_follow_up_counts_must_add_up(self):
        self.assert_error(changed("follow_ups.open", 40), "follow_ups.open: 40 is not the sum")

    def test_a_task_is_claimed_by_one_session_only(self):
        two = changed("sessions", STATE["sessions"] + [dict(STATE["sessions"][0], id=S0)])
        self.assert_error(two, "M1-14 is claimed by 2 sessions")

    def test_a_task_repeated_inside_one_row_is_named_as_such(self):
        msg = errors(body(changed("sessions.0.tasks", ["M1-14", "M1-14"])))
        self.assertIn("sessions[0]: M1-14 listed twice", msg)
        self.assertNotIn("claimed by", msg)
        msg = errors(body(changed("branches.0.in_review", ["M1-44", "M1-44"])))
        self.assertIn("branches[0]: M1-44 listed twice", msg)

    def test_duplicate_session_ids_and_branch_names(self):
        self.assert_error(changed("sessions", STATE["sessions"] * 2), f"duplicate session {S2}")
        self.assert_error(changed("branches", STATE["branches"] * 2), "duplicate branch tooling/ci-hardening-44")

    def test_an_ended_session_holds_no_claim(self):
        for status in ("archived", "failed"):
            self.assert_error(changed("sessions.0.status", status), f"sessions[0]: {status} but still claims M1-14")
        self.assertEqual(errors(body(changed("sessions.0.tasks", [], changed("sessions.0.status", "archived")))), "")

    def test_every_error_is_reported_not_just_the_first(self):
        data = changed("tasks_ref", "", changed("usage.read_at", "now"))
        msg = errors(body(data))
        self.assertIn("tasks_ref", msg)
        self.assertIn("usage.read_at", msg)


class RenderTest(unittest.TestCase):
    def test_summary_sits_above_the_block_and_prose_is_kept(self):
        out = state_body.render(body())
        self.assertTrue(out.startswith(PROSE.rstrip("\n")))
        self.assertLess(out.index(state_body.BEGIN), out.index(state_body.END))
        self.assertLess(out.index(state_body.END), out.index("```json"))
        self.assertIn("- keep me", out)

    def test_summary_is_short_and_readable(self):
        summary = state_body.summary(STATE)
        for line in (f"**Orchestrator:** `{S1}` since 2026-11-23T05:33Z · predecessor `{S0}` · lineage depth 4",
                     "**Updated:** 2026-11-23T06:10Z, after check-in", "**Tasks ref:** `main`",
                     "**Usage:** ok (read 2026-11-23T05:25Z)",
                     "open follow-ups: 41 (blocker 0, major 0, minor 29, nit 12)",
                     "1. #319 conflict fix, then a new owner approval", "2. #331 fix push, then R2"):
            self.assertIn(line, summary)
        for part in (S2, "M1-14", "running", "M1-O5", "#291", "trig_01Bak4xL", "#319", "3bb6976", "7076085601"):
            self.assertIn(part, summary)
        self.assertLessEqual(len(summary.splitlines()), 40)

    def test_render_round_trips_and_is_idempotent(self):
        once = state_body.render(body())
        self.assertEqual(state_body.load(once), STATE)
        self.assertEqual(state_body.render(once), once)

    def test_render_is_idempotent_when_the_body_ends_without_a_newline_and_with_blank_lines(self):
        for tail in ("", "\n", "\n\n\n"):
            with self.subTest(tail=repr(tail)):
                once = state_body.render(body(after=tail))
                self.assertEqual(state_body.render(once), once)
                self.assertTrue(once.endswith("```\n") and not once.endswith("\n\n"))

    def test_render_keeps_prose_after_the_block_and_is_idempotent(self):
        once = state_body.render(body(after="\n## Notes\n- after the block\n"))
        self.assertIn("## Notes\n- after the block\n", once)
        self.assertEqual(state_body.render(once), once)

    def test_render_handles_crlf_and_cr_line_ends(self):
        for eol in ("\r\n", "\r"):
            with self.subTest(eol=repr(eol)):
                once = state_body.render(body().replace("\n", eol))
                self.assertEqual(state_body.load(once), STATE)
                self.assertEqual(state_body.render(once), once)

    def test_render_refuses_a_summary_below_the_block(self):
        below = body(after=f"{state_body.BEGIN}\nold\n{state_body.END}\n")
        with self.assertRaises(state_body.StateError) as cm:
            state_body.render(below)
        self.assertIn("above the JSON block", "\n".join(cm.exception.errors))

    def test_render_replaces_a_stale_summary(self):
        once = state_body.render(body())
        stale = once.replace("lineage depth 4", "lineage depth 3")
        self.assertEqual(state_body.render(stale), once)

    def test_block_is_compact_one_list_item_per_line(self):
        block = state_body.dump(STATE)
        self.assertIn(f'    {{"id": "{S2}", "role": "implementer"', block)
        self.assertEqual(json.loads(block), STATE)

    def test_render_refuses_an_invalid_body(self):
        with self.assertRaises(state_body.StateError):
            state_body.render(body(changed("extra", 1)))

    def test_one_marker_without_the_other_fails(self):
        once = state_body.render(body())
        self.assertIn("summary markers", errors(once.replace(state_body.END, "")))


class CliTest(unittest.TestCase):
    def write(self, text):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        path = Path(d.name, "state.md")
        path.write_text(text, encoding="utf-8")
        return str(path)

    def test_validate_ok_and_counts(self):
        code, out, _ = run_cli("validate", self.write(body()))
        self.assertEqual((code, out.strip()), (0, "ok: 1 sessions, 1 branches, 1 claimed, 1 in review"))

    def test_validate_failure_exits_1_with_errors_on_stderr(self):
        code, out, err = run_cli("validate", self.write(body(changed("extra", 1))))
        self.assertEqual((code, out), (1, ""))
        self.assertIn("error: unknown field 'extra'", err)

    def test_validate_from_stdin(self):
        self.assertEqual(run_cli("validate", "-", stdin=body())[0], 0)
        code, out, err = run_cli("validate", "-", stdin=PROSE)
        self.assertEqual((code, out), (1, ""))
        self.assertIn("no ```json block", err)

    def test_render_from_stdin(self):
        code, out, _ = run_cli("render", "-", stdin=body())
        self.assertEqual(code, 0)
        self.assertEqual(out, state_body.render(body()))

    def test_render_failure_prints_nothing_on_stdout(self):
        code, out, err = run_cli("render", "-", stdin=PROSE)
        self.assertEqual((code, out), (1, ""))
        self.assertIn("no ```json block", err)

    def test_missing_file_exits_1(self):
        code, _, err = run_cli("validate", "/nonexistent/state.md")
        self.assertEqual(code, 1)
        self.assertIn("cannot read", err)

    def test_a_body_that_is_not_utf8_is_an_error_not_a_traceback(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        path = Path(d.name, "state.md")
        path.write_bytes(b"\xff\xfe```json\n")
        code, _, err = run_cli("validate", str(path))
        self.assertEqual(code, 1)
        self.assertIn(f"error: cannot read {path}: not UTF-8", err)

    def test_empty_input_is_an_error_not_an_empty_state(self):
        code, _, err = run_cli("validate", "-", stdin="")
        self.assertEqual(code, 1)
        self.assertIn("empty", err)


if __name__ == "__main__":
    unittest.main(verbosity=1)
