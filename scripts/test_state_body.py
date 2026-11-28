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
PROSE = "Living state for the Tally orchestrator. Process: docs/ORCHESTRATION.md.\n\n## Standing rules\n- keep me\n"


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
    def test_prose_mirrors_the_template_first_line(self):  # M1-92: the fixture and docs/orchestrator-state.md say the same name
        template = (Path(__file__).resolve().parent.parent / "docs" / "orchestrator-state.md").read_text(encoding="utf-8")
        self.assertIn(PROSE.splitlines()[0], template)

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
        self.assert_error(changed("branches.0.disposition", DELETE), "branches[0]: missing field 'disposition'")
        self.assert_error(changed("orchestrator.depth", DELETE), "orchestrator: missing field 'depth'")
        self.assert_error(changed("sessions.0.expects", DELETE), "sessions[0]: missing field 'expects'")

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

    def test_task_ids_take_two_or_three_digits(self):
        for ok in ("M1-99", "M1-100", "M1-999", "M1-O2", "M1-FU", "M0.5-100"):
            self.assertEqual(errors(body(changed("sessions.0.tasks", [ok]))), "", ok)
        for bad in ("M1-1", "M1-1000", "M1-0100", "M1-ABC", "M1-10x", "M1-\u0661\u0660\u0660", "M1-100\n"):
            self.assert_error(changed("sessions.0.tasks", [bad]), "sessions[0].tasks[0]: expected a task id")

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
        for part in ("M1-O5", "#291", "#331", "3bb6976", "1 running"):
            self.assertIn(part, summary)  # a running session is a count, not a row (M1-120)
        self.assertNotIn(S2, summary)
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


def full(data):
    """The state with every optional row field spelled out (what a body had to carry before M1-120)."""
    out = copy.deepcopy(data)
    for row in out["sessions"]:
        for k, v in (("tags", []), ("branch", None), ("pr", None), ("tasks", [])):
            row.setdefault(k, v)
    for row in out["branches"]:
        for k, v in (("pr", None), ("in_review", []), ("reviewed_through", None), ("unreviewed_since", None)):
            row.setdefault(k, v)
    return out


def session_row(i, role="implementer", branch=None, **extra):
    return {"id": f"session_01{role[:3].title()}{i:02d}", "role": role, "spawned": "2026-11-24T15:47Z", "expects": "WR",
            "checked": "2026-11-24T18:04Z", "status": "running", **({"branch": branch} if branch else {}), **extra}


def lean_state(sessions=15, branches=11):
    """About #399's shape: implementers on branches, a few reviewers, a merge agent; most optional fields empty."""
    data = copy.deepcopy(STATE)
    rows = [session_row(i, branch=f"m1/task-{i}", pr=300 + i, status="idle-with-result" if i % 4 == 0 else "running",
                        **({"tasks": [f"M1-{40 + i}"]} if i % 3 == 0 else {})) for i in range(branches)]
    rows += [session_row(i, "reviewer", f"m1/task-{i}", pr=300 + i) for i in range(sessions - branches - 1)]
    rows.append(session_row(0, "merge-agent"))
    data["sessions"] = rows
    data["branches"] = [{"name": f"m1/task-{i}", "pr": 300 + i, "disposition": f"R{i}; owner",
                         **({"in_review": [f"M1-{40 + i}"], "reviewed_through": "abc1234"} if i % 2 else {})} for i in range(branches)]
    return data


class LeanTest(unittest.TestCase):
    """M1-120 (owner decision 7140391316 item 3): a leaner body at the same 15000-byte limit."""

    def test_optional_row_fields_may_be_omitted_and_load_fills_them(self):
        s, b = session_row(1), {"name": "m1/x", "disposition": "implementing"}
        data = changed("branches", [b], changed("sessions", [s]))
        self.assertEqual(errors(body(data)), "")
        got = state_body.load(body(data))
        self.assertEqual({k: got["sessions"][0][k] for k in ("tags", "branch", "pr", "tasks")}, {"tags": [], "branch": None, "pr": None, "tasks": []})
        self.assertEqual({k: got["branches"][0][k] for k in ("pr", "in_review", "reviewed_through", "unreviewed_since")},
                         {"pr": None, "in_review": [], "reviewed_through": None, "unreviewed_since": None})

    def test_the_meaning_stays_required(self):
        for key in ("id", "role", "spawned", "expects", "checked", "status"):
            with self.subTest(key=key):
                self.assertIn(f"sessions[0]: missing field '{key}'", errors(body(changed("sessions", [{k: v for k, v in session_row(1).items() if k != key}]))))
        for key in ("name", "disposition"):
            with self.subTest(key=key):
                row = {k: v for k, v in {"name": "m1/x", "disposition": "d"}.items() if k != key}
                self.assertIn(f"branches[0]: missing field '{key}'", errors(body(changed("branches", [row]))))

    def test_an_omitted_field_with_a_bad_value_still_fails_when_present(self):
        self.assertIn("sessions[0].tasks: expected a list", errors(body(changed("sessions", [session_row(1, tasks="M1-14")]))))
        self.assertIn("branches[0].in_review[0]: expected a task id",
                      errors(body(changed("branches", [{"name": "b", "disposition": "d", "in_review": ["x"]}]))))
        self.assertIn("unknown field 'holders'", errors(body(changed("branches", [{"name": "b", "disposition": "d", "holders": 1}]))))

    def test_an_omitted_holder_is_the_one_implementer_on_the_branch(self):
        data = changed("branches", [{"name": "m1/x", "disposition": "d"}],
                       changed("sessions", [session_row(1, branch="m1/x"), session_row(2, "reviewer", "m1/x")]))
        self.assertEqual(state_body.load(body(data))["branches"][0]["holder"], session_row(1)["id"])

    def test_an_omitted_holder_with_no_or_two_implementers(self):
        none = changed("branches", [{"name": "m1/x", "disposition": "d"}], changed("sessions", [session_row(2, "reviewer", "m1/x")]))
        self.assertIsNone(state_body.load(body(none))["branches"][0]["holder"])
        two = changed("branches", [{"name": "m1/x", "disposition": "d"}],
                      changed("sessions", [session_row(1, branch="m1/x"), session_row(2, branch="m1/x")]))
        self.assertIn("branches[0].holder: 2 implementer sessions on m1/x; name the holder", errors(body(two)))

    def test_an_explicit_holder_or_null_wins_over_the_derived_one(self):
        sessions = [session_row(1, branch="m1/x"), session_row(2, branch="m1/x")]
        named = changed("branches", [{"name": "m1/x", "holder": session_row(2)["id"], "disposition": "d"}], changed("sessions", sessions))
        self.assertEqual(state_body.load(body(named))["branches"][0]["holder"], session_row(2)["id"])
        null = changed("branches", [{"name": "m1/x", "holder": None, "disposition": "d"}], changed("sessions", sessions[:1]))
        self.assertIsNone(state_body.load(body(null))["branches"][0]["holder"])

    def test_render_writes_the_canonical_lean_block(self):
        data = full(lean_state())
        for b in data["branches"]:
            b["holder"] = f"session_01Imp{int(b['name'].split('-')[1]):02d}"
        out = state_body.render(body(data))
        block = out[out.index("```json"):]
        for gone in ('"tags": []', '"branch": null', '"pr": null', '"tasks": []', '"in_review": []', '"reviewed_through": null',
                     '"unreviewed_since": null', '"holder"'):
            self.assertNotIn(gone, block)
        self.assertEqual(state_body.load(out), state_body.load(body(data)))
        self.assertEqual(state_body.render(out), out)

    def test_render_keeps_an_explicit_null_holder_when_one_would_be_derived(self):
        data = changed("branches", [{"name": "m1/x", "holder": None, "disposition": "d"}], changed("sessions", [session_row(1, branch="m1/x")]))
        out = state_body.render(body(data))
        self.assertIn('"holder": null', out)
        self.assertIsNone(state_body.load(out)["branches"][0]["holder"])

    def test_the_summary_counts_running_sessions_and_lists_the_others(self):
        summary = state_body.summary(state_body.load(body(lean_state())))
        self.assertIn("**Sessions** (15): 12 running, 3 idle-with-result", summary)
        for sid in ("session_01Imp00", "session_01Imp04", "session_01Imp08"):
            self.assertIn(sid, summary)
        for sid in ("session_01Imp01", "session_01Rev00", "session_01Mer00"):
            self.assertNotIn(sid, summary)

    def test_the_summary_has_one_line_per_branch_without_the_holder(self):
        data = lean_state()
        summary = state_body.summary(state_body.load(body(data)))
        rows = [ln for ln in summary.splitlines() if ln.startswith("- `m1/task-")]
        self.assertEqual(len(rows), 11)
        self.assertIn("- `m1/task-1` PR #301, in review M1-41, reviewed through `abc1234`: R1; owner", rows[1])
        self.assertNotIn("holder", "\n".join(rows))

    def test_the_summary_keeps_the_owner_queue_and_counts_triggers_and_decisions(self):
        summary = state_body.summary(STATE)
        self.assertIn("M1-O5 #291: approve the privacy text; then unblock testers", summary)
        self.assertIn("**Scheduled tasks:** 1, next 2026-11-23T06:55Z", summary)
        self.assertIn("**Standing owner decisions:** 1 (comment ids in the block)", summary)

    def test_a_body_with_a_live_load_stays_well_under_the_limit(self):
        data = lean_state()
        lean = len(state_body.render(body(data)).encode("utf-8"))
        old = len(state_body.render(body(full(data))).encode("utf-8"))
        self.assertEqual(lean, old, "render is canonical: a spelled-out body renders to the same bytes")
        self.assertLess(lean, 7000)  # the same shape was about 13 KB before M1-120 (the PR body has the numbers)


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


class RotationTest(unittest.TestCase):
    """M1-78, owner decision #15 7076313976: validate reports when the state issue passes about 250 comments or a body of about 15 KB, so the
    orchestrator rotates at the next handover boundary. A report is not an error: the body stays valid (exit 0)."""

    def validate(self, text, *flags):
        return run_cli("validate", *flags, "-", stdin=text)

    def padded(self, size):
        """A valid body of exactly `size` UTF-8 bytes (multi-byte prose, so bytes and characters differ)."""
        short = body()
        pad = size - len(short.encode("utf-8"))
        self.assertGreaterEqual(pad, 0)
        text = body(prose=PROSE + "æ" * (pad // 2) + "x" * (pad % 2))  # æ is two bytes in UTF-8
        self.assertEqual(len(text.encode("utf-8")), size)
        return text

    def test_below_both_limits_prints_no_rotation_line(self):
        code, out, err = self.validate(self.padded(state_body.BODY_LIMIT - 1), "--comments", str(state_body.COMMENT_LIMIT - 1))
        self.assertEqual((code, err), (0, ""))
        self.assertNotIn("rotate", out)

    def test_the_body_limit_is_counted_in_utf8_bytes(self):
        self.assertEqual(state_body.BODY_LIMIT, 15000)
        code, out, _ = self.validate(self.padded(state_body.BODY_LIMIT))
        self.assertEqual(code, 0)
        self.assertIn(f"rotate: the body is {state_body.BODY_LIMIT} bytes (limit {state_body.BODY_LIMIT})", out)
        self.assertIn("at the next handover boundary", out)
        self.assertLess(len(self.padded(state_body.BODY_LIMIT)), state_body.BODY_LIMIT, "the multi-byte prose must count as bytes, not characters")

    def test_the_comment_limit(self):
        self.assertEqual(state_body.COMMENT_LIMIT, 250)
        code, out, _ = self.validate(body(), "--comments", "250")
        self.assertEqual(code, 0)
        self.assertIn("rotate: the issue has 250 comments (limit 250)", out)
        self.assertNotIn("rotate", self.validate(body(), "--comments", "249")[1])

    def test_both_limits_passed_gives_two_lines_after_the_ok_line(self):
        code, out, _ = self.validate(self.padded(state_body.BODY_LIMIT + 1), "--comments", "570")
        lines = out.splitlines()
        self.assertEqual(code, 0)
        self.assertTrue(lines[0].startswith("ok: "), out)
        self.assertEqual([ln.split(":")[0] for ln in lines[1:]], ["rotate", "rotate"], out)

    def test_without_comments_only_the_body_is_checked(self):
        code, out, _ = self.validate(body())
        self.assertEqual((code, out.strip()), (0, "ok: 1 sessions, 1 branches, 1 claimed, 1 in review"))

    def test_a_bad_comment_count_is_a_usage_error(self):
        for bad in ("-1", "x", "", "2.5", "1e3", "\u0663"):  # \u0663 is an Arabic-Indic digit, which int() would read as 3
            with self.subTest(bad=bad), self.assertRaises(SystemExit) as cm, redirect_stderr(io.StringIO()):
                state_body.main(["validate", "--comments", bad, "-"])
            self.assertEqual(cm.exception.code, 2)

    def test_an_invalid_body_reports_its_errors_and_no_rotation(self):
        code, out, err = self.validate(body(changed("extra", 1)), "--comments", "999")
        self.assertEqual((code, out), (1, ""))
        self.assertIn("unknown field", err)

    def test_crlf_line_ends_count_as_two_bytes_from_a_file_and_from_stdin(self):  # bodies saved in the web UI carry CRLF; reading must not drop the CR
        text = self.padded(state_body.BODY_LIMIT - 1).replace("\n", "\r\n")
        size = len(text.encode("utf-8"))
        self.assertGreaterEqual(size, state_body.BODY_LIMIT, "the CRLF form must pass the limit for this test to mean anything")
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        path = Path(d.name, "state.md")
        path.write_bytes(text.encode("utf-8"))
        code, out, _ = run_cli("validate", str(path))
        self.assertEqual(code, 0)
        self.assertIn(f"rotate: the body is {size} bytes", out)
        old = sys.stdin
        try:
            sys.stdin = io.TextIOWrapper(io.BytesIO(text.encode("utf-8")), encoding="utf-8")  # the real stdin translates newlines too
            out = io.StringIO()
            with redirect_stdout(out), redirect_stderr(io.StringIO()):
                self.assertEqual(state_body.main(["validate", "-"]), 0)
        finally:
            sys.stdin = old
        self.assertIn(f"rotate: the body is {size} bytes", out.getvalue())

    def test_render_takes_no_comment_count(self):
        with self.assertRaises(SystemExit) as cm, redirect_stderr(io.StringIO()):
            state_body.main(["render", "--comments", "3", "-"])
        self.assertEqual(cm.exception.code, 2)


if __name__ == "__main__":
    unittest.main(verbosity=1)
