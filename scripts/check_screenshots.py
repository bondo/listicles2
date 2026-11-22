"""Checks that the screenshot gate (M1-03) is wired into verify.sh and CI.

  * verify.sh runs the gate's tests, this check and `scripts/screenshots.sh verify` as active steps,
  * ci.yml: the `tasks` job runs the tests and this check; the `screenshots` job runs the gate, then uploads the Roborazzi
    diffs when a step failed (a pinned actions/upload-artifact step after the gate), and none of the three
    commands' steps can be skipped (`if:`), allowed to fail (`continue-on-error`) or neutered (a folded `|| true`
    line). It is its own job because test_ci_scope.py forbids `if:` in the jobs that are required checks.
  * the golden set under app/src/test/screenshots is exactly, for every screen found by name, light and dark x en and da
    plus the 200 % font-scale Danish light golden (valid, small, all different), and TallyApp is always required;
  * the Roborazzi build setup compares exactly: no colour distance, shift or changed-pixel tolerance anywhere, and every
    Roborazzi capture call passes ScreenshotOptions.exact;
  * every Compose UI test in androidTest (any rule or runner) turns the ATF accessibility checks on, runs them on the
    screen, and none turns them off (P15).
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
GOLDEN_NAME = re.compile(r"(?P<screen>[A-Za-z][A-Za-z0-9]*)_(?:en|da)_(?:light|dark)(?:_font200)?\.png")


def screen_goldens(screen):
    """The goldens one screen needs: light and dark in en and da, plus the 200 % font-scale Danish light one (Q3 A, #15 comment 7058176190)."""
    return tuple(f"{screen}_{lang}_{mode}.png" for lang in ("en", "da") for mode in ("light", "dark")) + (f"{screen}_da_light_font200.png",)


GOLDENS = screen_goldens("TallyApp")  # the screen there is today; later screens add their own set, found by name
MAX_GOLDEN_BYTES = 300 * 1024  # the guards.sh limit for a PNG
EXACT_OPTIONS = ("ThresholdValidator(0f)", "maxDistance = 0f", "hShift = 0", "vShift = 0")
TOLERANCE = re.compile(r"changeThreshold|ThresholdValidator\(|SimpleImageComparator\(|(?:resultValidator|imageComparator)\s*=")
INPUT_PROBLEM = "app/build.gradle.kts must declare src/test/screenshots as an input of the test tasks (else verify skips when only goldens changed)"
TOKENS_PROBLEM = (
    "app/build.gradle.kts must pass design/tokens.json to the test tasks as a TokensArgs argument provider with an @get:InputFile "
    "(a plain systemProperty tracks no content and puts the absolute path into the cache key)"
)
OPTIONS_FILE = "app/src/test/kotlin/dk/bjarkebjarke/tally/ScreenshotOptions.kt"
COMPOSE_TEST = re.compile(r"create\w*ComposeRule|run\w*ComposeUiTest")
CAPTURE_CALL = re.compile(r"\bcapture\w*Robo\w*\(|\bRoborazziRule\(")
EXACT_ARGUMENT = re.compile(r"roborazziOptions\s*=\s*ScreenshotOptions\.exact\s*(?:,|\)|$)")
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


def _folded(step, command):
    """True if the line after `run: <command>` is indented further: YAML folds it into the run value (`|| true`, extra flags)."""
    lines = step.splitlines()
    for i, ln in enumerate(lines[:-1]):
        if ln.strip().removeprefix("- ") == f"run: {command}":
            indent = len(ln) - len(ln.lstrip())
            nxt = lines[i + 1]
            if nxt.strip() and len(nxt) - len(nxt.lstrip()) > indent:
                return True
    return False


def wiring_problems(root):
    root = Path(root)
    problems = []
    verify = _active_lines((root / "scripts/verify.sh").read_text())
    problems += [f"verify.sh has no active step: {want}" for want in VERIFY_STEPS if want not in verify]

    ci = (root / ".github/workflows/ci.yml").read_text()
    for job, cmds in (("tasks", (TESTS_CMD, CHECK_CMD)), ("screenshots", (GATE_CMD,))):
        steps = _job_steps(ci, job)
        problems += [f"ci.yml {job} job has no step running: {cmd}" for cmd in cmds if not any(_runs(s, cmd) for s in steps)]
        for cmd in cmds:
            for step in (s for s in steps if _runs(s, cmd)):
                if any(ln == "if:" or ln.startswith("if: ") or ln.startswith("- if: ") for ln in _active_lines(step)):
                    problems.append(f"ci.yml step running {cmd} has if:")
                if _folded(step, cmd):
                    problems.append(f"ci.yml step running {cmd} is followed by a more-indented line (a folded `|| true` or extra arguments)")
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
    screens = sorted({m.group("screen") for name in present if (m := GOLDEN_NAME.fullmatch(name))} | {"TallyApp"})
    wanted = [name for screen in screens for name in screen_goldens(screen)]
    problems += [f"missing golden {GOLDEN_DIR}/{name}" for name in wanted if name not in present]
    problems += [f"unexpected file {GOLDEN_DIR}/{name}" for name in sorted(present) if name not in wanted]
    seen = {}
    for name in wanted:
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


def _calls(text, opener):
    """The argument text of each call whose opening matches the regex `opener` (up to its balanced closing parenthesis)."""
    calls = []
    for m in opener.finditer(text):
        depth, i = 1, m.end()
        while i < len(text) and depth:
            depth += {"(": 1, ")": -1}.get(text[i], 0)
            i += 1
        calls.append(text[m.end() : i - 1].strip())
    return calls


def build_problems(root):
    root = Path(root)
    problems = []
    if "alias(libs.plugins.roborazzi)" not in (root / "app/build.gradle.kts").read_text():
        problems.append("app/build.gradle.kts does not apply the Roborazzi plugin")
    if not re.search(r"(?m)^roborazzi = \{ id = ", (root / "gradle/libs.versions.toml").read_text()):
        problems.append("libs.versions.toml has no roborazzi plugin")
    # files(fileTree(..)), not dir(..): a directory input must exist, a file tree may be empty (R1-07).
    if not re.search(r'inputs\s*\.files\(\s*fileTree\("src/test/screenshots"\)', (root / "app/build.gradle.kts").read_text()):
        problems.append(INPUT_PROBLEM)
    gradle = (root / "app/build.gradle.kts").read_text()
    if not (
        re.search(r"@get:InputFile[^)]*\)?[^)]*\bval tokensFile\b", gradle)
        and "-Dtally.tokensFile=" in gradle
        and re.search(r"jvmArgumentProviders\.add\(\s*TokensArgs\(", gradle)
    ) or re.search(r"systemProperty\(\s*\"tally\.tokensFile\"", gradle):
        problems.append(TOKENS_PROBLEM)
    options = root / OPTIONS_FILE
    text = options.read_text() if options.is_file() else ""
    if not all(want in text for want in EXACT_OPTIONS) or len(re.findall(r"ThresholdValidator\(", text)) != 1:
        problems.append("ScreenshotOptions.kt must compare exactly: " + ", ".join(EXACT_OPTIONS))
    for source in sorted((root / "app/src/test").rglob("*.kt")):
        text, name = source.read_text(), source.relative_to(root)
        if source != options and TOLERANCE.search(text):
            problems.append(f"{name} sets a comparison tolerance")
        # Every capture entry point defaults to Roborazzi's own options, which forgive a colour distance of 0.007 per pixel
        # (R1-04, R2-14); `.exact.copy(..)` would undo the exactness too, so the argument must end at the comma or the call.
        if any(not EXACT_ARGUMENT.search(call) for call in _calls(text, CAPTURE_CALL)):
            problems.append(f"{name} captures without roborazziOptions = ScreenshotOptions.exact")
    return problems


def accessibility_problems(root):
    root = Path(root)
    problems = []
    if "androidTestImplementation(libs.compose.ui.test.junit4.accessibility)" not in (root / "app/build.gradle.kts").read_text():
        problems.append("app/build.gradle.kts does not add compose.ui.test.junit4.accessibility to androidTestImplementation")
    for source in sorted(root.glob("**/src/androidTest/**/*.kt")):
        text, name = source.read_text(), source.relative_to(root)
        if COMPOSE_TEST.search(text) and "enableAccessibilityChecks()" not in text:
            problems.append(f"{name} uses a Compose test rule but never calls enableAccessibilityChecks()")
        elif COMPOSE_TEST.search(text) and "tryPerformAccessibilityChecks()" not in text:
            # The checks run only inside actions (performClick and so on); assertions and captureToImage() run none (R1-03).
            problems.append(f"{name} never calls tryPerformAccessibilityChecks(), so the checks never evaluate the screen")
        if "disableAccessibilityChecks" in text:
            problems.append(f"{name} calls disableAccessibilityChecks()")
    return problems


def main(root=ROOT):
    problems = wiring_problems(root) + golden_problems(root) + build_problems(root) + accessibility_problems(root)
    for p in problems:
        print(f"check_screenshots: {p}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
