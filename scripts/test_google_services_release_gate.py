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
    TEMP_CONFIG.write_text('{"project_info": {"project_number": "1", "project_id": "release-test"}, "client": []}')
    try:
        yield True
    finally:
        TEMP_CONFIG.unlink()


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


if __name__ == "__main__":
    unittest.main()
