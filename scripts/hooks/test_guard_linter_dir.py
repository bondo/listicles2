"""The allow rules run whatever sits in .tools/bin/, so non-tooling sessions must not write there, nor edit the installer or its pins."""

import unittest

from test_pretooluse_guard import TOOLING, repo, run

PROTECTED_PATHS = [".tools/bin/shellcheck", ".tools/bin/actionlint", ".tools/bin/zizmor", ".tools/x", "scripts/install_linters.sh",
                   "scripts/linters.pins", "sub/../.tools/bin/shellcheck", ".tools"]
WRITES = ["echo x > {p}", "cp /tmp/x {p}", "tee {p} < /tmp/x", "sed -i s/a/b/ {p}", "ln -sf /tmp/x {p}", "mv /tmp/x {p}", "rm -f {p}"]


class LinterDir(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = repo()

    def test_writes_denied_for_non_tooling_sessions(self):
        for p in PROTECTED_PATHS:
            for tool in ("Write", "Edit"):
                self.assertEqual(run(tool, {"file_path": p}, self.d), 2, (tool, p))
            for w in WRITES:
                self.assertEqual(run("Bash", {"command": w.format(p=p)}, self.d), 2, w.format(p=p))

    def test_tooling_sessions_may_write(self):
        for p in PROTECTED_PATHS:
            self.assertEqual(run("Write", {"file_path": p}, self.d, TOOLING), 0, p)
        self.assertEqual(run("Bash", {"command": "echo x > .tools/bin/shellcheck"}, self.d, TOOLING), 0)

    def test_reading_and_running_stay_allowed(self):
        for c in ["cat scripts/linters.pins", "cat scripts/install_linters.sh", "ls .tools/bin", "scripts/install_linters.sh",
                  "bash scripts/install_linters.sh", ".tools/bin/shellcheck scripts/verify.sh", ".tools/bin/actionlint",
                  ".tools/bin/zizmor --offline .github/workflows", "git add scripts/other.sh", "echo x > scripts/other.sh",
                  "cp a docs/tools.md", "echo x > .toolsx/a"]:
            self.assertEqual(run("Bash", {"command": c}, self.d), 0, c)
        self.assertEqual(run("Write", {"file_path": "scripts/other.sh"}, self.d), 0)
        self.assertEqual(run("Read", {"file_path": ".tools/bin/shellcheck"}, self.d), 0)


if __name__ == "__main__":
    unittest.main()
