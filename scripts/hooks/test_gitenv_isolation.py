"""R11-51: pushing from a linked worktree makes git export GIT_DIR to the pre-push hook, and the hook runs these tests.
Tests that create repos must never touch the enclosing one. Each case points GIT_DIR at a sentinel repo and proves the sentinel
is unchanged. Run: python3 -I -m unittest discover -s scripts/hooks"""

import os
import subprocess
import sys
import tempfile
import unittest

import gitenv  # noqa: F401  (drops GIT_DIR and friends, see gitenv.py)

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
SUITES = ("test_prepush_hook.py", "test_prepush_scope.py", "test_guards_sh.py", "test_pretooluse_guard.py", "test_session_end_metrics.py")


def git(cwd, *args, env=None):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, env=env, check=True).stdout


def sentinel():
    d = tempfile.mkdtemp(prefix="sentinel-")
    git(d, "init", "-q", "-b", "work")
    git(d, "-c", "user.name=s", "-c", "user.email=s@s", "commit", "-q", "--allow-empty", "-m", "sentinel")
    return d


def snapshot(d):
    return (git(d, "rev-parse", "HEAD"), git(d, "log", "--oneline"), git(d, "config", "--local", "--list"))


class GitEnvIsolation(unittest.TestCase):
    def test_suites_never_touch_the_repo_named_by_git_dir(self):
        s = sentinel()
        before = snapshot(s)
        env = dict(os.environ, GIT_DIR=os.path.join(s, ".git"))
        for suite in SUITES:
            r = subprocess.run([sys.executable, "-I", "-m", "unittest", "discover", "-s", HERE, "-p", suite], cwd=ROOT, env=env,
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, suite + r.stderr[-600:])
            self.assertEqual(snapshot(s), before, f"{suite} modified the repository named by GIT_DIR")

    def test_suites_pass_under_a_hostile_global_git_config(self):
        """R12-52: signing, hooks or identity in the developer's global/system config must not matter to fixture repos."""
        cfg = os.path.join(tempfile.mkdtemp(), "hostile.cfg")
        with open(cfg, "w") as f:
            f.write("[commit]\n\tgpgsign = true\n[gpg]\n\tprogram = false\n[core]\n\thooksPath = /nonexistent\n")
        env = dict(os.environ, GIT_CONFIG_GLOBAL=cfg)
        for suite in ("test_prepush_hook.py", "test_guards_sh.py"):
            r = subprocess.run([sys.executable, "-I", "-m", "unittest", "discover", "-s", HERE, "-p", suite], cwd=ROOT, env=env,
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, suite + r.stderr[-600:])

    def test_leak_detection_works(self):
        """Negative case: a process that really inherits GIT_DIR does change the sentinel, so the check above can fail."""
        s = sentinel()
        before = snapshot(s)
        t = tempfile.mkdtemp()
        subprocess.run(["git", "config", "leak.probe", "1"], cwd=t, env=dict(os.environ, GIT_DIR=os.path.join(s, ".git")), check=True)
        self.assertNotEqual(snapshot(s), before)


if __name__ == "__main__":
    unittest.main()
