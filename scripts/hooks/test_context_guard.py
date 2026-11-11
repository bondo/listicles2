"""Run: python3 -I -m unittest discover -s scripts/hooks"""

import json
import os
import subprocess
import sys
import tempfile
import unittest

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
        self.write([assistant(80000)])
        self.assertEqual(self.hook(), "")  # 40%
        self.write([assistant(80000), assistant(100000, mid="b")])  # exactly 50%
        out = json.loads(self.hook())
        self.assertIn("50%", out["hookSpecificOutput"]["additionalContext"])
        self.assertEqual(out["hookSpecificOutput"]["hookEventName"], "PostToolUse")
        self.assertEqual(self.hook(), "")  # only once per session
        self.assertNotEqual(self.hook(sid="other"), "")  # other sessions warn separately

    def test_below_threshold_is_silent(self):
        self.write([assistant(99999)])
        self.assertEqual(self.hook(), "")

    def test_uses_the_last_main_thread_usage_and_skips_noise(self):
        self.write([assistant(150000, mid="a"), {"type": "user"}, assistant(190000, mid="s", sidechain=True), "not json",
                    assistant(40000, mid="b"), {"type": "assistant", "message": {"id": "x"}}])
        self.assertEqual(self.hook(), "")  # last real main record is 20%

    def test_window_and_threshold_come_from_env_or_model(self):
        self.write([assistant(120000)])
        self.assertEqual(self.hook(env={"LISTICLES_CONTEXT_WINDOW": "1000000"}), "")  # 12%
        self.assertNotEqual(self.hook(sid="w2", env={"LISTICLES_CONTEXT_THRESHOLD": "30"}), "")
        self.write([assistant(120000, model="claude-opus-5-5[1m]")])
        self.assertEqual(self.hook(sid="w3"), "")  # [1m] models have a 1M window

    def test_large_transcript_only_tail_is_needed(self):
        self.write([assistant(10000, mid=f"m{i}") for i in range(30000)] + [assistant(150000, mid="last")])
        self.assertGreater(os.path.getsize(self.tp), 4_000_000)
        self.assertIn("75%", self.hook())

    def test_bad_or_missing_transcript_is_silent(self):
        self.assertEqual(self.hook(tp="/nonexistent/x.jsonl"), "")
        self.write([])
        self.assertEqual(self.hook(sid="e"), "")
        r = subprocess.run([sys.executable, "-I", GUARD], input=json.dumps({"session_id": "h2"}), capture_output=True, text=True)
        self.assertEqual((r.returncode, r.stdout), (0, ""))

    def test_statusline_threshold_follows_env(self):
        env = dict(os.environ, TMPDIR=self.tmp, LISTICLES_CONTEXT_THRESHOLD="80")
        out = subprocess.run(["bash", STATUS], input=json.dumps({"session_id": "s1", "context_window": {"used_percentage": 60}}),
                             env=env, capture_output=True, text=True).stdout
        self.assertNotIn("HANDOFF", out)


if __name__ == "__main__":
    unittest.main()
