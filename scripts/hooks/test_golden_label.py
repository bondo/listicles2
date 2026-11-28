"""M1-126 (owner decision #399 comment 7239508302 item 2): on pre-push, guards.sh allows changed screenshot references when the open
PR whose head is the pushed branch of this repo carries the `golden-update` label, as CI does from the label (ci.yml guards job).
scripts/hooks/golden_label.py makes that decision; guards.sh calls it only with --pre-push and only when GOLDEN_UPDATE is not 1.
Fail closed: no PR, more than one, a gh error, an unparsable answer, a branch or repository that does not match exactly all refuse.
gh is a stub on PATH that records its argv and environment and prints a canned answer. Run: python3 -I scripts/hooks/run_hook_tests.py"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

import gitenv  # noqa: F401  # justified: imported for its side effect, drops GIT_DIR and friends (see gitenv.py)
from test_guards_sh import Repo

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
ZERO = "0" * 40
URL = "https://github.com/o/r.git"
GH_STUB = f"""#!{sys.executable}
import json, os, sys
d = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(d, "calls"), "a") as f:
    f.write(json.dumps({{"argv": sys.argv[1:], "env": dict(os.environ)}}) + "\\n")
with open(os.path.join(d, "out")) as f:
    sys.stdout.write(f.read())
with open(os.path.join(d, "rc")) as f:
    sys.exit(int(f.read()))
"""


def pr(number=7, ref="work", head_repo="o/r", base_repo="o/r", labels=("golden-update",), state="open"):
    return {"number": number, "state": state, "labels": [{"name": n} for n in labels],
            "head": {"ref": ref, "repo": {"full_name": head_repo}}, "base": {"ref": "main", "repo": {"full_name": base_repo}}}


class GoldenRepo(Repo):
    """A guards test repo with the helper and repo_slug.py beside guards.sh (untracked), origin = o/r, branch `work`, a stub gh."""

    def __init__(self):
        super().__init__()
        os.makedirs(os.path.join(self.dir, "scripts", "hooks"))
        shutil.copy(os.path.join(HERE, "golden_label.py"), os.path.join(self.dir, "scripts", "hooks", "golden_label.py"))
        shutil.copy(os.path.join(ROOT, "scripts", "repo_slug.py"), os.path.join(self.dir, "scripts", "repo_slug.py"))
        with open(os.path.join(self.dir, ".git", "info", "exclude"), "a") as f:
            f.write("/scripts/hooks/\n/scripts/repo_slug.py\n")
        self.git("remote", "add", "origin", URL)
        self.bin = tempfile.mkdtemp(prefix="golden-gh-")
        path = os.path.join(self.bin, "gh")
        with open(path, "w") as f:
            f.write(GH_STUB)
        os.chmod(path, 0o755)
        self.answer([pr()])

    def answer(self, body, rc=0):
        with open(os.path.join(self.bin, "out"), "w") as f:
            f.write(body if isinstance(body, str) else json.dumps(body))
        with open(os.path.join(self.bin, "rc"), "w") as f:
            f.write(str(rc))

    def calls(self):
        try:
            with open(os.path.join(self.bin, "calls")) as f:
                return [json.loads(line) for line in f]
        except FileNotFoundError:
            return []

    def head(self):
        return self.git("rev-parse", "HEAD").strip()

    def push_line(self):
        return f"refs/heads/work {self.head()} refs/heads/work {ZERO}\n"

    def prepush(self, stdin=None, args=("--pre-push", URL), **env):
        e = {k: v for k, v in os.environ.items() if k not in ("CI", "GUARD_BASE", "GOLDEN_UPDATE", "GUARD_MAX_DIFF")}
        e["PATH"] = self.bin + os.pathsep + e.get("PATH", "")
        e.update(env)
        r = subprocess.run(["bash", "scripts/guards.sh", *args], cwd=self.dir, capture_output=True, text=True, env=e,
                           input=self.push_line() if stdin is None else stdin)
        return r.returncode, r.stdout + r.stderr

    def cleanup(self):
        super().cleanup()
        shutil.rmtree(self.bin, ignore_errors=True)


class Case(unittest.TestCase):
    def setUp(self):
        self.repo = GoldenRepo()
        self.addCleanup(self.repo.cleanup)
        self.repo.write("app/src/test/snapshots/a.png", "png1")
        self.repo.commit()

    def allowed(self, **kw):
        rc, out = self.repo.prepush(**kw)
        self.assertEqual(rc, 0, out)
        self.assertIn("guards: ok", out)
        return out

    def refused(self, reason, gh_called=True, **kw):
        before = len(self.repo.calls())
        rc, out = self.repo.prepush(**kw)
        self.assertNotEqual(rc, 0, out)
        self.assertIn("screenshot references changed without the golden-update label", out)
        self.assertIn(reason, out)
        self.assertEqual(len(self.repo.calls()) > before, gh_called, out)
        return out


class LabelAllows(Case):
    def test_labelled_pr_of_the_pushed_branch_allows_the_goldens(self):
        out = self.allowed()
        self.assertIn("golden-update label on PR #7", out)
        (call,) = self.repo.calls()
        self.assertEqual(call["argv"], ["api", "--hostname", "github.com", "-X", "GET", "repos/o/r/pulls",
                                        "-f", "state=open", "-f", "head=o:work", "-f", "per_page=100"])

    def test_other_labels_beside_it_do_not_matter(self):
        self.repo.answer([pr(labels=("big-pr", "golden-update", "x"))])
        self.allowed()

    def test_golden_update_env_still_allows_without_asking_gh(self):
        self.repo.answer([pr(labels=())])
        self.allowed(GOLDEN_UPDATE="1")
        self.assertEqual(self.repo.calls(), [])

    def test_no_changed_golden_never_asks_gh(self):
        self.repo.git("update-ref", "refs/remotes/origin/main", "HEAD")
        self.repo.answer("not json", rc=1)
        self.allowed()
        self.assertEqual(self.repo.calls(), [])

    def test_ci_env_does_not_change_the_pre_push_answer(self):
        self.allowed(CI="true")
        self.repo.answer([pr(labels=())])
        self.refused("has no golden-update label", CI="true")


class LabelRefuses(Case):
    def test_pr_without_the_label_refuses(self):
        for labels in ((), ("golden-updates",), ("Golden-Update",), ("golden-update ",), ("big-pr",)):
            with self.subTest(labels=labels):
                self.repo.answer([pr(labels=labels)])
                self.refused("PR #7 has no golden-update label")

    def test_no_open_pr_refuses(self):
        self.repo.answer([])
        self.refused("no open PR")

    def test_more_than_one_pr_refuses(self):
        self.repo.answer([pr(), pr(number=8)])
        self.refused("2 open PRs")

    def test_gh_error_refuses(self):
        for rc in (1, 4, 127):
            with self.subTest(rc=rc):
                self.repo.answer(json.dumps([pr()]), rc=rc)
                self.refused("gh api failed")

    def test_unparsable_answers_refuse(self):
        bad = ["", "not json", "{}", '"x"', "null", json.dumps([pr()])[:-1], json.dumps({"items": [pr()]}), "[1]", "[[]]",
               json.dumps([dict(pr(), labels="golden-update")]), json.dumps([dict(pr(), labels=["golden-update"])]),
               json.dumps([dict(pr(), labels=[{"name": 1}])]), json.dumps([{k: v for k, v in pr().items() if k != "head"}]),
               json.dumps([dict(pr(), head={"ref": "work"})]), json.dumps([dict(pr(), head={"ref": "work", "repo": None})]),
               json.dumps([dict(pr(), number="7")]), json.dumps([{k: v for k, v in pr().items() if k != "labels"}])]
        for body in bad:
            with self.subTest(body=body):
                self.repo.answer(body)
                self.refused("golden_label:")

    def test_another_branch_or_repository_on_the_pr_refuses(self):
        for kw in ({"ref": "work2"}, {"ref": "Work"}, {"ref": "work "}, {"ref": "feature/work"}, {"head_repo": "fork/r"},
                   {"head_repo": "o/r2"}, {"base_repo": "x/r"}, {"state": "closed"}):
            with self.subTest(**kw):
                self.repo.answer([pr(**kw)])
                self.refused("golden_label:")


class PushInputRefuses(Case):
    """The pushed ref must be exactly the checked-out branch at HEAD, pushed to the same name; anything else never asks gh."""

    def test_bad_push_input_refuses_without_asking_gh(self):
        head = self.repo.head()
        other = self.repo.git("rev-parse", "HEAD~1").strip()
        for stdin in ["", "\n", "garbage\n", f"refs/heads/work {head} refs/heads/work\n",
                      f"refs/heads/work {head} refs/heads/work {ZERO} extra\n",
                      f"refs/heads/work {head} refs/heads/work {ZERO}\nrefs/heads/x {head} refs/heads/x {ZERO}\n",
                      f"refs/heads/work {head} refs/heads/other {ZERO}\n", f"refs/heads/work {head} refs/heads/Work {ZERO}\n",
                      f"refs/heads/work {head} refs/tags/work {ZERO}\n", f"refs/tags/v1 {head} refs/tags/v1 {ZERO}\n",
                      f"refs/heads/other {head} refs/heads/other {ZERO}\n", f"refs/heads/work {other} refs/heads/work {ZERO}\n",
                      f"(delete) {ZERO} refs/heads/work {head}\n", f"refs/heads/work {ZERO} refs/heads/work {head}\n",
                      f"HEAD {head} refs/heads/work {ZERO}\n", f"refs/heads/work {head[:12]} refs/heads/work {ZERO}\n"]:
            with self.subTest(stdin=stdin):
                self.refused("golden_label:", gh_called=False, stdin=stdin)

    def test_detached_head_refuses(self):
        self.repo.git("checkout", "-q", "--detach")
        self.refused("golden_label:", gh_called=False)

    def test_push_url_of_another_repository_refuses(self):
        for url in ("https://github.com/x/r.git", "https://github.com/o/r2", "https://example.com/o/r.git", "", "/tmp/r.git"):
            with self.subTest(url=url):
                self.refused("golden_label:", gh_called=False, args=("--pre-push", url))

    def test_missing_push_url_refuses(self):
        self.refused("golden_label:", gh_called=False, args=("--pre-push",))

    def test_origin_of_another_host_refuses(self):
        self.repo.git("remote", "set-url", "origin", "https://example.com/o/r.git")
        self.refused("golden_label:", gh_called=False)


class OnlyPrePushAsks(Case):
    def test_without_pre_push_the_label_is_never_read(self):
        """CI keeps its env input: a plain guards.sh run refuses without GOLDEN_UPDATE=1 and never runs gh."""
        rc, out = self.repo.prepush(args=())
        self.assertNotEqual(rc, 0, out)
        self.assertIn("screenshot references changed without the golden-update label", out)
        self.assertEqual(self.repo.calls(), [])

    def test_staged_mode_never_asks_gh(self):
        self.repo.prepush(args=("--staged",))
        self.assertEqual(self.repo.calls(), [])


class EnvironmentCannotSteer(Case):
    """Only GOLDEN_UPDATE changes the result: variables that pick gh's repository or host, or this checkout's slug, are dropped."""

    STEER = {"GH_REPO": "x/y", "GH_HOST": "example.com", "GITHUB_REPOSITORY": "x/y", "GH_ENTERPRISE_TOKEN": "t",
             "GITHUB_ENTERPRISE_TOKEN": "t", "GH_DEBUG": "api", "GH_PAGER": "cat", "GH_FORCE_TTY": "1", "CLICOLOR_FORCE": "1"}

    def test_steering_variables_do_not_reach_gh(self):
        self.allowed(**self.STEER)
        (call,) = self.repo.calls()
        self.assertIn("repos/o/r/pulls", call["argv"])
        self.assertIn("head=o:work", call["argv"])
        for k in self.STEER:
            self.assertNotIn(k, call["env"])

    def test_steering_variables_do_not_turn_a_refusal_into_an_allow(self):
        self.repo.answer([pr(labels=())])
        self.refused("has no golden-update label", **self.STEER, GOLDEN_LABEL="1", GUARD_GOLDEN_LABEL="1")
        self.repo.answer([])
        self.refused("no open PR", **self.STEER)


if __name__ == "__main__":
    unittest.main()
