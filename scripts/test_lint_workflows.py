"""Tests for M0.5-06: shellcheck (-S warning), actionlint and zizmor (--offline), pinned in scripts/linters.pins, run by
scripts/lint_workflows.sh from verify.sh and CI. Behaviour tests run the real script on deliberate violations (an unpinned
action, a missing persist-credentials, a shellcheck warning, an actionlint error) and expect a failure that names the rule,
and on clean input and expect a pass. Wiring tests check verify.sh, CI, the SHA pins with their version comments, and that
nothing weakens the check (no config, no ignore comment, no threshold flag). Run: python3 -I scripts/test_lint_workflows.py"""

import glob
import os
import re
import subprocess
import tempfile
import unittest

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
SCRIPT = os.path.join(ROOT, "scripts", "lint_workflows.sh")
LINT_CMD = "./scripts/lint_workflows.sh"
TEST_CMD = "python3 -I scripts/test_lint_workflows.py"
SHA = "34e114876b0b11c390a56381ad16ebd13914f8d5"
USES = re.compile(r"^\s*-?\s*uses:\s*(\S+)@(\S+?)(?:\s+#\s*(.*))?$")
PINNED = re.compile(r"^[0-9a-f]{40}$")
VERSION = re.compile(r"^v\d+(\.\d+){1,2}$")


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


def active_lines(text):
    return [ln.strip() for ln in text.splitlines() if ln.strip() and not ln.strip().startswith("#")]


def runs(text, command):
    """True if an active line is exactly the command as a verify.sh `step <name> <cmd>` or a workflow `run: <cmd>`."""
    pattern = re.compile(rf"^(?:step\s+[\w-]+\s+|(?:-\s+)?run:\s+){re.escape(command)}$")
    return any(pattern.match(ln) for ln in active_lines(text))


def top_level_step(text, command):
    """Like runs(), but the line must not be indented, so a step moved into the --fast branch does not count."""
    return runs("\n".join(ln for ln in text.splitlines() if ln == ln.lstrip()), command)


def job(text, name):
    m = re.search(rf"^  {re.escape(name)}:\n(.*?)(?=^  [A-Za-z][\w-]*:\n|\Z)", text, re.S | re.M)
    return m.group(1) if m else None


def pin_problems(text):
    """Every `uses:` of a remote action must be a full commit SHA followed by a `# vX.Y.Z` version comment."""
    out = []
    for ln in text.splitlines():
        m = USES.match(ln)
        if not m or m.group(1).startswith("./"):
            continue
        if not PINNED.fullmatch(m.group(2)):
            out.append(f"{m.group(1)}@{m.group(2)}: not a 40-hex commit SHA")
        elif not VERSION.fullmatch((m.group(3) or "").strip()):
            out.append(f"{m.group(1)}@{m.group(2)[:7]}: needs a trailing '# vX.Y.Z' version comment")
    return out


def checkout_problems(text):
    """Every actions/checkout step must set persist-credentials: false in its own with: block."""
    out = []
    steps = re.split(r"(?m)^\s*- (?=\S)", text)
    for s in steps:
        if re.match(r"uses:\s*actions/checkout@", s) and not re.search(r"(?m)^\s*persist-credentials:\s*false\s*$", s):
            out.append("actions/checkout without persist-credentials: false")
    return out


CHECKOUT = f"uses: actions/checkout@{SHA} # v4.3.1\n        with:\n          persist-credentials: false"


def workflow(step=CHECKOUT, run="echo ok"):
    return (f"name: t\non: push\npermissions: {{}}\njobs:\n  j:\n    runs-on: ubuntu-latest\n    permissions:\n      contents: read\n"
            f"    steps:\n      - {step}\n      - run: {run}\n")


def lint(args, files):
    """Run lint_workflows.sh `args` (a path placeholder {d} is the temp dir) on temp files; returns (exit code, output)."""
    with tempfile.TemporaryDirectory() as tmp:
        for rel, text in files.items():
            path = os.path.join(tmp, rel)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
        done = subprocess.run([SCRIPT, *[a.format(d=tmp) for a in args]], cwd=ROOT, capture_output=True, text=True, check=False)
    return done.returncode, done.stdout + done.stderr


def lint_wf(text):
    return lint(["workflows", "{d}/.github/workflows"], {".github/workflows/t.yml": text})


def lint_sh(text):
    return lint(["shell", "{d}/t.sh"], {"t.sh": text})


class Helpers(unittest.TestCase):
    def test_pin_check_flags_unpinned_and_uncommented(self):
        self.assertEqual(pin_problems(f"      - uses: actions/checkout@{SHA} # v4.3.1\n"), [])
        self.assertEqual(pin_problems("      - uses: ./local-action\n"), [])
        for bad in ("actions/checkout@v4", "actions/checkout@main", f"actions/checkout@{SHA[:39]}", f"actions/checkout@{SHA.upper()}",
                    f"actions/checkout@{SHA}", f"actions/checkout@{SHA} # latest", f"actions/checkout@{SHA} #"):
            with self.subTest(bad):
                self.assertNotEqual(pin_problems(f"      - uses: {bad}\n"), [])

    def test_checkout_check_flags_missing_or_true(self):
        ok = f"steps:\n  - uses: actions/checkout@{SHA} # v4.3.1\n    with:\n      persist-credentials: false\n  - run: x\n"
        self.assertEqual(checkout_problems(ok), [])
        self.assertNotEqual(checkout_problems(ok.replace("false", "true")), [])
        self.assertNotEqual(checkout_problems(ok.replace("      persist-credentials: false\n", "")), [])
        self.assertNotEqual(checkout_problems(ok.replace("persist-credentials: false", "ref: main")), [])
        two = ok + f"  - uses: actions/checkout@{SHA} # v4.3.1\n  - run: y\n"
        self.assertNotEqual(checkout_problems(two), [])


class Behaviour(unittest.TestCase):
    def test_clean_workflow_passes(self):
        code, out = lint_wf(workflow())
        self.assertEqual(code, 0, out)

    def test_unpinned_action_fails(self):
        code, out = lint_wf(workflow(step="uses: actions/checkout@v4\n        with:\n          persist-credentials: false"))
        self.assertNotEqual(code, 0)
        self.assertIn("unpinned-uses", out)

    def test_missing_persist_credentials_fails(self):
        code, out = lint_wf(workflow(step=f"uses: actions/checkout@{SHA} # v4.3.1"))
        self.assertNotEqual(code, 0)
        self.assertIn("artipacked", out)

    def test_ignore_comment_does_not_hide_a_finding(self):
        code, out = lint_wf(workflow(step="uses: actions/checkout@v4 # zizmor: ignore[unpinned-uses]\n        with:\n          persist-credentials: false"))
        self.assertNotEqual(code, 0)
        self.assertIn("unpinned-uses", out)

    def test_actionlint_error_fails(self):
        code, out = lint_wf(workflow().replace("runs-on: ubuntu-latest", "runs-on: ubuntu-latest\n    needs: nowhere"))
        self.assertNotEqual(code, 0)
        self.assertIn("nowhere", out)

    def test_shellcheck_warning_inside_a_run_step_fails(self):
        code, out = lint_wf(workflow(run="rm $(ls)"))
        self.assertNotEqual(code, 0)
        self.assertIn("SC2046", out)

    def test_shell_warning_fails(self):
        code, out = lint_sh("#!/usr/bin/env bash\nrm $(ls)\n")
        self.assertNotEqual(code, 0)
        self.assertIn("SC2046", out)

    def test_shell_info_level_finding_does_not_fail_at_warning_severity(self):
        code, out = lint_sh('#!/usr/bin/env bash\nx=1\necho $x\n')
        self.assertEqual(code, 0, out)

    def test_clean_shell_passes(self):
        code, out = lint_sh('#!/usr/bin/env bash\nset -euo pipefail\necho "$1"\n')
        self.assertEqual(code, 0, out)

    def test_missing_target_fails(self):
        self.assertNotEqual(lint(["shell", "{d}/nope.sh"], {})[0], 0)
        self.assertNotEqual(lint(["workflows", "{d}/.github/workflows"], {})[0], 0)
        self.assertNotEqual(lint(["bogus"], {})[0], 0)


class Repository(unittest.TestCase):
    def test_every_tracked_shell_file_and_workflow_passes(self):
        """Includes the lint script itself: a comment that starts with `# shellcheck (` is parsed as a directive (SC1073)."""
        done = subprocess.run([SCRIPT], cwd=ROOT, capture_output=True, text=True, check=False)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)


class Wiring(unittest.TestCase):
    def test_verify_runs_the_lint_and_its_tests_even_in_fast_mode(self):
        verify = read("scripts", "verify.sh")
        self.assertTrue(top_level_step(verify, LINT_CMD))
        self.assertTrue(top_level_step(verify, TEST_CMD))

    def test_ci_job_runs_both_without_escape_hatches(self):
        body = job(read(".github", "workflows", "ci.yml"), "workflow-lint")
        self.assertIsNotNone(body, "ci.yml needs a workflow-lint job")
        self.assertTrue(runs(body, LINT_CMD))
        self.assertTrue(runs(body, TEST_CMD))
        self.assertNotRegex(body, r"(?m)^\s*if:")
        self.assertNotIn("continue-on-error", body)

    def test_every_action_is_sha_pinned_with_a_version_comment(self):
        files = sorted(glob.glob(os.path.join(ROOT, ".github", "workflows", "*.yml")))
        self.assertGreaterEqual(len(files), 2)
        for path in files:
            with self.subTest(os.path.basename(path)):
                text = read(".github", "workflows", os.path.basename(path))
                self.assertEqual(pin_problems(text), [])
                self.assertEqual(checkout_problems(text), [])

    def test_nothing_weakens_the_check(self):
        for cfg in (".github/zizmor.yml", ".github/zizmor.yaml", "zizmor.yml", "zizmor.yaml", ".github/actionlint.yaml",
                    ".github/actionlint.yml", ".shellcheckrc"):
            self.assertFalse(os.path.exists(os.path.join(ROOT, cfg)), f"{cfg} could lower the policy")
        for path in glob.glob(os.path.join(ROOT, ".github", "workflows", "*.yml")):
            self.assertNotRegex(read(".github", "workflows", os.path.basename(path)), r"zizmor:\s*ignore|shellcheck\s+disable", path)
        script = read("scripts", "lint_workflows.sh")
        self.assertRegex(script, r"shellcheck\b.*-S warning")
        self.assertRegex(script, r"zizmor\b.*--offline.*--no-ignores")
        self.assertNotRegex(script, r"--min-severity|--min-confidence|--persona|--pedantic|(?<![\w-])-ignore\b|--fix|\|\|\s*true")

    def test_codeowners_name_the_script_and_the_pins_explicitly(self):
        owners = active_lines(read(".github", "CODEOWNERS"))
        for path in ("scripts/lint_workflows.sh", "scripts/linters.pins"):
            self.assertTrue(any(ln.split()[:2] == ["/" + path, "@bondo"] for ln in owners), path)


if __name__ == "__main__":
    unittest.main()
