"""Run: python3 -I -m unittest discover -s scripts/hooks"""

import json
import os
import subprocess
import sys
import tempfile
import unittest

import gitenv  # noqa: F401  (drops GIT_DIR and friends, see gitenv.py)

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


class OutputDir(unittest.TestCase):
    """R9-07: metrics go to the project root, not wherever the hook's cwd happens to be."""

    def run_hook(self, cwd, env=None):
        d = tempfile.mkdtemp()
        tp = os.path.join(d, "s.jsonl")
        open(tp, "w").write(json.dumps(rec("a", 1)) + "\n")
        e = {k: v for k, v in os.environ.items() if k not in ("LISTICLES_METRICS_DIR", "CLAUDE_PROJECT_DIR")}
        e.update(env or {})
        r = subprocess.run([sys.executable, "-I", HOOK], input=json.dumps(
            {"session_id": "s", "transcript_path": tp, "cwd": cwd, "reason": "other"}), env=e, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_project_dir_env_wins_over_cwd(self):
        proj, elsewhere = tempfile.mkdtemp(), tempfile.mkdtemp()
        self.run_hook(elsewhere, {"CLAUDE_PROJECT_DIR": proj})
        self.assertTrue(os.path.exists(os.path.join(proj, "metrics", "sessions", "s.json")))
        self.assertFalse(os.path.exists(os.path.join(elsewhere, "metrics")))

    def test_git_root_of_cwd_without_env(self):
        root = tempfile.mkdtemp()
        subprocess.run(["git", "init", "-q"], cwd=root, check=True)
        sub = os.path.join(root, "app", "src")
        os.makedirs(sub)
        self.run_hook(sub)
        self.assertTrue(os.path.exists(os.path.join(root, "metrics", "sessions", "s.json")))
        self.assertFalse(os.path.exists(os.path.join(sub, "metrics")))

    def test_plain_cwd_when_not_a_repo_and_explicit_dir_wins(self):
        plain, out = tempfile.mkdtemp(), tempfile.mkdtemp()
        self.run_hook(plain)
        self.assertTrue(os.path.exists(os.path.join(plain, "metrics", "sessions", "s.json")))
        self.run_hook(plain, {"LISTICLES_METRICS_DIR": out})
        self.assertTrue(os.path.exists(os.path.join(out, "s.json")))


if __name__ == "__main__":
    unittest.main()
