"""R12-52: signing, hooks or identity in the developer's global/system config must not matter to fixture repos.
Split from test_gitenv_isolation.py (issue 229) so the parallel hook runner can run the two slow halves side by side.
Run: python3 -I -m unittest discover -s scripts/hooks"""

import os
import tempfile
import unittest

import gitenv  # noqa: F401  # justified: imported for its side effect, drops GIT_DIR and friends (see gitenv.py)
from test_gitenv_isolation import run_suites


class HostileGitConfig(unittest.TestCase):
    def test_suites_pass_under_a_hostile_global_git_config(self):
        """The same suites pass with commit signing, a failing gpg program and a bad hooksPath in the global config."""
        cfg = os.path.join(tempfile.mkdtemp(), "hostile.cfg")
        with open(cfg, "w") as f:
            f.write("[commit]\n\tgpgsign = true\n[gpg]\n\tprogram = false\n[core]\n\thooksPath = /nonexistent\n")
        env = dict(os.environ, GIT_CONFIG_GLOBAL=cfg)
        for suite, r in run_suites(("test_prepush_hook.py", "test_precommit_hook.py", "test_guards_sh.py"), env).items():
            self.assertEqual(r.returncode, 0, suite + r.stderr[-600:])


if __name__ == "__main__":
    unittest.main()
