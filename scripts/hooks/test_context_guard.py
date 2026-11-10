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


if __name__ == "__main__":
    unittest.main()
