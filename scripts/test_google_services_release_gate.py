"""A release build refuses the google-services.json stand-in (M1-30, PR 304 R1-02; docs/milestones/M1.md section 1).

Run: python3 -I scripts/test_google_services_release_gate.py   (a slow Gradle self-test, scripts/ci_scope.py SELFTESTS)
Without a real config, packaging non-debug fails unless -Ptally.allowStandInRelease=true (M1-33); debug is unaffected.
With one, nothing is refused and no stand-in is made (the owner's file is used as is, else a temporary one).
"""

import contextlib
import subprocess
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REFUSE = ":app:refuseGoogleServicesStandInRelease"
TEMP_CONFIG = ROOT / "app/src/release/google-services.json"  # git-ignored; written only when no real config exists


def real_configs():
    return [p for p in [ROOT / "app/google-services.json", *(ROOT / "app/src").glob("*/google-services.json")] if p.is_file()]


def gradle(*args):
    cmd = [str(ROOT / "gradlew"), "-q", "--console=plain", "--no-daemon", *args]
    for attempt in range(5):
        r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
        out = r.stdout + r.stderr
        # Retry only Maven/Gradle 429 (rate limit) so a throttled download is not read as a test failure.
        if "429" in out and "Too Many Requests" in out and attempt < 4:
            time.sleep(10 * (attempt + 1))
            continue
        return r.returncode, out
    raise AssertionError("unreachable")


def planned(*args):
    rc, out = gradle(*args, "--dry-run")
    assert rc == 0, f"dry run of {args} failed:\n{out}"
    return out


@contextlib.contextmanager
def a_real_config():
    """The owner's real config if there is one, else a temporary release config with dummy values, removed afterwards."""
    if real_configs():
        yield False
        return
    made_dir = not TEMP_CONFIG.parent.is_dir()
    TEMP_CONFIG.parent.mkdir(exist_ok=True)
    TEMP_CONFIG.write_text('{"project_info": {"project_number": "1", "project_id": "release-test"}, "client": []}')
    try:
        yield True
    finally:
        TEMP_CONFIG.unlink()
        if made_dir:
            TEMP_CONFIG.parent.rmdir()


class ReleaseGate(unittest.TestCase):
    def assert_real_config_is_used(self):
        out = planned(":app:assembleRelease", ":app:bundleRelease", ":app:assembleDebug")
        self.assertNotIn("refuseGoogleServicesStandIn", out)
        self.assertNotIn("googleServicesStandIn", out)
        self.assertIn(":app:processReleaseGoogleServices", out)

    def test_with_a_real_config_nothing_is_refused_and_no_stand_in_is_made(self):
        with a_real_config() as temporary:
            self.assert_real_config_is_used()
        if temporary:
            self.assertFalse(TEMP_CONFIG.is_file(), "the temporary config was not removed")

    def test_without_one_release_packaging_is_refused_unless_opted_in_and_debug_is_unaffected(self):
        if real_configs():
            self.assert_real_config_is_used()
            return
        for args in [(":app:assembleRelease",), (":app:bundleRelease",), (":app:assembleRelease", "-Ptally.allowStandInRelease=yes")]:
            self.assertIn(REFUSE, planned(*args), args)
        for args, stand_in in [(("-Ptally.allowStandInRelease=true", ":app:bundleRelease"), "Release"), ((":app:bundleDebug",), "Debug")]:
            out = planned(":app:assemble" + stand_in, *args)
            self.assertNotIn("refuseGoogleServicesStandIn", out)
            self.assertIn(":app:googleServicesStandIn" + stand_in, out)
        rc, out = gradle(REFUSE)
        self.assertNotEqual(rc, 0, out)
        self.assertIn("app/google-services.json", out)
        self.assertIn("-Ptally.allowStandInRelease=true", out)


CHECK = ":app:checkNoDebugAppCheckInRelease"


class DebugAppCheckNeverInRelease(unittest.TestCase):
    """M1-26 (PR 317 R1-03): firebase-appcheck-debug must not be on the release runtime classpath.

    The check runs before every release build (M1-33's release-smoke job builds assembleRelease). The negative case adds
    the debug provider to the release classpath with -Ptally.selfTestDebugAppCheckInRelease=true and must fail the check.
    """

    def test_every_release_build_runs_the_check(self):
        self.assertIn(CHECK, planned(":app:assembleRelease"))
        self.assertIn(CHECK, planned(":app:bundleRelease"))

    def test_it_passes_on_the_real_release_classpath(self):
        rc, out = gradle(CHECK)
        self.assertEqual(rc, 0, out)

    def test_it_fails_when_the_debug_provider_is_on_the_release_classpath(self):
        rc, out = gradle(CHECK, "-Ptally.selfTestDebugAppCheckInRelease=true")
        self.assertNotEqual(rc, 0, out)
        self.assertIn("com.google.firebase:firebase-appcheck-debug", out)

    def test_the_debug_build_still_has_the_debug_provider(self):
        rc, out = gradle(":app:dependencies", "--configuration", "debugRuntimeClasspath")
        self.assertEqual(rc, 0, out)
        self.assertIn("firebase-appcheck-debug", out)


if __name__ == "__main__":
    unittest.main()
