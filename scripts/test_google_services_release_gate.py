"""A release build refuses the google-services.json stand-in (M1-30, PR 304 R1-02; docs/milestones/M1.md section 1).

Run: python3 -I scripts/test_google_services_release_gate.py   (a slow Gradle self-test, scripts/ci_scope.py SELFTESTS)
Without the real config, packaging a non-debug variant must fail unless -Ptally.allowStandInRelease=true (M1-33's CI
smoke build); debug is unaffected. Needs a checkout without a real google-services.json (CI, a fresh clone).
"""

import subprocess
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REFUSE = ":app:refuseGoogleServicesStandInRelease"


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


class ReleaseRefusesTheStandIn(unittest.TestCase):
    def test_checkout_has_no_real_config(self):
        real = [p for p in [ROOT / "app/google-services.json", *(ROOT / "app/src").glob("*/google-services.json")] if p.is_file()]
        self.assertEqual(real, [], "these tests need a checkout without a real google-services.json")

    def test_packaging_runs_the_refusal_unless_the_opt_in_is_exactly_true(self):
        for args in [(":app:assembleRelease",), (":app:bundleRelease",), (":app:assembleRelease", "-Ptally.allowStandInRelease=yes")]:
            self.assertIn(REFUSE, planned(*args), args)
        out = planned(":app:assembleRelease", ":app:bundleRelease", "-Ptally.allowStandInRelease=true")
        self.assertNotIn("refuseGoogleServicesStandIn", out)
        self.assertIn(":app:googleServicesStandInRelease", out)

    def test_the_refusal_fails_and_names_the_way_out(self):
        rc, out = gradle(REFUSE)
        self.assertNotEqual(rc, 0, out)
        self.assertIn("app/google-services.json", out)
        self.assertIn("-Ptally.allowStandInRelease=true", out)

    def test_debug_is_unaffected(self):
        out = planned(":app:assembleDebug", ":app:bundleDebug")
        self.assertNotIn("refuseGoogleServicesStandIn", out)
        self.assertIn(":app:googleServicesStandInDebug", out)


if __name__ == "__main__":
    unittest.main()
