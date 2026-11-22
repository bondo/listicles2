"""Tests that .gitignore covers google-services.json and key files, and that none is tracked (M1-30). Run: python3 -I scripts/test_gitignore_secrets.py

Uses `git check-ignore --no-index`, so the answer is about the patterns alone, not about what is tracked. Git runs
without global or system config and without .git/info/exclude (see check_ignore), so the result is the same on every machine.
"""

import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent

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
    "firebase/listicles-firebase-adminsdk-x1y2z-0123456789.json",
    "listicles-firebase-adminsdk-x1y2z-0123456789.json",
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
    "firebase/.firebaserc",
    "docs/firebase-admin.md",
    "firebase/firestore.rules",
    "docs/service-accounts.md",
    "scripts/service_account.py",
    "core/testing/src/main/resources/META-INF/services/org.junit.platform.launcher.LauncherSessionListener",
    ".env.example",
    "docs/env.md",
    "gradle/verification-metadata.xml",
    "README.md",
]


def clean_env() -> dict[str, str]:
    """The environment for git with no global or system config, so a developer's own settings cannot change an answer."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    return {**env, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}


def check_ignore(path: str) -> bool:
    """True when the patterns of the repo's root .gitignore ignore `path`.

    Runs in a throwaway repo that holds only a copy of the root .gitignore: no global excludes file (core.excludesFile),
    no .git/info/exclude and no other .gitignore can add a pattern the repo lacks.
    """
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / ".gitignore").write_bytes((ROOT / ".gitignore").read_bytes())
        env = clean_env()
        subprocess.run(["git", "init", "-q", "--template=", tmp], env=env, capture_output=True, check=True)
        r = subprocess.run(
            ["git", "-c", "core.excludesFile=" + os.devnull, "check-ignore", "--no-index", "-q", "--", path],
            cwd=tmp,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
    if r.returncode not in (0, 1):
        raise RuntimeError(f"git check-ignore failed for {path}: {r.stderr}")
    return r.returncode == 0


def tracked_ignored() -> set[str]:
    """Tracked files that the repo's own .gitignore files (root and nested) would ignore; global excludes are not read."""
    out = subprocess.run(
        ["git", "-c", "core.excludesFile=" + os.devnull, "ls-files", "-ci", "-X", ".gitignore", "--exclude-per-directory=.gitignore"],
        cwd=ROOT,
        env=clean_env(),
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return set(out.split("\n")) - {""}


def tracked_google_services(root: Path) -> list[str]:
    """Tracked files named google-services.json in any directory of the repo at `root`, sorted."""
    out = subprocess.run(
        ["git", "ls-files", "-z", "--", ":(glob)**/google-services.json"],
        cwd=root,
        env=clean_env(),
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return sorted(set(out.split("\0")) - {""})


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
        self.assertEqual(tracked_ignored(), set())


class NoTrackedFirebaseConfig(unittest.TestCase):
    """M1-30 (M1.md section 1): no google-services.json is ever committed; the build generates a stand-in instead."""

    def test_no_google_services_json_is_tracked(self):
        self.assertEqual(tracked_google_services(ROOT), [])

    def test_a_force_added_one_is_found_and_look_alikes_are_not(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = clean_env()
            subprocess.run(["git", "init", "-q", "--template=", tmp], env=env, capture_output=True, check=True)
            for name in ["app/google-services.json", "app/src/debug/google-services.json", "docs/google-services.json.md"]:
                (Path(tmp) / name).parent.mkdir(parents=True, exist_ok=True)
                (Path(tmp) / name).write_text("{}")
            subprocess.run(["git", "add", "-f", "."], cwd=tmp, env=env, capture_output=True, check=True)
            self.assertEqual(tracked_google_services(Path(tmp)), ["app/google-services.json", "app/src/debug/google-services.json"])


class IndependentOfDeveloperMachine(unittest.TestCase):
    """A global excludes file must not change the answers: one set by core.excludesFile and the default one in XDG_CONFIG_HOME/git/ignore."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        excludes = Path(tmp.name) / "excludes"
        excludes.write_text("poison-*.txt\nREADME.md\n")
        config = Path(tmp.name) / "gitconfig"
        config.write_text(f"[core]\n\texcludesFile = {excludes}\n")
        xdg_ignore = Path(tmp.name) / "xdg" / "git" / "ignore"  # git reads this without any config naming it
        xdg_ignore.parent.mkdir(parents=True)
        xdg_ignore.write_text("poison-*.txt\nREADME.md\n")
        env = {"GIT_CONFIG_GLOBAL": str(config), "XDG_CONFIG_HOME": str(Path(tmp.name) / "xdg")}
        patcher = mock.patch.dict(os.environ, env)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_global_excludes_do_not_hide_a_missing_pattern(self):
        self.assertFalse(check_ignore("poison-1.txt"))

    def test_global_excludes_do_not_hide_a_tracked_ignored_file(self):
        self.assertEqual(tracked_ignored(), set())


if __name__ == "__main__":
    unittest.main()
