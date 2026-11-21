"""Checks that the screenshot gate (M1-03) is wired into verify.sh and CI.

  * verify.sh runs the gate's tests, this check and `scripts/screenshots.sh verify` as active steps,
  * ci.yml: the `tasks` job runs the tests and this check; the `screenshots` job runs the gate, then uploads the Roborazzi
    diffs when a step failed (a pinned actions/upload-artifact step after the gate), and the gate step cannot be allowed
    to fail. It is its own job because test_ci_scope.py forbids `if:` in the jobs that are required checks.
  * the golden set under app/src/test/screenshots is exactly light and dark x en and da plus the 200 % font-scale Danish
    light golden (valid, small, all different), and the Roborazzi build setup compares exactly (no colour distance, shift or changed-pixel tolerance, anywhere),
    and every Compose UI test in androidTest turns the ATF accessibility checks on and none turns them off (P15).
Run: python3 -I scripts/check_screenshots.py  (exit 1 and one line per problem).
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TESTS_CMD = "python3 -I scripts/test_screenshots.py"
CHECK_CMD = "python3 -I scripts/check_screenshots.py"
GATE_CMD = "./scripts/screenshots.sh verify"
VERIFY_STEPS = (f"step screenshots-tests {TESTS_CMD}", f"step screenshots-wiring {CHECK_CMD}", f"step screenshots {GATE_CMD}")
DIFF_PATH = "app/build/outputs/roborazzi"
GOLDEN_DIR = "app/src/test/screenshots"
GOLDENS = tuple(f"TallyApp_{lang}_{mode}.png" for lang in ("en", "da") for mode in ("light", "dark")) + ("TallyApp_da_light_font200.png",)
MAX_GOLDEN_BYTES = 300 * 1024  # the guards.sh limit for a PNG
EXACT_OPTIONS = ("ThresholdValidator(0f)", "maxDistance = 0f", "hShift = 0", "vShift = 0")
TOLERANCE = re.compile(r"changeThreshold|ThresholdValidator\(|SimpleImageComparator\(|(?:resultValidator|imageComparator)\s*=")
INPUT_PROBLEM = "app/build.gradle.kts must declare src/test/screenshots as an input of the test tasks (else verify skips when only goldens changed)"
OPTIONS_FILE = "app/src/test/kotlin/dk/bjarkebjarke/tally/ScreenshotOptions.kt"
PINNED = re.compile(r"uses:\s*actions/upload-artifact@[0-9a-f]{40}(?:\s|$)")


def _active_lines(text):
    return [ln.strip() for ln in text.splitlines() if ln.strip() and not ln.strip().startswith("#")]


def _job_steps(ci, job):
    """One job of ci.yml as a list of step texts."""
    m = re.search(rf"^  {job}:\n(.*?)(?=^  [A-Za-z][\w-]*:[ \t]*$|\Z)", ci, re.S | re.M)
    if m is None:
        return []
    return [s for s in re.split(r"(?m)^      - ", m.group(1))[1:]]


def _runs(step, command):
    return any(ln.removeprefix("- ") == f"run: {command}" for ln in _active_lines(step))


def wiring_problems(root):
    root = Path(root)
    problems = []
    verify = _active_lines((root / "scripts/verify.sh").read_text())
    problems += [f"verify.sh has no active step: {want}" for want in VERIFY_STEPS if want not in verify]

    ci = (root / ".github/workflows/ci.yml").read_text()
    for job, cmds in (("tasks", (TESTS_CMD, CHECK_CMD)), ("screenshots", (GATE_CMD,))):
        steps = _job_steps(ci, job)
        problems += [f"ci.yml {job} job has no step running: {cmd}" for cmd in cmds if not any(_runs(s, cmd) for s in steps)]
    steps = _job_steps(ci, "screenshots")
    gate = next((i for i, s in enumerate(steps) if _runs(s, GATE_CMD)), None)
    if gate is not None and "continue-on-error" in steps[gate]:
        problems.append("ci.yml screenshot gate step has continue-on-error")

    upload = next((i for i, s in enumerate(steps) if "uses: actions/upload-artifact@" in s), None)
    if upload is None:
        problems.append("ci.yml screenshots job has no actions/upload-artifact step")
        return problems
    step = steps[upload]
    lines = _active_lines(step)
    if not PINNED.search(step):
        problems.append("ci.yml upload-artifact must be pinned to a 40-character commit SHA")
    if "if: failure()" not in lines:
        problems.append("ci.yml screenshot-diffs upload must have if: failure()")
    if f"path: {DIFF_PATH}" not in lines:
        problems.append(f"ci.yml screenshot-diffs upload must have path: {DIFF_PATH}")
    if gate is not None and upload < gate:
        problems.append("ci.yml screenshot-diffs upload must come after the screenshot gate step")
    return problems


def golden_problems(root):
    folder = Path(root) / GOLDEN_DIR
    problems = []
    present = {p.name: p for p in folder.glob("*")} if folder.is_dir() else {}
    problems += [f"missing golden {GOLDEN_DIR}/{name}" for name in GOLDENS if name not in present]
    problems += [f"unexpected file {GOLDEN_DIR}/{name}" for name in sorted(present) if name not in GOLDENS]
    seen = {}
    for name in GOLDENS:
        if name not in present:
            continue
        data = present[name].read_bytes()
        if not data.startswith(b"\x89PNG\r\n\x1a\n"):
            problems.append(f"{GOLDEN_DIR}/{name} is not a PNG")
        elif len(data) > MAX_GOLDEN_BYTES:
            problems.append(f"{GOLDEN_DIR}/{name} is over 300 KB")
        elif data in seen:
            problems.append(f"{GOLDEN_DIR}/{name} and {seen[data]} are identical")
        else:
            seen[data] = name
    return problems


def build_problems(root):
    root = Path(root)
    problems = []
    if "alias(libs.plugins.roborazzi)" not in (root / "app/build.gradle.kts").read_text():
        problems.append("app/build.gradle.kts does not apply the Roborazzi plugin")
    if not re.search(r"(?m)^roborazzi = \{ id = ", (root / "gradle/libs.versions.toml").read_text()):
        problems.append("libs.versions.toml has no roborazzi plugin")
    if not re.search(r'inputs\s*\.dir\("src/test/screenshots"\)', (root / "app/build.gradle.kts").read_text()):
        problems.append(INPUT_PROBLEM)
    options = root / OPTIONS_FILE
    text = options.read_text() if options.is_file() else ""
    if not all(want in text for want in EXACT_OPTIONS) or len(re.findall(r"ThresholdValidator\(", text)) != 1:
        problems.append("ScreenshotOptions.kt must compare exactly: " + ", ".join(EXACT_OPTIONS))
    for source in sorted((root / "app/src/test").rglob("*.kt")):
        if source != options and TOLERANCE.search(source.read_text()):
            problems.append(f"{source.relative_to(root)} sets a comparison tolerance")
    return problems


def accessibility_problems(root):
    root = Path(root)
    problems = []
    if "androidTestImplementation(libs.compose.ui.test.junit4.accessibility)" not in (root / "app/build.gradle.kts").read_text():
        problems.append("app/build.gradle.kts does not add compose.ui.test.junit4.accessibility to androidTestImplementation")
    for source in sorted(root.glob("**/src/androidTest/**/*.kt")):
        text, name = source.read_text(), source.relative_to(root)
        if re.search(r"createComposeRule|createAndroidComposeRule", text) and "enableAccessibilityChecks()" not in text:
            problems.append(f"{name} uses a Compose test rule but never calls enableAccessibilityChecks()")
        if "disableAccessibilityChecks" in text:
            problems.append(f"{name} calls disableAccessibilityChecks()")
    return problems


def main():
    problems = wiring_problems(ROOT) + golden_problems(ROOT) + build_problems(ROOT) + accessibility_problems(ROOT)
    for p in problems:
        print(f"check_screenshots: {p}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
