"""Run: python3 -I -m unittest discover -s scripts/hooks"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import gitenv  # noqa: F401  # justified: imported for its side effect, drops GIT_DIR and friends (see gitenv.py)

HERE = os.path.dirname(os.path.abspath(__file__))
GUARD = os.path.join(HERE, "context_guard.py")
STATUS = os.path.join(HERE, "..", "statusline.sh")
CTX_PREFIXES = ("TALLY_CONTEXT", "LISTICLES_CONTEXT")  # M1-91: renamed outright; tests clear both names from the inherited env


def ctx_env(**extra):
    """os.environ without TALLY_CONTEXT_* and LISTICLES_CONTEXT_*, then extra on top."""
    e = {k: v for k, v in os.environ.items() if not k.startswith(CTX_PREFIXES)}
    e.update(extra)
    return e


class Context(unittest.TestCase):
    def test_statusline_to_hook_roundtrip_warns_once(self):
        tmp = tempfile.mkdtemp()
        env = ctx_env(TMPDIR=tmp)

        def status(pct):
            return subprocess.run(["bash", STATUS], input=json.dumps({"session_id": "s9", "context_window": {"used_percentage": pct},
                "model": {"display_name": "M"}, "workspace": {"current_dir": tmp}}), env=env, capture_output=True, text=True).stdout

        def hook():
            r = subprocess.run([sys.executable, "-I", GUARD], input=json.dumps({"session_id": "s9"}), env=env, capture_output=True, text=True)
            self.assertEqual(r.returncode, 0)
            return r.stdout

        self.assertEqual(hook(), "")  # no data yet
        self.assertIn("ctx 30%", status(30.4))
        self.assertEqual(hook(), "")
        self.assertIn("HANDOFF SOON", status(62.9))
        out = json.loads(hook())
        self.assertIn("62%", out["hookSpecificOutput"]["additionalContext"])
        self.assertEqual(hook(), "")  # only once per stage
        self.assertIn("HANDOFF NOW", status(82.9))
        self.assertIn("82%", json.loads(hook())["hookSpecificOutput"]["additionalContext"])
        self.assertEqual(hook(), "")


def assistant(total_tokens, model="claude-sonnet-5-5", mid="m", sidechain=False):
    """Assistant record whose context size (input + cache) is total_tokens."""
    rec = {"type": "assistant", "uuid": mid, "message": {"id": mid, "model": model, "usage": {
        "input_tokens": 5, "cache_creation_input_tokens": 1000, "cache_read_input_tokens": total_tokens - 1005, "output_tokens": 0}}}
    if sidechain:
        rec["isSidechain"] = True
    return rec


class Headless(unittest.TestCase):
    """R9-04: cloud/headless sessions never run the statusline, so usage must come from the transcript."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()  # empty TMPDIR: no statusline file exists
        self.tp = os.path.join(self.tmp, "t.jsonl")

    def write(self, recs, raw_prefix=""):
        with open(self.tp, "w") as f:
            f.write(raw_prefix)
            for r in recs:
                f.write((r if isinstance(r, str) else json.dumps(r)) + "\n")

    def hook(self, sid="h1", env=None, tp="default"):
        e = ctx_env(TMPDIR=self.tmp, **(env or {}))
        r = subprocess.run([sys.executable, "-I", GUARD], input=json.dumps(
            {"session_id": sid, "transcript_path": self.tp if tp == "default" else tp}), env=e, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout

    def test_warns_once_from_transcript_at_threshold(self):
        w = {"TALLY_CONTEXT_WINDOW": "200000"}
        self.write([assistant(79999)])
        self.assertEqual(self.hook(env=w), "")  # just under 40%
        self.write([assistant(80000, mid="b")])  # exactly 40%: the step-boundary reminder
        out = json.loads(self.hook(env=w))
        self.assertIn("40%", out["hookSpecificOutput"]["additionalContext"])
        self.assertIn("next step boundary", out["hookSpecificOutput"]["additionalContext"])
        self.assertEqual(out["hookSpecificOutput"]["hookEventName"], "PostToolUse")
        self.assertEqual(self.hook(env=w), "")  # once per stage
        self.write([assistant(120000, mid="c")])  # exactly 60%: the hard reminder
        self.assertIn("Do not start new work", self.hook(env=w))
        self.assertEqual(self.hook(env=w), "")
        self.assertNotEqual(self.hook(sid="other", env=w), "")  # other sessions warn separately

    def test_below_threshold_is_silent(self):
        self.write([assistant(79999)])
        self.assertEqual(self.hook(env={"TALLY_CONTEXT_WINDOW": "200000"}), "")

    def test_uses_the_last_main_thread_usage_and_skips_noise(self):
        self.write([assistant(150000, mid="a"), {"type": "user"}, assistant(190000, mid="s", sidechain=True), "not json",
                    assistant(40000, mid="b"), {"type": "assistant", "message": {"id": "x"}}])
        self.assertEqual(self.hook(env={"TALLY_CONTEXT_WINDOW": "200000"}), "")  # last real main record is 20%

    def test_window_and_threshold_come_from_env_or_model(self):
        self.write([assistant(120000)])
        self.assertEqual(self.hook(env={"TALLY_CONTEXT_WINDOW": "1000000"}), "")  # 12%
        self.assertNotEqual(self.hook(sid="w2", env={"TALLY_CONTEXT_THRESHOLD": "30", "TALLY_CONTEXT_WINDOW": "200000"}), "")

    def test_large_transcript_only_tail_is_needed(self):
        self.write([assistant(10000, mid=f"m{i}") for i in range(30000)] + [assistant(150000, mid="last")])
        self.assertGreater(os.path.getsize(self.tp), 4_000_000)
        self.assertIn("75%", self.hook(env={"TALLY_CONTEXT_WINDOW": "200000"}))

    def test_bad_or_missing_transcript_is_silent(self):
        self.assertEqual(self.hook(tp="/nonexistent/x.jsonl"), "")
        self.write([])
        self.assertEqual(self.hook(sid="e"), "")
        r = subprocess.run([sys.executable, "-I", GUARD], input=json.dumps({"session_id": "h2"}), capture_output=True, text=True)
        self.assertEqual((r.returncode, r.stdout), (0, ""))

    # Default window is 1,000,000 (the models used here); a 200k default fired the reminder at ~100k tokens.
    def test_default_window_is_1m_so_120k_does_not_warn(self):
        for model in ("claude-sonnet-5-5", "claude-opus-5-5[1m]", ""):
            self.write([assistant(120000, model=model)])
            self.assertEqual(self.hook(sid="d" + model[-4:]), "", model)

    def test_1m_window_has_a_step_boundary_reminder_at_60_and_a_hard_one_at_80(self):
        self.write([assistant(599999)])
        self.assertEqual(self.hook(sid="d1"), "")
        self.write([assistant(600000, mid="b")])
        soft = json.loads(self.hook(sid="d1"))["hookSpecificOutput"]["additionalContext"]
        self.assertIn("60%", soft)
        self.assertIn("next step boundary", soft)
        self.assertNotIn("Do not start new work", soft)
        self.assertEqual(self.hook(sid="d1"), "")
        self.write([assistant(799999, mid="c")])
        self.assertEqual(self.hook(sid="d1"), "")  # still the soft stage, already given
        self.write([assistant(800000, mid="d")])
        hard = json.loads(self.hook(sid="d1"))["hookSpecificOutput"]["additionalContext"]
        self.assertIn("80%", hard)
        self.assertIn("Do not start new work", hard)
        self.assertEqual(self.hook(sid="d1"), "")

    def test_200k_window_has_its_own_40_and_60_percent_stages(self):
        w = {"TALLY_CONTEXT_WINDOW": "200000"}
        self.write([assistant(79999)])
        self.assertEqual(self.hook(sid="e1", env=w), "")
        self.write([assistant(80000, mid="b")])
        self.assertIn("40%", self.hook(sid="e1", env=w))
        self.write([assistant(119999, mid="c")])
        self.assertEqual(self.hook(sid="e1", env=w), "")
        self.write([assistant(120000, mid="d")])
        self.assertIn("Do not start new work", self.hook(sid="e1", env=w))

    def test_window_of_exactly_200k_is_small_and_one_token_more_is_large(self):
        self.write([assistant(130000)])  # 65% of either window
        small = self.hook(sid="m1", env={"TALLY_CONTEXT_WINDOW": "200000"})
        large = self.hook(sid="m2", env={"TALLY_CONTEXT_WINDOW": "200001"})
        self.assertIn("Do not start new work", small)  # 65% >= 60%
        self.assertIn("next step boundary", large)  # 65% is between 60% and 80%
        self.assertNotIn("Do not start new work", large)

    def test_a_jump_past_the_hard_threshold_gives_only_the_hard_reminder_and_no_later_soft_one(self):
        self.write([assistant(900000)])
        self.assertIn("Do not start new work", self.hook(sid="j1"))
        self.assertEqual(self.hook(sid="j1"), "")

    def test_threshold_env_overrides_the_hard_stage_and_drops_the_soft_one(self):
        self.write([assistant(600000)])
        self.assertEqual(self.hook(sid="o1", env={"TALLY_CONTEXT_THRESHOLD": "70"}), "")  # no soft stage at 60%
        self.write([assistant(700000, mid="b")])
        self.assertIn("70%", self.hook(sid="o1", env={"TALLY_CONTEXT_THRESHOLD": "70"}))

    def test_context_window_in_hook_input_is_ignored(self):
        """R10-55: PostToolUse input never carries context_window (statusline JSON only); do not trust an invented shape."""
        self.write([assistant(250000)])
        data = {"session_id": "i1", "transcript_path": self.tp, "context_window": {"context_window_size": 400000}}
        e = ctx_env(TMPDIR=self.tmp)
        out = subprocess.run([sys.executable, "-I", GUARD], input=json.dumps(data), env=e, capture_output=True, text=True).stdout
        self.assertEqual(out, "")  # 250k of the default 1M window is 25%

    def test_subagent_tool_calls_neither_warn_nor_use_up_the_reminder(self):
        """R10-51: PostToolUse also fires inside subagents; the main session must still get its one reminder."""
        self.write([assistant(600000)])
        e = ctx_env(TMPDIR=self.tmp)

        def run(extra):
            data = dict({"session_id": "a1", "transcript_path": self.tp}, **extra)
            return subprocess.run([sys.executable, "-I", GUARD], input=json.dumps(data), env=e, capture_output=True, text=True).stdout

        self.assertEqual(run({"agent_id": "sub-1", "agent_type": "explorer"}), "")
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "tally-ctx", "a1.warned")))
        self.assertIn("60%", run({}))  # the main thread still gets it
        self.assertEqual(run({}), "")  # and only once
        self.assertEqual(run({"agent_id": ""}), "")  # empty agent_id counts as main thread (already warned)

    def test_trailing_sidechain_record_is_skipped(self):
        """R10-56: the last record is a sidechain one above the threshold; the earlier main record is below it."""
        self.write([assistant(100000, mid="main"), assistant(900000, mid="side", sidechain=True)])
        self.assertEqual(self.hook(), "")

    def test_non_ascii_digits_are_garbage_not_a_crash(self):
        """R10-59: '²'.isdigit() is True but int('²') raises."""
        self.write([assistant(600000)])
        for bad in ("\u00b2", "\u0663"):
            r = subprocess.run([sys.executable, "-I", GUARD], input=json.dumps({"session_id": "u" + str(ord(bad)), "transcript_path": self.tp}),
                               env=ctx_env(TMPDIR=self.tmp, TALLY_CONTEXT_THRESHOLD=bad, TALLY_CONTEXT_WINDOW=bad),
                               capture_output=True, text=True)
            self.assertEqual(r.stderr, "", bad)
            self.assertIn("60%", r.stdout, bad)  # both fall back to the 1M defaults (soft stage at 60%)

    def test_garbage_window_env_falls_back_to_1m(self):
        self.write([assistant(600000)])
        for i, bad in enumerate(("abc", "0", "-5", "1.5")):
            self.assertIn("60%", self.hook(sid=f"g{i}", env={"TALLY_CONTEXT_WINDOW": bad}), bad)

    def test_garbage_threshold_env_falls_back_to_the_window_defaults(self):
        self.write([assistant(600000)])
        self.assertIn("next step boundary", self.hook(sid="t1", env={"TALLY_CONTEXT_THRESHOLD": "abc"}))  # 60% of 1M: soft stage

    def test_statusline_threshold_follows_env(self):
        env = ctx_env(TMPDIR=self.tmp, TALLY_CONTEXT_THRESHOLD="80")
        out = subprocess.run(["bash", STATUS], input=json.dumps({"session_id": "s1", "context_window": {"used_percentage": 60}}),
                             env=env, capture_output=True, text=True).stdout
        self.assertNotIn("HANDOFF", out)

    def status(self, pct, thr=None, window=None, env_window=None):
        env = ctx_env(TMPDIR=self.tmp)
        if thr is not None:
            env["TALLY_CONTEXT_THRESHOLD"] = thr
        if env_window is not None:
            env["TALLY_CONTEXT_WINDOW"] = env_window
        cw = {"used_percentage": pct}
        if window is not None:
            cw["context_window_size"] = window
        return subprocess.run(["bash", STATUS], input=json.dumps({"session_id": "s2", "context_window": cw}), env=env,
                              capture_output=True, text=True).stdout

    def test_statusline_default_1m_stages(self):
        self.assertNotIn("HANDOFF", self.status(59))
        self.assertIn("HANDOFF SOON", self.status(60))
        self.assertIn("HANDOFF SOON", self.status(79))
        self.assertIn("HANDOFF NOW", self.status(80))

    def test_statusline_200k_stages_come_from_the_window_size_in_its_input(self):
        self.assertNotIn("HANDOFF", self.status(39, window=200000))
        self.assertIn("HANDOFF SOON", self.status(40, window=200000))
        self.assertIn("HANDOFF SOON", self.status(59, window=200000))
        self.assertIn("HANDOFF NOW", self.status(60, window=200000))
        self.assertNotIn("HANDOFF", self.status(59, window=1000000))  # the same 59% on a 1M window is quiet

    def test_statusline_falls_back_to_the_window_env_then_to_1m(self):
        self.assertIn("HANDOFF NOW", self.status(60, env_window="200000"))
        self.assertIn("HANDOFF SOON", self.status(60, env_window="garbage"))
        self.assertIn("HANDOFF SOON", self.status(60, window="abc"))  # a garbage window size in the input counts as unknown

    # R1-01 (#126 review): the statusline knows the real window; it records it next to the % and the hook uses it.
    def record(self, pct, window, sid="r1"):
        """Run the statusline for session `sid` (window=None: the status JSON has no context_window_size) in self.tmp."""
        cw = {"used_percentage": pct}
        if window is not None:
            cw["context_window_size"] = window
        env = ctx_env(TMPDIR=self.tmp)
        return subprocess.run(["bash", STATUS], input=json.dumps({"session_id": sid, "context_window": cw}), env=env,
                              capture_output=True, text=True).stdout

    def test_a_200k_session_at_65_percent_gets_the_hard_reminder_like_its_status_line_says(self):
        self.assertIn("HANDOFF NOW", self.record(65, 200000))
        out = self.hook(sid="r1")  # no TALLY_CONTEXT_WINDOW: the recorded window is used
        self.assertIn("Do not start new work", out)
        self.assertIn("65%", out)

    def test_the_recorded_window_beats_the_env_window(self):
        self.record(45, 200000)  # 45% of a 200k window is past the 40% soft stage
        self.assertIn("next step boundary", self.hook(sid="r1", env={"TALLY_CONTEXT_WINDOW": "1000000"}))

    def test_the_recorded_window_sizes_the_transcript_percentage_too(self):
        self.record(10, 200000)  # the statusline % is low; the transcript says 130k tokens = 65% of 200k (13% of 1M)
        self.write([assistant(130000)])
        self.assertIn("Do not start new work", self.hook(sid="r1"))

    def test_without_a_recorded_window_the_env_then_1m_still_apply(self):
        self.assertNotIn("HANDOFF", self.record(50, None))  # 50% of the 1M default: quiet
        self.assertEqual(self.hook(sid="r1"), "")
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "tally-ctx", "r1.window")))
        self.record(45, None, sid="r2")
        self.assertIn("next step boundary", self.hook(sid="r2", env={"TALLY_CONTEXT_WINDOW": "200000"}))

    def test_a_garbage_window_is_neither_recorded_nor_used(self):
        for bad in ("abc", 0, -5, 1.5):
            self.record(45, bad, sid="r3")
            self.assertFalse(os.path.exists(os.path.join(self.tmp, "tally-ctx", "r3.window")), bad)
        base = os.path.join(self.tmp, "tally-ctx")
        for i, junk in enumerate(("abc", "0", "-5", "\u00b2", "")):
            with open(os.path.join(base, f"r4{i}.window"), "w") as f:
                f.write(junk)
            with open(os.path.join(base, f"r4{i}"), "w") as f:
                f.write("45")
            self.assertEqual(self.hook(sid=f"r4{i}"), "", repr(junk))  # 45% of the 1M default: quiet, no crash

    # R2-01 (#126 review): a window recorded earlier must not outlive a status JSON that no longer carries one.
    def test_a_stale_window_file_is_removed_when_the_status_json_has_no_valid_window(self):
        path = os.path.join(self.tmp, "tally-ctx", "r5.window")
        for later in (None, "abc", 0):
            self.record(65, 200000, sid="r5")
            self.assertTrue(os.path.exists(path))
            self.record(45, later, sid="r5")
            self.assertFalse(os.path.exists(path), later)
            self.assertEqual(self.hook(sid="r5"), "", later)  # 45% of the 1M default is quiet, not 45% of a stale 200k

    def test_a_valid_window_stays_recorded_and_is_replaced_by_a_newer_one(self):
        path = os.path.join(self.tmp, "tally-ctx", "r6.window")
        self.record(65, 200000, sid="r6")
        self.record(66, 200000, sid="r6")
        self.assertEqual(Path(path).read_text(), "200000")
        self.record(66, 1000000, sid="r6")
        self.assertEqual(Path(path).read_text(), "1000000")
        self.record(10, None, sid="r7")  # removing a window file that was never there is not an error
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "tally-ctx", "r7.window")))

    def test_the_recorded_window_stays_per_session(self):
        self.record(65, 200000, sid="ra")
        self.record(65, 1000000, sid="rb")
        self.assertIn("Do not start new work", self.hook(sid="ra"))
        self.assertIn("next step boundary", self.hook(sid="rb"))

    def test_statusline_threshold_env_is_a_single_stage(self):
        self.assertNotIn("HANDOFF", self.status(79, thr="80"))
        self.assertIn("HANDOFF NOW", self.status(80, thr="80"))
        for bad in ("abc", "0", "-1", ""):
            self.assertIn("HANDOFF SOON", self.status(60, thr=bad), bad)  # garbage falls back to the window defaults
            self.assertNotIn("HANDOFF", self.status(40, thr=bad), bad)


class Names(unittest.TestCase):
    """M1-91: TALLY_CONTEXT_WINDOW and TALLY_CONTEXT_THRESHOLD replace the LISTICLES_* names outright, and the hook and the status
    line share $TMPDIR/tally-ctx."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.tp = os.path.join(self.tmp, "t.jsonl")
        with open(self.tp, "w") as f:
            f.write(json.dumps(assistant(130000)) + "\n")  # 65% of a 200k window, 13% of the 1M default

    def hook(self, sid, **env):
        r = subprocess.run([sys.executable, "-I", GUARD], input=json.dumps({"session_id": sid, "transcript_path": self.tp}),
                           env=ctx_env(TMPDIR=self.tmp, **env), capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout

    def status(self, pct, sid="n1", **env):
        return subprocess.run(["bash", STATUS], input=json.dumps({"session_id": sid, "context_window": {"used_percentage": pct}}),
                              env=ctx_env(TMPDIR=self.tmp, **env), capture_output=True, text=True).stdout

    def test_hook_reads_the_tally_names(self):
        self.assertIn("Do not start new work", self.hook("a1", TALLY_CONTEXT_WINDOW="200000"))
        self.assertIn("Do not start new work", self.hook("a2", TALLY_CONTEXT_THRESHOLD="10"))

    def test_hook_ignores_the_listicles_names(self):
        self.assertEqual(self.hook("b1", LISTICLES_CONTEXT_WINDOW="200000"), "")
        self.assertEqual(self.hook("b2", LISTICLES_CONTEXT_THRESHOLD="10"), "")
        self.assertEqual(self.hook("b3", LISTICLES_CONTEXT_WINDOW="200000", TALLY_CONTEXT_WINDOW="1000000"), "")

    def test_statusline_reads_the_tally_names_and_ignores_the_listicles_ones(self):
        self.assertIn("HANDOFF NOW", self.status(65, TALLY_CONTEXT_WINDOW="200000"))
        self.assertIn("HANDOFF NOW", self.status(20, TALLY_CONTEXT_THRESHOLD="10"))
        self.assertNotIn("HANDOFF", self.status(50, LISTICLES_CONTEXT_WINDOW="200000"))
        self.assertNotIn("HANDOFF", self.status(20, LISTICLES_CONTEXT_THRESHOLD="10"))

    def test_shared_dir_is_tally_ctx(self):
        self.status(70, sid="c1")
        self.assertEqual(Path(self.tmp, "tally-ctx", "c1").read_text(), "70")
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "listicles-ctx")))
        os.makedirs(os.path.join(self.tmp, "listicles-ctx"))
        Path(self.tmp, "listicles-ctx", "c2").write_text("90")  # a file at the old place is not read
        r = subprocess.run([sys.executable, "-I", GUARD], input=json.dumps({"session_id": "c2"}), env=ctx_env(TMPDIR=self.tmp),
                           capture_output=True, text=True)
        self.assertEqual((r.returncode, r.stdout), (0, ""))
        r = subprocess.run([sys.executable, "-I", GUARD], input=json.dumps({"session_id": "c1"}), env=ctx_env(TMPDIR=self.tmp),
                           capture_output=True, text=True)
        self.assertIn("70%", r.stdout)  # the hook reads what the status line wrote


if __name__ == "__main__":
    unittest.main()
