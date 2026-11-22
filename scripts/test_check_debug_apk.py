"""Tests for scripts/check_debug_apk.py, the wiring of the debug APK artifact in ci.yml (M1-63, #15 comment 7081546814).

Run: python3 -I scripts/test_check_debug_apk.py

The check runs on the real files first, then on copies with one defect each, which must each be reported. The upload must be one
frozen step that only a push to main runs; a pull request must never publish an APK, and the workflow keeps `contents: read`.
"""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_debug_apk as c  # noqa: E402  # justified: must follow the sys.path insert above

ROOT = Path(__file__).resolve().parent.parent
CI = ".github/workflows/ci.yml"
VERIFY = "scripts/verify.sh"
README = "README.md"
PUSH_MAIN = "github.event_name == 'push' && github.ref == 'refs/heads/main'"
PINNED_UPLOAD = "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a"


def is_upload(step):
    return str(step.get("uses", "")).startswith("actions/upload-artifact@")


class Wiring(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        for name in (CI, VERIFY, README):
            (self.root / name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(ROOT / name, self.root / name)

    def edit_ci(self, change):
        """Load the copied ci.yml, apply `change(workflow)`, write it back, and report the problems."""
        path = self.root / CI
        workflow = yaml.safe_load(path.read_text())
        change(workflow)
        path.write_text(yaml.safe_dump(workflow, sort_keys=False, width=10000))
        return c.problems(self.root)

    def edit_text(self, name, old, new, count=1):
        path = self.root / name
        text = path.read_text()
        self.assertIn(old, text, f"{name} no longer contains {old!r}: update the test")
        path.write_text(text.replace(old, new, count))
        return c.problems(self.root)

    def steps(self, workflow, job="unit"):
        return workflow["jobs"][job]["steps"]

    def upload(self, workflow):
        return next(s for s in self.steps(workflow) if is_upload(s))

    def test_the_repository_wiring_is_complete(self):
        self.assertEqual(c.problems(ROOT), [])

    def test_the_upload_step_is_what_the_owner_asked_for(self):
        # The positive reading of the request: unit job, push to main only, name tally-debug-<short sha>, 30 days, error when no file.
        ci = yaml.safe_load((ROOT / CI).read_text())
        step = self.upload(ci)
        self.assertEqual(step["if"], PUSH_MAIN)
        self.assertEqual(step["uses"], PINNED_UPLOAD)
        self.assertEqual(step["with"]["name"], "tally-debug-${{ steps.sha.outputs.short }}")
        self.assertEqual(step["with"]["retention-days"], 30)
        self.assertEqual(step["with"]["if-no-files-found"], "error")
        self.assertEqual(step["with"]["path"], "app/build/outputs/apk/debug/*.apk")
        self.assertNotIn("pull_request", step["if"])

    def test_the_upload_step_is_one_frozen_mapping(self):
        def drop_if(w):
            del self.upload(w)["if"]

        def set_key(key, value):
            def change(w):
                self.upload(w)[key] = value

            return change

        def set_with(key, value):
            def change(w):
                self.upload(w)["with"][key] = value

            return change

        def drop_with(key):
            def change(w):
                del self.upload(w)["with"][key]

            return change

        def remove(w):
            self.steps(w).remove(self.upload(w))

        def twice(w):
            self.steps(w).append(dict(self.upload(w)))

        mutations = {
            "no if (runs on pull requests too)": drop_if,
            "pull_request only": set_key("if", "github.event_name == 'pull_request'"),
            "any push": set_key("if", "github.event_name == 'push'"),
            "main ref only": set_key("if", "github.ref == 'refs/heads/main'"),
            "push or main": set_key("if", "github.event_name == 'push' || github.ref == 'refs/heads/main'"),
            "always": set_key("if", "always()"),
            "failure": set_key("if", "failure()"),
            "negated pull_request": set_key("if", "github.event_name != 'pull_request'"),
            "another branch": set_key("if", "github.event_name == 'push' && github.ref == 'refs/heads/dev'"),
            "continue-on-error": set_key("continue-on-error", True),
            "unpinned action": set_key("uses", "actions/upload-artifact@v7"),
            "another sha": set_key("uses", "actions/upload-artifact@" + "0" * 40),
            "another action": set_key("uses", "actions/cache@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a"),
            "name without the sha": set_with("name", "tally-debug"),
            "name latest": set_with("name", "tally-debug-latest"),
            "name with the full sha": set_with("name", "tally-debug-${{ github.sha }}"),
            "name renamed": set_with("name", "tally-${{ steps.sha.outputs.short }}"),
            "retention 90": set_with("retention-days", 90),
            "retention 31": set_with("retention-days", 31),
            "retention as text": set_with("retention-days", "30"),
            "no retention (the 90 day default)": drop_with("retention-days"),
            "missing files only warn": set_with("if-no-files-found", "warn"),
            "missing files ignored": set_with("if-no-files-found", "ignore"),
            "no if-no-files-found (warns)": drop_with("if-no-files-found"),
            "path is the whole build dir": set_with("path", "app/build"),
            "path is every apk": set_with("path", "app/build/outputs/apk/**/*.apk"),
            "path is the release apk": set_with("path", "app/build/outputs/apk/release/*.apk"),
            "hidden files included": set_with("include-hidden-files", True),
            "overwrite": set_with("overwrite", True),
            "step removed": remove,
            "two upload steps": twice,
        }
        for name, change in mutations.items():
            with self.subTest(name):
                shutil.copy(ROOT / CI, self.root / CI)
                self.assertEqual(self.edit_ci(change), [c.UPLOAD_PROBLEM])

    def test_the_upload_comes_after_the_build_and_the_sha_step(self):
        def upload_first(w):
            steps = self.steps(w)
            up = self.upload(w)
            steps.remove(up)
            steps.insert(0, up)

        def build_after(w):
            steps = self.steps(w)
            build = next(s for s in steps if ":app:assembleDebug" in str(s.get("run", "")))
            steps.remove(build)
            steps.append(build)

        for name, change in (("upload before everything", upload_first), ("build after the upload", build_after)):
            with self.subTest(name):
                shutil.copy(ROOT / CI, self.root / CI)
                self.assertEqual(self.edit_ci(change), [c.ORDER_PROBLEM])

    def test_the_apk_is_built_by_the_unit_job_step_that_runs_assembleDebug(self):
        def no_build(w):
            for s in self.steps(w):
                if ":app:assembleDebug" in str(s.get("run", "")):
                    s["run"] = s["run"].replace(":app:assembleDebug", ":app:assembleRelease")

        self.assertEqual(self.edit_ci(no_build), [c.ORDER_PROBLEM])

    def test_the_short_sha_step_is_frozen(self):
        def sha(w):
            return next(s for s in self.steps(w) if s.get("id") == "sha")

        def remove(w):
            self.steps(w).remove(sha(w))

        def set_key(key, value):
            def change(w):
                sha(w)[key] = value

            return change

        mutations = {
            "removed": remove,
            "no id": set_key("id", "other"),
            "full sha": set_key("run", 'echo "short=${GITHUB_SHA}" >> "$GITHUB_OUTPUT"'),
            "inline expression": set_key("run", 'echo "short=${{ github.sha }}" >> "$GITHUB_OUTPUT"'),
            "wrong output name": set_key("run", 'echo "sha=${GITHUB_SHA::7}" >> "$GITHUB_OUTPUT"'),
            "gated": set_key("if", PUSH_MAIN),
            "continue-on-error": set_key("continue-on-error", True),
            "env": set_key("env", {"GITHUB_SHA": "abcdef1234"}),
        }
        for name, change in mutations.items():
            with self.subTest(name):
                shutil.copy(ROOT / CI, self.root / CI)
                self.assertEqual(self.edit_ci(change), [c.SHA_PROBLEM])

    def test_the_short_sha_step_makes_seven_characters_and_nothing_else(self):
        ci = yaml.safe_load((ROOT / CI).read_text())
        step = next(s for s in self.steps(ci) if s.get("id") == "sha")
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp, "output")
            sha = "0123456789abcdef0123456789abcdef01234567"
            env = {"PATH": os.environ["PATH"], "GITHUB_SHA": sha, "GITHUB_OUTPUT": str(out)}
            subprocess.run(["bash", "-e", "-c", step["run"]], env=env, check=True, capture_output=True)
            self.assertEqual(out.read_text(), "short=0123456\n")

    def test_no_other_job_publishes_an_artifact(self):
        # An upload in any job other than unit (the APK) or the screenshots job (diffs when a step failed) would run on pull requests.
        def add_to(job):
            def change(w):
                self.steps(w, job).append({"uses": PINNED_UPLOAD, "with": {"name": "x", "path": "app/build"}})

            return change

        for job in ("static", "guards", "tasks", "firebase"):
            with self.subTest(job):
                shutil.copy(ROOT / CI, self.root / CI)
                self.assertEqual(self.edit_ci(add_to(job)), [c.ELSEWHERE_PROBLEM])

    def test_a_second_upload_in_the_screenshots_job_is_flagged(self):
        def change(w):
            self.steps(w, "screenshots").append({"uses": PINNED_UPLOAD, "with": {"name": "x", "path": "app/build"}})

        self.assertIn(c.ELSEWHERE_PROBLEM, self.edit_ci(change))

    def test_the_screenshots_job_upload_may_stay_as_it_is(self):
        ci = yaml.safe_load((ROOT / CI).read_text())
        uploads = [s for s in self.steps(ci, "screenshots") if is_upload(s)]
        self.assertEqual(len(uploads), 1)
        self.assertEqual(uploads[0]["if"], "failure()")
        self.assertEqual(c.problems(ROOT), [])

    def test_the_workflow_keeps_read_only_permissions(self):
        def workflow_write(w):
            w["permissions"] = {"contents": "write"}

        def workflow_more(w):
            w["permissions"]["actions"] = "write"

        def workflow_none(w):
            del w["permissions"]

        def workflow_all(w):
            w["permissions"] = "write-all"

        def unit_job(w):
            w["jobs"]["unit"]["permissions"] = {"contents": "write"}

        def unit_job_read(w):
            w["jobs"]["unit"]["permissions"] = {"contents": "read"}

        mutations = {
            "contents write": workflow_write,
            "extra scope": workflow_more,
            "no permissions block": workflow_none,
            "write-all": workflow_all,
            "unit job override": unit_job,
            "unit job override even for read": unit_job_read,
        }
        for name, change in mutations.items():
            with self.subTest(name):
                shutil.copy(ROOT / CI, self.root / CI)
                self.assertEqual(self.edit_ci(change), [c.PERMISSIONS_PROBLEM])

    def test_the_workflow_runs_on_pushes_to_main_and_never_on_pull_request_target(self):
        def triggers(w):
            return w.get("on", w.get(True))

        def other_branches(w):
            triggers(w)["push"]["branches"] = ["**"]

        def no_push(w):
            del triggers(w)["push"]

        def target(w):
            triggers(w)["pull_request_target"] = {"types": ["opened"]}

        def release(w):
            triggers(w)["release"] = {"types": ["published"]}

        for name, change in {"all branches": other_branches, "no push": no_push, "pull_request_target": target, "release": release}.items():
            with self.subTest(name):
                shutil.copy(ROOT / CI, self.root / CI)
                self.assertEqual(self.edit_ci(change), [c.TRIGGER_PROBLEM])

    def test_pull_request_stays_a_trigger_so_the_build_is_still_checked(self):
        def no_pr(w):
            del w.get("on", w.get(True))["pull_request"]

        self.assertEqual(self.edit_ci(no_pr), [c.TRIGGER_PROBLEM])

    def test_verify_sh_must_run_the_check_and_its_tests(self):
        got = self.edit_text(VERIFY, "step debug-apk python3 -I scripts/check_debug_apk.py\n", "")
        self.assertEqual(got, ["verify.sh has no active step: step debug-apk python3 -I scripts/check_debug_apk.py"])
        shutil.copy(ROOT / VERIFY, self.root / VERIFY)
        got = self.edit_text(VERIFY, "step debug-apk-tests", "# step debug-apk-tests")
        self.assertEqual(got, ["verify.sh has no active step: step debug-apk-tests python3 -I scripts/test_check_debug_apk.py"])

    def test_the_tasks_job_must_run_the_check_and_its_tests(self):
        for cmd in (c.TESTS_CMD, c.CHECK_CMD):
            with self.subTest(cmd):
                shutil.copy(ROOT / CI, self.root / CI)
                got = self.edit_text(CI, f"run: {cmd}", "run: true")
                self.assertEqual(got, [f"ci.yml tasks job has no step running: {cmd}"])

    def test_the_readme_tells_the_owner_where_to_download_it_and_what_it_is(self):
        for phrase in c.DOC_PHRASES:
            with self.subTest(phrase):
                shutil.copy(ROOT / README, self.root / README)
                text = (self.root / README).read_text()
                head, _, rest = text.partition("## Debug APK")
                section, sep, tail = rest.partition("\n## ")
                self.assertIn(phrase, section)
                (self.root / README).write_text(head + "## Debug APK" + section.replace(phrase, "x") + sep + tail)
                self.assertEqual(c.problems(self.root), [f"README.md section 'Debug APK' does not mention {phrase!r}"])

    def test_a_phrase_outside_the_section_does_not_count(self):
        text = (self.root / README).read_text().replace("## Debug APK", "## Something else")
        (self.root / README).write_text(text + "\n" + " ".join(c.DOC_PHRASES) + "\n")
        self.assertEqual(c.problems(self.root), ["README.md has no 'Debug APK' section"])


if __name__ == "__main__":
    unittest.main()
