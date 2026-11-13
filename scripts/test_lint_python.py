"""Tests for M0.5-07: ruff check (E,F,W,B,UP,SIM) and mypy (default) over scripts/, via scripts/lint_python.sh.
Wiring (config, pinned tools, verify.sh, CI, CODEOWNERS) has negative cases; the behaviour tests run the real script on
deliberate violations and check that it fails for the right rule, and on clean code and check that it passes.
Needs the pinned tools installed: pip install -r scripts/requirements-lint.txt. Run: python3 -I scripts/test_lint_python.py"""

import os
import re
import subprocess
import tempfile
import tomllib
import unittest

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
SCRIPT = os.path.join(ROOT, "scripts", "lint_python.sh")
RULES = ["E", "F", "W", "B", "UP", "SIM"]
LINT_CMD = "./scripts/lint_python.sh"
TEST_CMD = "python3 -I scripts/test_lint_python.py"
PIN = re.compile(r"^[A-Za-z0-9_.-]+==[0-9][0-9A-Za-z.]*$")
CLEAN = 'def add(a: int, b: int) -> int:\n    return a + b\n'
# One deliberate violation per selected rule family, and one for mypy. Each must fail the script and name its rule.
VIOLATIONS = {
    "F401": "import os\n",
    "E711": "def f(x: int | None) -> bool:\n    return x == None\n",
    "W291": "x = 1  \n",
    "B006": "def f(a: list[int] = []) -> list[int]:\n    return a\n",
    "UP006": "from typing import List\n\n\ndef f(a: List[int]) -> int:\n    return len(a)\n",
    "SIM108": "def f(c: bool) -> int:\n    if c:\n        r = 1\n    else:\n        r = 2\n    return r\n",
    "[assignment]": 'x: int = "not an int"\n',
}


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


def explicit_owners(codeowners, path):
    for ln in active_lines(codeowners):
        parts = ln.split()
        if parts and parts[0] == "/" + path:
            return parts[1:]
    return None


def lint(source, requirements=None):
    """Run lint_python.sh on a temp file holding `source`; returns (exit code, combined output)."""
    env = dict(os.environ)
    if requirements is not None:
        env["LINT_PY_REQUIREMENTS"] = requirements
    with tempfile.TemporaryDirectory() as tmp:
        target = os.path.join(tmp, "sample.py")
        with open(target, "w", encoding="utf-8") as f:
            f.write(source)
        done = subprocess.run([SCRIPT, target], cwd=ROOT, env=env, capture_output=True, text=True, check=False)
    return done.returncode, done.stdout + done.stderr


class HelperNegativeCases(unittest.TestCase):
    def test_commented_out_or_masked_command_does_not_count(self):
        self.assertFalse(runs(f"# step l {LINT_CMD}\n", LINT_CMD))
        self.assertFalse(runs(f"step l {LINT_CMD} || true\n", LINT_CMD))
        self.assertFalse(runs(f"      - run: {LINT_CMD} ; true\n", LINT_CMD))
        self.assertTrue(runs(f"step l {LINT_CMD}\n", LINT_CMD))
        self.assertTrue(runs(f"        run: {LINT_CMD}\n", LINT_CMD))

    def test_step_in_a_branch_is_not_top_level(self):
        self.assertFalse(top_level_step(f'if [ "$FAST" = 0 ]; then\n  step l {LINT_CMD}\nfi\n', LINT_CMD))
        self.assertTrue(top_level_step(f"step l {LINT_CMD}\n", LINT_CMD))

    def test_directory_pattern_is_not_an_explicit_entry(self):
        self.assertIsNone(explicit_owners("/scripts/  @bondo\n", "ruff.toml"))
        self.assertEqual(explicit_owners("/ruff.toml  @bondo\n", "ruff.toml"), ["@bondo"])


class Config(unittest.TestCase):
    def test_ruff_selects_exactly_the_agreed_rules(self):
        cfg = tomllib.loads(read("ruff.toml"))
        self.assertEqual(cfg.get("lint", {}).get("select"), RULES)

    def test_ruff_config_relaxes_nothing_and_has_no_formatter(self):
        text = read("ruff.toml")
        cfg = tomllib.loads(text)
        lint_cfg = cfg.get("lint", {})
        for key in ("ignore", "extend-ignore", "per-file-ignores", "extend-select", "fixable", "unfixable"):
            self.assertNotIn(key, lint_cfg, key)
        for key in ("exclude", "extend-exclude", "format", "preview", "unsafe-fixes"):
            self.assertNotIn(key, cfg, key)
        self.assertNotRegex(text, r"(?m)^\s*(ignore|exclude|extend-exclude|per-file-ignores)\b")

    def test_mypy_is_default_and_relaxes_nothing(self):
        text = read("mypy.ini")
        self.assertIn("[mypy]", text)
        for ln in active_lines(text):
            self.assertRegex(ln, r"^(\[mypy\]|files\s*=\s*scripts|cache_dir\s*=\s*\S+)$", ln)

    def test_tools_are_pinned_exactly(self):
        lines = active_lines(read("scripts", "requirements-lint.txt"))
        for ln in lines:
            self.assertRegex(ln, PIN, ln)
        names = {ln.split("==")[0].lower() for ln in lines}
        self.assertTrue({"ruff", "mypy", "types-pyyaml"} <= names, names)

    def test_no_ruff_format_anywhere_in_the_wiring(self):
        for rel in (("scripts", "verify.sh"), ("scripts", "lint_python.sh"), (".github", "workflows", "ci.yml")):
            self.assertNotRegex(read(*rel), r"ruff\s+format", rel)


class VerifyAndCiWiring(unittest.TestCase):
    def test_verify_runs_lint_and_its_tests_even_in_fast_mode(self):
        verify = read("scripts", "verify.sh")
        self.assertTrue(top_level_step(verify, LINT_CMD))
        self.assertTrue(top_level_step(verify, TEST_CMD))

    def test_ci_job_installs_pinned_tools_and_runs_both(self):
        body = job(read(".github", "workflows", "ci.yml"), "python-lint")
        self.assertIsNotNone(body, "ci.yml needs a python-lint job")
        self.assertIn("actions/checkout", body)
        self.assertIn("actions/setup-python", body)
        self.assertTrue(runs(body, "pip install -r scripts/requirements-lint.txt"))
        self.assertTrue(runs(body, LINT_CMD))
        self.assertTrue(runs(body, TEST_CMD))
        self.assertNotRegex(body, r"(?m)^\s*if:")
        self.assertNotIn("continue-on-error", body)

    def test_codeowners_name_the_config_files_explicitly(self):
        owners = read(".github", "CODEOWNERS")
        for path in ("ruff.toml", "mypy.ini", "scripts/requirements-lint.txt", "scripts/lint_python.sh"):
            self.assertEqual(explicit_owners(owners, path), ["@bondo"], path)


class Behaviour(unittest.TestCase):
    def test_clean_code_passes(self):
        code, out = lint(CLEAN)
        self.assertEqual(code, 0, out)

    def test_each_deliberate_violation_fails_with_its_rule(self):
        for rule, source in VIOLATIONS.items():
            with self.subTest(rule=rule):
                code, out = lint(source)
                self.assertNotEqual(code, 0, out)
                self.assertIn(rule, out)

    def test_a_pin_that_does_not_match_the_installed_tool_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            reqs = os.path.join(tmp, "reqs.txt")
            with open(reqs, "w", encoding="utf-8") as f:
                f.write("ruff==0.0.1\nmypy==0.0.1\n")
            code, out = lint(CLEAN, requirements=reqs)
        self.assertNotEqual(code, 0, out)
        self.assertIn("requirements-lint.txt", out)

    def test_missing_requirements_file_fails(self):
        code, out = lint(CLEAN, requirements="/nonexistent/requirements.txt")
        self.assertNotEqual(code, 0, out)


if __name__ == "__main__":
    unittest.main()
