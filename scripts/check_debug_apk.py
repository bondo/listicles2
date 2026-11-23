"""Checks the debug APK artifact wiring in ci.yml (M1-63, #15 comment 7081546814).

Every push to main uploads the debug APK that the `unit` job already builds (`:app:assembleDebug`) as an Actions artifact:

  * the `unit` job has exactly one actions/upload-artifact step and it equals one frozen mapping (EXPECTED_UPLOAD): only a push to
    main runs it, the name is `tally-debug-<short sha>`, retention 30 days, and a missing APK fails the job. Any other key, `if`,
    path, version or `continue-on-error` fails. It comes after the step that runs `:app:assembleDebug` and after the short sha step,
  * the short sha step (`id: sha`) is frozen too (EXPECTED_SHA): it needs no condition and uses no expression for the sha,
  * no other job uploads an artifact except the screenshots job (diffs when a step failed; check_screenshots.py owns that step),
    so a pull request can never publish an APK,
  * the workflow keeps `permissions: contents: read` and no job overrides it; it triggers on pull requests and on pushes to `main`
    only (no `pull_request_target`, no release or other trigger),
  * verify.sh and the CI `tasks` job run this check and its tests,
  * README.md has a "Debug APK" section that says where to download it, that it carries the demo-tally stand-in Firebase config and
    is for the owner's own device only (M1-O5, #291).
Run: python3 -I scripts/check_debug_apk.py  (exit 1 and one line per problem).
"""

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
UPLOAD_ACTION = "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a"
PUSH_MAIN = "github.event_name == 'push' && github.ref == 'refs/heads/main'"
# Frozen (an allowlist fails closed where a deny list can be bypassed). Changing the upload changes this mapping, in the same PR.
EXPECTED_UPLOAD = {
    "name": "debug APK artifact (push to main only, M1-63)",
    "if": PUSH_MAIN,
    "uses": UPLOAD_ACTION,
    "with": {
        "name": "tally-debug-${{ steps.sha.outputs.short }}",
        "path": "app/build/outputs/apk/debug/*.apk",
        "retention-days": 30,
        "if-no-files-found": "error",
    },
}
EXPECTED_SHA = {
    "name": "short commit sha for the debug APK artifact name",
    "id": "sha",
    "run": 'echo "short=${GITHUB_SHA::7}" >> "$GITHUB_OUTPUT"',
}
BUILD_TASK = ":app:assembleDebug"
TESTS_CMD = "python3 -I scripts/test_check_debug_apk.py"
CHECK_CMD = "python3 -I scripts/check_debug_apk.py"
VERIFY_STEPS = (f"step debug-apk-tests {TESTS_CMD}", f"step debug-apk {CHECK_CMD}")
DOC_HEADING = "## Debug APK"
DOC_PHRASES = ("Artifacts", "tally-debug-", "demo-tally", "own device", "M1-O5")
UPLOAD_PROBLEM = "ci.yml jobs.unit must have exactly one actions/upload-artifact step, equal to EXPECTED_UPLOAD in check_debug_apk.py"
SHA_PROBLEM = "ci.yml jobs.unit must have the short sha step (id: sha), equal to EXPECTED_SHA in check_debug_apk.py"
ORDER_PROBLEM = f"ci.yml jobs.unit: the {BUILD_TASK} step must come before the sha step, and both before the upload step"
ELSEWHERE_PROBLEM = "ci.yml: actions/upload-artifact outside the unit job and the screenshots job (a pull request must not publish an artifact)"
PERMISSIONS_PROBLEM = "ci.yml must keep the workflow `permissions: contents: read`, with no permissions of its own on the unit job"
TRIGGER_PROBLEM = "ci.yml must trigger on pull_request and on push to main only"


def _is_upload(step):
    return isinstance(step, dict) and str(step.get("uses", "")).startswith("actions/upload-artifact@")


def _steps(job):
    return [s for s in (job or {}).get("steps") or [] if isinstance(s, dict)]


def _first(steps, predicate):
    return next((i for i, s in enumerate(steps) if predicate(s)), None)


def ci_problems(root):
    ci = yaml.safe_load((root / ".github/workflows/ci.yml").read_text()) or {}
    jobs = ci.get("jobs") or {}
    unit = jobs.get("unit") or {}
    steps = _steps(unit)
    problems = []
    upload_ok = [s for s in steps if _is_upload(s)] == [EXPECTED_UPLOAD]
    sha_ok = [s for s in steps if s.get("id") == "sha"] == [EXPECTED_SHA]
    if not upload_ok:
        problems.append(UPLOAD_PROBLEM)
    if not sha_ok:
        problems.append(SHA_PROBLEM)
    if upload_ok and sha_ok:
        build = _first(steps, lambda s: BUILD_TASK in str(s.get("run", "")).split())
        sha = _first(steps, lambda s: s.get("id") == "sha")
        upload = _first(steps, _is_upload)
        if build is None or sha is None or upload is None or not build < sha < upload:
            problems.append(ORDER_PROBLEM)
    for name, job in jobs.items():
        if name not in ("unit", "screenshots") and any(_is_upload(s) for s in _steps(job)):
            problems.append(ELSEWHERE_PROBLEM)
    if sum(_is_upload(s) for s in _steps(jobs.get("screenshots"))) > 1:
        problems.append(ELSEWHERE_PROBLEM)
    if ci.get("permissions") != {"contents": "read"} or "permissions" in unit:
        problems.append(PERMISSIONS_PROBLEM)
    triggers = ci.get("on", ci.get(True))
    if not isinstance(triggers, dict) or set(triggers) != {"pull_request", "push"} or (triggers.get("push") or {}).get("branches") != ["main"]:
        problems.append(TRIGGER_PROBLEM)
    return problems


def _active_lines(text):
    return [ln.strip() for ln in text.splitlines() if ln.strip() and not ln.strip().startswith("#")]


def wiring_problems(root):
    verify = _active_lines((root / "scripts/verify.sh").read_text())
    problems = [f"verify.sh has no active step: {want}" for want in VERIFY_STEPS if want not in verify]
    tasks = _steps(((yaml.safe_load((root / ".github/workflows/ci.yml").read_text()) or {}).get("jobs") or {}).get("tasks"))
    for cmd in (TESTS_CMD, CHECK_CMD):
        if not any(s.get("run") == cmd for s in tasks):
            problems.append(f"ci.yml tasks job has no step running: {cmd}")
    return problems


def doc_problems(root):
    text = (root / "README.md").read_text()
    if DOC_HEADING not in text.splitlines():
        return [f"README.md has no {DOC_HEADING.removeprefix('## ')!r} section"]
    section = text.split(DOC_HEADING + "\n", 1)[1].split("\n## ", 1)[0]
    return [f"README.md section {DOC_HEADING.removeprefix('## ')!r} does not mention {p!r}" for p in DOC_PHRASES if p not in section]


def problems(root=ROOT):
    root = Path(root)
    return ci_problems(root) + wiring_problems(root) + doc_problems(root)


def main(root=ROOT):
    found = problems(root)
    for p in found:
        print(f"check_debug_apk: {p}")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
