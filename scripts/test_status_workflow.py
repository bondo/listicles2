"""Wiring and security tests for the status workflow (M0.5-27): .github/workflows/status.yml must keep write access to
the one job, use only GITHUB_TOKEN, never put event text in a shell, never force-push and never run for fork PRs; its
tests must run in verify.sh and CI; README must embed the image from the status branch. Each rule has a negative
case: a mutated copy of the real workflow must be flagged. Run: python3 -I scripts/test_status_workflow.py"""

import os
import re
import unittest

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
IMAGE_URL = "https://raw.githubusercontent.com/bondo/listicles2/status/status.svg"
TESTS = ("python3 -I scripts/test_status_visual.py", "python3 -I scripts/test_status_publish.py",
         "python3 -I scripts/test_status_workflow.py")
JOB_PERMISSIONS = ["checks: read", "contents: write", "issues: read", "pull-requests: read"]
USES = re.compile(r"^\s*-?\s*uses:\s*([\w./-]+)@(\S+)\s*$")


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


def active_lines(text):
    return [ln.strip() for ln in text.splitlines() if ln.strip() and not ln.strip().startswith("#")]


def runs(text, command):
    pattern = re.compile(rf"^(?:step\s+[\w-]+\s+|(?:-\s+)?run:\s+){re.escape(command)}$")
    return any(pattern.match(ln) for ln in active_lines(text))


def block(text, key, indent):
    """Lines of the mapping under `<indent spaces><key>:` (more deeply indented), or None."""
    lines = text.splitlines()
    for i, ln in enumerate(lines):
        if re.fullmatch(rf" {{{indent}}}{re.escape(key)}:\s*(#.*)?", ln):
            out = []
            for nxt in lines[i + 1:]:
                if nxt.strip() and len(nxt) - len(nxt.lstrip()) <= indent:
                    break
                out.append(nxt)
            return out
    return None


def run_scripts(text):
    """The text of every `run:` step (one-liners and block scalars)."""
    lines, out = text.splitlines(), []
    for i, ln in enumerate(lines):
        m = re.match(r"^(\s*)(?:-\s+)?run:\s*(.*)$", ln)
        if not m:
            continue
        indent, rest = len(m.group(1)), m.group(2)
        if rest.strip() in ("|", ">", "|-", ">-"):
            body = []
            for nxt in lines[i + 1:]:
                if nxt.strip() and len(nxt) - len(nxt.lstrip()) <= indent:
                    break
                body.append(nxt)
            out.append("\n".join(body))
        else:
            out.append(rest)
    return out


def step_after(text, marker):
    """The stripped lines of the step that starts at the line containing marker (up to the next `- ` step)."""
    lines = text.splitlines()
    start = next((i for i, ln in enumerate(lines) if marker in ln), None)
    out = []
    for ln in lines[start + 1:] if start is not None else []:
        if ln.strip().startswith("- "):
            break
        out.append(ln.strip())
    return out


def problems(text):
    found = []
    top = block(text, "permissions", 0)
    if top is None or [x.strip() for x in top if x.strip()] != ["contents: read"]:
        found.append("workflow-level permissions must be exactly `contents: read`")
    job = block(text, "publish", 2)
    perms = block("\n".join(job or []), "permissions", 4) if job else None
    if perms is None or sorted(x.strip() for x in perms if x.strip()) != JOB_PERMISSIONS:
        found.append("the job's permissions must be exactly contents: write plus read on pull-requests, issues and checks")
    for trigger in ("schedule:", "workflow_dispatch:", "issues:", "push:"):
        if not re.search(rf"^  {trigger}", text, re.M):
            found.append(f"missing trigger {trigger}")
    if "*/30 * * * *" not in text:
        found.append("schedule must be every 30 minutes")
    if "branches: [main]" not in text:
        found.append("push trigger must be limited to branches: [main]")
    if re.search(r"^  (pull_request\w*|issue_comment|workflow_run):", text, re.M):
        found.append("pull_request, pull_request_target, issue_comment and workflow_run are not allowed")
    for script in run_scripts(text):
        if "${{" in script:
            found.append("a run step interpolates an expression: pass it through env")
    for m in re.finditer(r"secrets\.(\w+)", text):
        if m.group(1) != "GITHUB_TOKEN":
            found.append(f"secret {m.group(1)}: only GITHUB_TOKEN is allowed")
    if "github.actor != 'dependabot[bot]'" not in text:
        found.append("the job must skip Dependabot (read-only token)")
    conc = block(text, "concurrency", 0) or []
    if not any(re.fullmatch(r"  group: \S+", ln) for ln in conc) or "  cancel-in-progress: false" not in conc:
        found.append("concurrency group with cancel-in-progress: false is required")
    if "ref: main" not in step_after(text, "uses: actions/checkout@v4"):
        found.append("checkout must use ref: main")
    for ln in text.splitlines():
        m = USES.match(ln)
        if m and not re.fullmatch(r"v\d+", m.group(2)):
            found.append(f"{m.group(1)}@{m.group(2)}: pin like ci.yml (major tag)")
    if re.search(r"--force|force-with-lease|\s-f\s|push\s+\S+\s+\+", text):
        found.append("never force-push")
    for needle in ("scripts/status_fetch.py", "scripts/status_visual.py render", "scripts/status_publish.py"):
        if needle not in text:
            found.append(f"missing step: {needle}")
    return found


class StatusWorkflow(unittest.TestCase):
    def setUp(self):
        self.text = read(".github", "workflows", "status.yml")

    def test_real_workflow_has_no_problems(self):
        self.assertEqual(problems(self.text), [])

    def flagged(self, mutated, keyword):
        self.assertNotEqual(mutated, self.text, "mutation did not apply")
        self.assertTrue(any(keyword in p for p in problems(mutated)), problems(mutated))

    def test_extra_job_permission_is_flagged(self):
        self.flagged(self.text.replace("contents: write", "contents: write\n      actions: write"), "job's permissions")

    def test_write_at_workflow_level_is_flagged(self):
        self.flagged(self.text.replace("permissions:\n  contents: read", "permissions:\n  contents: write", 1), "workflow-level")

    def test_pull_request_triggers_are_flagged(self):
        for trigger in ("pull_request", "pull_request_target"):
            with self.subTest(trigger):
                self.flagged(self.text.replace("  issues:", f"  {trigger}:\n  issues:", 1), "not allowed")

    def test_write_on_another_scope_is_flagged(self):
        self.flagged(self.text.replace("issues: read", "issues: write"), "job's permissions")

    def test_dropping_a_read_scope_is_flagged(self):
        self.flagged(self.text.replace("      checks: read\n", ""), "job's permissions")

    def test_event_text_in_a_shell_step_is_flagged(self):
        injected = "echo ${{ github.event.issue.title }}\n          python3 -I scripts/status_fetch.py"
        self.flagged(self.text.replace("python3 -I scripts/status_fetch.py", injected, 1), "interpolates")

    def test_other_secrets_are_flagged(self):
        self.flagged(self.text.replace("secrets.GITHUB_TOKEN", "secrets.MY_PAT", 1), "only GITHUB_TOKEN")

    def test_force_push_is_flagged(self):
        self.flagged(self.text + "\n      - run: git push --force origin status\n", "force-push")

    def test_unpinned_action_is_flagged(self):
        self.flagged(self.text.replace("actions/checkout@v4", "actions/checkout@main", 1), "pin like ci.yml")

    def test_checkout_of_the_event_ref_is_flagged(self):
        self.flagged(self.text.replace("ref: main", "ref: ${{ github.ref }}", 1), "ref: main")

    def test_cancelling_runs_is_flagged(self):
        self.flagged(self.text.replace("cancel-in-progress: false", "cancel-in-progress: true"), "concurrency")

    def test_the_publisher_never_force_pushes(self):
        src = read("scripts", "status_publish.py")
        self.assertFalse(re.search(r"--force|force-with-lease|\"\+|'\+", src), "status_publish.py must push plainly")


class Wiring(unittest.TestCase):
    def test_tests_run_in_verify_and_ci(self):
        verify, ci = read("scripts", "verify.sh"), read(".github", "workflows", "ci.yml")
        for cmd in TESTS:
            self.assertTrue(runs(verify, cmd), f"verify.sh must run {cmd}")
            self.assertTrue(runs(ci, cmd), f"ci.yml must run {cmd}")

    def test_runs_helper_rejects_commented_and_suffixed_commands(self):
        self.assertFalse(runs("# step x python3 -I a.py", "python3 -I a.py"))
        self.assertFalse(runs("step x python3 -I a.py || true", "python3 -I a.py"))
        self.assertTrue(runs("step x python3 -I a.py", "python3 -I a.py"))

    def test_readme_embeds_the_image_from_the_status_branch(self):
        self.assertIn(f"]({IMAGE_URL})", read("README.md"))


if __name__ == "__main__":
    unittest.main()
