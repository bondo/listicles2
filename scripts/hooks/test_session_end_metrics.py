"""Run: python3 -I -m unittest discover -s scripts/hooks"""

import json
import os
import subprocess
import sys
import tempfile
import unittest

HOOK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "session_end_metrics.py")


def rec(mid, out, model="m1"):
    return {"type": "assistant", "uuid": "u" + str(out), "message": {"id": mid, "model": model, "usage": {
        "input_tokens": 2, "output_tokens": out, "cache_creation_input_tokens": 10, "cache_read_input_tokens": 100}}}


class Metrics(unittest.TestCase):
    def test_dedupes_by_message_id_and_sums_subagents(self):
        d = tempfile.mkdtemp()
        tp = os.path.join(d, "s1.jsonl")
        with open(tp, "w") as f:
            for r in [rec("a", 5), rec("a", 50), rec("b", 7, "m2"), {"type": "user"}]:
                f.write(json.dumps(r) + "\n")
            f.write("not json\n")
        os.makedirs(os.path.join(d, "s1", "subagents"))
        with open(os.path.join(d, "s1", "subagents", "x.jsonl"), "w") as f:
            f.write(json.dumps(rec("c", 9)) + "\n")
        out = os.path.join(d, "out")
        env = dict(os.environ, LISTICLES_METRICS_DIR=out, LISTICLES_ROLE="implementer")
        r = subprocess.run([sys.executable, "-I", HOOK], input=json.dumps(
            {"session_id": "s1", "transcript_path": tp, "cwd": d, "reason": "other"}), env=env, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        j = json.load(open(os.path.join(out, "s1.json")))
        self.assertEqual(j["main"]["messages"], 2)
        self.assertEqual(j["main"]["total"]["output_tokens"], 57)
        self.assertEqual(j["main"]["total"]["cache_read_input_tokens"], 200)
        self.assertEqual(j["main"]["by_model"]["m2"]["output_tokens"], 7)
        self.assertEqual(j["subagents"]["total"]["output_tokens"], 9)
        self.assertEqual(j["role"], "implementer")

    def test_bad_input_never_fails(self):
        r = subprocess.run([sys.executable, "-I", HOOK], input="x", capture_output=True, text=True)
        self.assertEqual(r.returncode, 0)


if __name__ == "__main__":
    unittest.main()
