"""Tests that .gitignore covers google-services.json and key files. Run: python3 -I scripts/test_gitignore_secrets.py

Uses `git check-ignore --no-index`, so the answer is about the patterns alone, not about what is tracked.
"""

import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Tracked although ignored: predates this check. Anything else tracked must never match an ignore pattern.
TRACKED_BUT_IGNORED = {"firebase/.firebaserc"}

MUST_IGNORE = [
    "app/google-services.json",
    "app/src/debug/google-services.json",
    "app/src/release/google-services.json",
    "app/src/main/google-services.json",
    "app/src/staging/google-services.json",
    "app/src/stagingDebug/google-services.json",
    "google-services.json",
    "feature/lists/google-services.json",
    "release.jks",
    "app/release.keystore",
    "upload.p12",
    "app/keys/signing.p12",
    "server.pem",
    "certs/private.pem",
    ".env",
    ".env.local",
    ".env.production",
    "firebase/.env",
    "app/.env.local",
    "service-account.json",
    "service-account-key.json",
    "firebase/service-account-prod.json",
    "app/src/debug/service-account.json",
    "firebase/.firebase/hosting.abc.cache",
    "firebase/.firebase/",
]

MUST_NOT_IGNORE = [
    "app/google-services.json.md",
    "docs/google-services.md",
    "app/src/main/res/values/google_services.xml",
    "app/build.gradle.kts",
    "firebase/firebase.json",
    "firebase/.gitignore",
    "firebase/firestore.rules",
    "docs/service-accounts.md",
    "scripts/service_account.py",
    "core/testing/src/main/resources/META-INF/services/org.junit.platform.launcher.LauncherSessionListener",
    ".env.example",
    "docs/env.md",
    "gradle/verification-metadata.xml",
    "README.md",
]


def check_ignore(path: str) -> bool:
    r = subprocess.run(
        ["git", "check-ignore", "--no-index", "-q", "--", path], cwd=ROOT, capture_output=True, text=True, check=False
    )
    if r.returncode not in (0, 1):
        raise RuntimeError(f"git check-ignore failed for {path}: {r.stderr}")
    return r.returncode == 0


class Ignored(unittest.TestCase):
    def test_secret_paths_are_ignored(self):
        for path in MUST_IGNORE:
            with self.subTest(path=path):
                self.assertTrue(check_ignore(path), f"{path} must be git-ignored")


class NotIgnored(unittest.TestCase):
    def test_ordinary_paths_are_not_ignored(self):
        for path in MUST_NOT_IGNORE:
            with self.subTest(path=path):
                self.assertFalse(check_ignore(path), f"{path} must not be git-ignored")

    def test_no_tracked_file_is_ignored(self):
        out = subprocess.run(
            ["git", "ls-files", "-ci", "--exclude-standard"], cwd=ROOT, capture_output=True, text=True, check=True
        ).stdout
        tracked_ignored = set(out.split("\n")) - {""}
        self.assertEqual(tracked_ignored - TRACKED_BUT_IGNORED, set())


if __name__ == "__main__":
    unittest.main()
