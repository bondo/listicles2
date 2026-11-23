"""CI hardening rules (M1-44, issues 189 and 127). Fails closed: a rule that cannot be read is a problem.

  * every job in ci.yml and status.yml has `timeout-minutes`, a whole number from 1 to 60 (GitHub's default is 6 hours),
  * python and node come from actions/setup-python and actions/setup-node, not from the runner image: a job that runs python3, pip,
    a shell script that runs python3, node, npm or npx (or a script that runs node) has the setup step before its first such step,
    one python minor and one node major in every job,
  * `npm ci` runs with --ignore-scripts, in the workflows and in verify.sh (the lockfile's install scripts are not needed: the
    emulators and the rules tests run without them, re2 is only an optional dependency of the hosting emulator),
  * the gitleaks download uses --proto =https, --proto-redir =https and --retry, the archive checksum is checked, and the scan is
    `gitleaks git` (`detect` is deprecated),
  * verify.sh and the CI `tasks` job run this check and its tests, and docs/adr/0003-gradle-dependency-verification.md records that
    Gradle dependency verification is checksum-only (issue 189 item 6).
Run: python3 -I scripts/check_ci_hardening.py  (exit 1 and one line per problem).
"""

import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS = (".github/workflows/ci.yml", ".github/workflows/status.yml")
MAX_TIMEOUT = 60
PYTHON_VERSION = "3.13"  # what the runner image shipped before the pin; 3.12 fails a hook test (chr() raises OverflowError there)
NODE_VERSION = "22"
SETUP_PYTHON = "actions/setup-python@"
SETUP_NODE = "actions/setup-node@"
# Scripts that start node themselves; a job that runs them needs the node pin although its commands never say `node`.
NODE_SCRIPTS = ("test_wireframes_safety.py", "test_firebase_ts.py")
ADR = "docs/adr/0003-gradle-dependency-verification.md"
ADR_PHRASES = ("Status: accepted", "verify-signatures", "checksum")
CHECK_CMD = "python3 -I scripts/check_ci_hardening.py"
TESTS_CMD = "python3 -I scripts/test_check_ci_hardening.py"
VERIFY_STEPS = (f"step ci-hardening-tests {TESTS_CMD}", f"step ci-hardening {CHECK_CMD}")
PYTHON_WORD = re.compile(r"(?<![\w./-])(?:python3?|pip3?)(?![\w-])")
NODE_WORD = re.compile(r"(?<![\w./-])(?:node|npm|npx)(?![\w-])")
# Gradle tasks that run python3 in an Exec (checkUnitTestResults finalizes the unit-test tasks, checkJavaApiLevel in build.gradle.kts):
# a job that runs one of them needs the python pin although its commands never say `python3`. A fixed list, held to the build files by
# the tests; `check` and `build` stay out (they would match build/ paths).
GRADLE_PYTHON_TASKS = ("testDebugUnitTest", "verifyRoborazziDebug", "recordRoborazziDebug", "checkJavaApiLevel")
GRADLE_PYTHON = re.compile(r"gradlew\b[\s\S]*(?<![\w])(?:" + "|".join(GRADLE_PYTHON_TASKS) + r")(?![\w])")
# setup-python's interpreter has no PyYAML (the runner image's had) and most gate scripts import yaml.
REQUIREMENTS_CI = "scripts/requirements-ci.txt"
INSTALL_CI = "pip install -r scripts/requirements-ci.txt"
SHELL_SCRIPT = re.compile(r"scripts/[\w.-]+\.sh")


def _steps(job):
    return [s for s in (job or {}).get("steps") or [] if isinstance(s, dict)]


def _is_use(step, prefix):
    return str(step.get("uses", "")).startswith(prefix)


def _code(step):
    """The commands a step runs (run, and the script of an action that takes one), comment lines removed."""
    text = str(step.get("run", "")) + "\n" + str((step.get("with") or {}).get("script", ""))
    return "\n".join(ln for ln in text.splitlines() if not ln.strip().startswith("#"))


def _runs_python(text):
    return bool(PYTHON_WORD.search(text) or GRADLE_PYTHON.search(text))


def _needs_python(code, root):
    if _runs_python(code):
        return True
    for script in SHELL_SCRIPT.findall(code):
        path = root / script
        if path.is_file() and _runs_python(path.read_text()):
            return True
    return False


def _needs_node(code):
    return bool(NODE_WORD.search(code)) or any(s in code for s in NODE_SCRIPTS)


def _load(root, name):
    return yaml.safe_load((root / name).read_text()) or {}


def _setup_problems(where, steps, prefix, tool, want, version_key, needs, install=None):
    first = next((i for i, s in enumerate(steps) if needs(_code(s))), None)
    if first is None:
        return []
    setups = [i for i, s in enumerate(steps) if _is_use(s, prefix)]
    if not setups:
        return [f"{where} runs {tool} but has no {prefix.rstrip('@')} step: it would use the runner image's {tool}"]
    problems = []
    if setups[0] > first:
        problems.append(f"{where}: {prefix.rstrip('@')} must come before the first step that runs {tool} ({steps[first].get('name', first)})")
    for i in setups:
        got = (steps[i].get("with") or {}).get(version_key)
        if str(got) != want:
            problems.append(f"{where}: {version_key} must be {want} (one {tool} version in every job), not {got!r}")
    if install:
        found = [i for i, s in enumerate(steps) if s.get("run") == install]
        if not found:
            problems.append(f"{where}: no step runs `{install}` (requirements-ci.txt: PyYAML, which setup-python's {tool} lacks)")
        elif found[0] > first:
            problems.append(f"{where}: `{install}` must come before the first step that runs {tool} ({steps[first].get('name', first)})")
    return problems


def requirements_ci_problems(root):
    path = root / REQUIREMENTS_CI
    if not path.is_file():
        return [f"{REQUIREMENTS_CI} is missing (PyYAML pinned with ==, installed by every job that sets up python)"]
    lines = [ln.split("#", 1)[0].strip() for ln in path.read_text().splitlines()]
    lines = [ln for ln in lines if ln]
    if lines != [ln for ln in lines if re.fullmatch(r"PyYAML==\d+\.\d+\.\d+", ln)] or len(lines) != 1:
        return [f"{REQUIREMENTS_CI} must hold exactly one line, PyYAML==X.Y.Z (the other scripts use the standard library)"]
    return []


def workflow_problems(root):
    problems = []
    for name in WORKFLOWS:
        base = name.rsplit("/", 1)[1]
        for job_name, job in (_load(root, name).get("jobs") or {}).items():
            where = f"{base} job {job_name}"
            timeout = (job or {}).get("timeout-minutes")
            if type(timeout) is not int or not 1 <= timeout <= MAX_TIMEOUT:
                problems.append(f"{where}: timeout-minutes must be a whole number from 1 to {MAX_TIMEOUT}, not {timeout!r}")
            steps = _steps(job)
            problems += _setup_problems(where, steps, SETUP_PYTHON, "python", PYTHON_VERSION, "python-version", lambda c: _needs_python(c, root), INSTALL_CI)
            problems += _setup_problems(where, steps, SETUP_NODE, "node", NODE_VERSION, "node-version", _needs_node)
            for step in steps:
                code = _code(step)
                for line in code.splitlines():
                    if re.search(r"\bnpm\s+ci\b", line) and "--ignore-scripts" not in line:
                        problems.append(f"{where}: `npm ci` needs --ignore-scripts")
                if "gitleaks" in code:
                    problems += _gitleaks_problems(where, code)
    return problems


def _gitleaks_problems(where, code):
    problems = []
    for flag in ("--proto =https", "--proto-redir =https", "--retry"):
        if flag not in code:
            problems.append(f"{where}: the gitleaks download needs curl {flag}")
    if "sha256sum -c" not in code:
        problems.append(f"{where}: the gitleaks archive must be checked with sha256sum -c")
    if "gitleaks detect" in code or "gitleaks git" not in code:
        problems.append(f"{where}: run `gitleaks git` (`gitleaks detect` is deprecated)")
    if re.search(r"gitleaks git\b.*--source", code):
        problems.append(f"{where}: `gitleaks git` takes the repository as an argument, not --source (unknown flag)")
    return problems


def verify_problems(root):
    lines = [ln.strip() for ln in (root / "scripts/verify.sh").read_text().splitlines() if ln.strip() and not ln.strip().startswith("#")]
    problems = [f"verify.sh has no active step: {want}" for want in VERIFY_STEPS if want not in lines]
    problems += [f"verify.sh: `npm ci` needs --ignore-scripts: {ln}" for ln in lines if re.search(r"\bnpm\s+ci\b", ln) and "--ignore-scripts" not in ln]
    tasks = _steps((_load(root, WORKFLOWS[0]).get("jobs") or {}).get("tasks"))
    problems += [f"ci.yml tasks job has no step running: {cmd}" for cmd in (TESTS_CMD, CHECK_CMD) if not any(s.get("run") == cmd for s in tasks)]
    return problems


def adr_problems(root):
    path = root / ADR
    if not path.is_file():
        return [f"ADR missing: {ADR} (issue 189 item 6: Gradle dependency verification is checksum-only)"]
    text = path.read_text()
    return [f"ADR {ADR} does not mention {p!r}" for p in ADR_PHRASES if p not in text]


def problems(root=ROOT):
    root = Path(root)
    return workflow_problems(root) + requirements_ci_problems(root) + verify_problems(root) + adr_problems(root)


def main(root=ROOT):
    found = problems(root)
    for p in found:
        print(f"check_ci_hardening: {p}")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
