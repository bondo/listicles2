"""Run: python3 -I -m unittest discover -s scripts/hooks"""

import json
import os
import subprocess
import sys
import tempfile
import unittest

import gitenv  # noqa: F401  (drops GIT_DIR and friends, see gitenv.py)

HERE = os.path.dirname(os.path.abspath(__file__))
GUARD = os.path.join(HERE, "context_guard.py")
STATUS = os.path.join(HERE, "..", "statusline.sh")


class Context(unittest.TestCase):
    def test_statusline_to_hook_roundtrip_warns_once(self):
        tmp = tempfile.mkdtemp()
        env = dict(os.environ, TMPDIR=tmp)

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
        self.assertIn("HANDOFF NOW", status(52.9))
        out = json.loads(hook())
        self.assertIn("52%", out["hookSpecificOutput"]["additionalContext"])
        self.assertEqual(hook(), "")  # only once


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
        e = dict(os.environ, TMPDIR=self.tmp, **(env or {}))
        for k in ("LISTICLES_CONTEXT_THRESHOLD", "LISTICLES_CONTEXT_WINDOW"):
            if k not in (env or {}):
                e.pop(k, None)
        r = subprocess.run([sys.executable, "-I", GUARD], input=json.dumps(
            {"session_id": sid, "transcript_path": self.tp if tp == "default" else tp}), env=e, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout

    def test_warns_once_from_transcript_at_threshold(self):
        w = {"LISTICLES_CONTEXT_WINDOW": "200000"}
        self.write([assistant(80000)])
        self.assertEqual(self.hook(env=w), "")  # 40%
        self.write([assistant(80000), assistant(100000, mid="b")])  # exactly 50%
        out = json.loads(self.hook(env=w))
        self.assertIn("50%", out["hookSpecificOutput"]["additionalContext"])
        self.assertEqual(out["hookSpecificOutput"]["hookEventName"], "PostToolUse")
        self.assertEqual(self.hook(env=w), "")  # only once per session
        self.assertNotEqual(self.hook(sid="other", env=w), "")  # other sessions warn separately

    def test_below_threshold_is_silent(self):
        self.write([assistant(99999)])
        self.assertEqual(self.hook(env={"LISTICLES_CONTEXT_WINDOW": "200000"}), "")

    def test_uses_the_last_main_thread_usage_and_skips_noise(self):
        self.write([assistant(150000, mid="a"), {"type": "user"}, assistant(190000, mid="s", sidechain=True), "not json",
                    assistant(40000, mid="b"), {"type": "assistant", "message": {"id": "x"}}])
        self.assertEqual(self.hook(env={"LISTICLES_CONTEXT_WINDOW": "200000"}), "")  # last real main record is 20%

    def test_window_and_threshold_come_from_env_or_model(self):
        self.write([assistant(120000)])
        self.assertEqual(self.hook(env={"LISTICLES_CONTEXT_WINDOW": "1000000"}), "")  # 12%
        self.assertNotEqual(self.hook(sid="w2", env={"LISTICLES_CONTEXT_THRESHOLD": "30", "LISTICLES_CONTEXT_WINDOW": "200000"}), "")

    def test_large_transcript_only_tail_is_needed(self):
        self.write([assistant(10000, mid=f"m{i}") for i in range(30000)] + [assistant(150000, mid="last")])
        self.assertGreater(os.path.getsize(self.tp), 4_000_000)
        self.assertIn("75%", self.hook(env={"LISTICLES_CONTEXT_WINDOW": "200000"}))

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

    def test_default_window_warns_at_500k(self):
        self.write([assistant(499999)])
        self.assertEqual(self.hook(sid="d1"), "")
        self.write([assistant(500000, mid="b")])
        self.assertIn("50%", json.loads(self.hook(sid="d1"))["hookSpecificOutput"]["additionalContext"])

    def test_200k_window_still_warns_at_its_own_50_percent(self):
        w = {"LISTICLES_CONTEXT_WINDOW": "200000"}
        self.write([assistant(99999)])
        self.assertEqual(self.hook(sid="e1", env=w), "")
        self.write([assistant(100000, mid="b")])
        self.assertIn("50%", self.hook(sid="e1", env=w))

    def test_context_window_in_hook_input_is_ignored(self):
        """R10-55: PostToolUse input never carries context_window (statusline JSON only); do not trust an invented shape."""
        self.write([assistant(250000)])
        data = {"session_id": "i1", "transcript_path": self.tp, "context_window": {"context_window_size": 400000}}
        e = {k: v for k, v in os.environ.items() if not k.startswith("LISTICLES_CONTEXT")}
        e.update(TMPDIR=self.tmp)
        out = subprocess.run([sys.executable, "-I", GUARD], input=json.dumps(data), env=e, capture_output=True, text=True).stdout
        self.assertEqual(out, "")  # 250k of the default 1M window is 25%

    def test_subagent_tool_calls_neither_warn_nor_use_up_the_reminder(self):
        """R10-51: PostToolUse also fires inside subagents; the main session must still get its one reminder."""
        self.write([assistant(600000)])
        e = dict(os.environ, TMPDIR=self.tmp)
        e.pop("LISTICLES_CONTEXT_WINDOW", None)
        e.pop("LISTICLES_CONTEXT_THRESHOLD", None)

        def run(extra):
            data = dict({"session_id": "a1", "transcript_path": self.tp}, **extra)
            return subprocess.run([sys.executable, "-I", GUARD], input=json.dumps(data), env=e, capture_output=True, text=True).stdout

        self.assertEqual(run({"agent_id": "sub-1", "agent_type": "explorer"}), "")
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "listicles-ctx", "a1.warned")))
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
                               env=dict(os.environ, TMPDIR=self.tmp, LISTICLES_CONTEXT_THRESHOLD=bad, LISTICLES_CONTEXT_WINDOW=bad),
                               capture_output=True, text=True)
            self.assertEqual(r.stderr, "", bad)
            self.assertIn("60%", r.stdout, bad)  # both fall back to 50% of 1M

    def test_garbage_window_env_falls_back_to_1m(self):
        self.write([assistant(600000)])
        for i, bad in enumerate(("abc", "0", "-5", "1.5")):
            self.assertIn("60%", self.hook(sid=f"g{i}", env={"LISTICLES_CONTEXT_WINDOW": bad}), bad)

    def test_garbage_threshold_env_falls_back_to_50(self):
        self.write([assistant(600000)])
        self.assertIn("60%", self.hook(sid="t1", env={"LISTICLES_CONTEXT_THRESHOLD": "abc"}))

    def test_statusline_threshold_follows_env(self):
        env = dict(os.environ, TMPDIR=self.tmp, LISTICLES_CONTEXT_THRESHOLD="80")
        out = subprocess.run(["bash", STATUS], input=json.dumps({"session_id": "s1", "context_window": {"used_percentage": 60}}),
                             env=env, capture_output=True, text=True).stdout
        self.assertNotIn("HANDOFF", out)

    def test_statusline_threshold_boundaries_and_garbage(self):
        def status(pct, thr):
            env = {k: v for k, v in os.environ.items() if not k.startswith("LISTICLES_CONTEXT")}
            env.update(TMPDIR=self.tmp, **({"LISTICLES_CONTEXT_THRESHOLD": thr} if thr is not None else {}))
            return subprocess.run(["bash", STATUS], input=json.dumps({"session_id": "s2", "context_window": {"used_percentage": pct}}),
                                  env=env, capture_output=True, text=True).stdout

        self.assertNotIn("HANDOFF", status(49, None))
        self.assertIn("HANDOFF NOW", status(50, None))
        self.assertNotIn("HANDOFF", status(79, "80"))
        self.assertIn("HANDOFF NOW", status(80, "80"))
        for bad in ("abc", "0", "-1", ""):
            self.assertIn("HANDOFF NOW", status(60, bad), bad)  # garbage falls back to 50
            self.assertNotIn("HANDOFF", status(40, bad), bad)


if __name__ == "__main__":
    unittest.main()
