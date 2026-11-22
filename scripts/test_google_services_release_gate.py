"""Tests that a release build refuses the google-services.json stand-in (M1-30, PR 304 R1-02).

Run: python3 -I scripts/test_google_services_release_gate.py

Without app/google-services.json the build generates a demo-tally stand-in (app/build.gradle.kts). That is for CI only
(docs/milestones/M1.md section 1): packaging a non-debug variant (APK or bundle) must fail, unless the build passes
-Ptally.allowStandInRelease=true (only M1-33's CI release smoke build). Debug builds always use the stand-in.
The tests read the task graph (--dry-run) and run the refusal task itself. They need a checkout without a real
google-services.json (CI, a fresh clone), so the first test fails with a clear message when one is present.
A slow Gradle self-test (scripts/ci_scope.py SELFTESTS).
"""

import os
import subprocess
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REFUSE = ":app:refuseGoogleServicesStandInRelease"
OPT_IN = "-Ptally.allowStandInRelease=true"


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
    if rc != 0:
        raise AssertionError(f"dry run of {args} failed:\n{out}")
    return out


class ReleaseRefusesTheStandIn(unittest.TestCase):
    def test_checkout_has_no_real_config(self):
        real = sorted(str(p.relative_to(ROOT)) for p in [ROOT / "app/google-services.json", *(ROOT / "app/src").glob("*/google-services.json")] if p.is_file())
        self.assertEqual(real, [], "these tests need a checkout without a real google-services.json")

    def test_apk_and_bundle_packaging_run_the_refusal(self):
        self.assertIn(REFUSE, planned(":app:assembleRelease"))
        self.assertIn(REFUSE, planned(":app:bundleRelease"))

    def test_the_refusal_fails_and_names_the_way_out(self):
        rc, out = gradle(REFUSE)
        self.assertNotEqual(rc, 0, out)
        self.assertIn("google-services.json", out)
        self.assertIn("tally.allowStandInRelease=true", out)

    def test_the_opt_in_lets_release_use_the_stand_in(self):
        out = planned(":app:assembleRelease", ":app:bundleRelease", OPT_IN)
        self.assertNotIn("refuseGoogleServicesStandIn", out)
        self.assertIn(":app:googleServicesStandInRelease", out)

    def test_only_true_opts_in(self):
        self.assertIn(REFUSE, planned(":app:assembleRelease", "-Ptally.allowStandInRelease=false"))
        self.assertIn(REFUSE, planned(":app:assembleRelease", "-Ptally.allowStandInRelease=yes"))

    def test_debug_is_unaffected(self):
        out = planned(":app:assembleDebug", ":app:bundleDebug")
        self.assertNotIn("refuseGoogleServicesStandIn", out)
        self.assertIn(":app:googleServicesStandInDebug", out)


if __name__ == "__main__":
    unittest.main()
