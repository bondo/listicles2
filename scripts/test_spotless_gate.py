"""Tests for what the root spotlessCheck formats (M1-98). Run: python3 -I scripts/test_spotless_gate.py

A slow Gradle self-test (scripts/ci_scope.py SELFTESTS). The root build passes Spotless file trees, not "**/..." strings, because for a
string Spotless reads every subproject's layout, which Gradle's isolated projects mode rejects. This checks that the trees cover what the
strings did: a badly formatted .kt file in any module's sources (also in a package named `build`) and a .gradle.kts file anywhere fail
spotlessCheck, naming the file; build output (the root's and each module's build directory) is not checked. Each probe file is written
for one run and removed afterwards, with any directory it created.
"""

import contextlib
import shutil
import subprocess
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BAD_KOTLIN = "package probe\nfun  spotlessProbe( ) {  }\n"
BAD_SCRIPT = "val  spotlessProbe =  1\n"
CHECKED = {
    "app/src/main/kotlin/probe/SpotlessProbe.kt": BAD_KOTLIN,
    "core/domain/src/test/kotlin/probe/SpotlessProbe.kt": BAD_KOTLIN,
    # M1-98 self-review: a source package named `build` is source, not build output.
    "core/data/src/main/kotlin/dk/bjarkebjarke/tally/build/SpotlessProbe.kt": BAD_KOTLIN,
    "core/testing/spotless-probe.gradle.kts": BAD_SCRIPT,
}
NOT_CHECKED = {
    "build/spotless-probe/src/main/kotlin/SpotlessProbe.kt": BAD_KOTLIN,
    "app/build/spotless-probe/src/main/kotlin/SpotlessProbe.kt": BAD_KOTLIN,
    "core/domain/build/spotless-probe/src/main/kotlin/SpotlessProbe.kt": BAD_KOTLIN,
    "app/build/spotless-probe/probe.gradle.kts": BAD_SCRIPT,
}


@contextlib.contextmanager
def probes(files):
    """Writes the files (none may exist yet) and removes them and every directory they needed, whatever happens."""
    made = []
    try:
        for rel, text in files.items():
            path = ROOT / rel
            assert not path.exists(), f"{rel} exists already; the probe would overwrite it"
            first_new = next((p for p in reversed(path.parents) if not p.exists()), None)
            path.parent.mkdir(parents=True, exist_ok=True)
            made.append(first_new or path)
            path.write_text(text, encoding="utf-8")
        yield
    finally:
        for p in made:
            if p.is_dir():
                shutil.rmtree(p)
            elif p.exists():
                p.unlink()


def spotless_check():
    # --continue: the Kotlin and the Gradle-script checks both report, whichever fails first.
    cmd = [str(ROOT / "gradlew"), "-q", "--console=plain", "--no-daemon", "--continue", "spotlessCheck"]
    for attempt in range(5):
        r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
        out = r.stdout + r.stderr
        # Retry only Maven/Gradle 429 (rate limit) so a throttled download is not read as a test failure.
        if "429" in out and "Too Many Requests" in out and attempt < 4:
            time.sleep(10 * (attempt + 1))
            continue
        return r.returncode, out
    raise AssertionError("unreachable")


class SpotlessGateTest(unittest.TestCase):
    def test_clean_tree_passes(self):
        rc, out = spotless_check()
        self.assertEqual(rc, 0, out)

    def test_module_sources_and_gradle_scripts_are_checked(self):
        with probes(CHECKED):
            rc, out = spotless_check()
        self.assertNotEqual(rc, 0, out)
        self.assertIn("format violations", out)
        for rel in CHECKED:
            with self.subTest(rel=rel):
                self.assertIn(rel, out)

    def test_build_output_is_not_checked(self):
        with probes(NOT_CHECKED):
            rc, out = spotless_check()
        self.assertEqual(rc, 0, out)

    def test_probes_are_removed(self):
        with probes({"app/build/spotless-probe/x/SpotlessProbe.kt": BAD_KOTLIN}):
            self.assertTrue((ROOT / "app/build/spotless-probe/x/SpotlessProbe.kt").is_file())
        self.assertFalse((ROOT / "app/build/spotless-probe").exists())


if __name__ == "__main__":
    unittest.main()
