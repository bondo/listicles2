"""Tests for scripts/check_ui_emulators.py, the wiring of the Auth and Firestore emulators behind the `ui` job (M1-02, #254).

Run: python3 -I scripts/test_check_ui_emulators.py

The check runs on the real files first, then on copies with one defect each, which must each be reported.
"""

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_ui_emulators as c  # noqa: E402  # justified: must follow the sys.path insert above

ROOT = Path(__file__).resolve().parent.parent
CI = ".github/workflows/ci.yml"
VERIFY = "scripts/verify.sh"
FIREBASE = "firebase/firebase.json"
HELPER = "core/data/src/androidTest/kotlin/dk/bjarkebjarke/tally/data/FirebaseEmulator.kt"
SMOKE = "core/data/src/androidTest/kotlin/dk/bjarkebjarke/tally/data/EmulatorSmokeTest.kt"
BUILD = "core/data/build.gradle.kts"
EXEC = "firebase emulators:exec --only auth,firestore --project demo-tally"
SHAPE = c.SHAPE


class Wiring(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        for name in (CI, VERIFY, FIREBASE, HELPER, SMOKE, BUILD):
            (self.root / name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(ROOT / name, self.root / name)

    def mutated(self, name, old, new, count=1):
        path = self.root / name
        text = path.read_text()
        self.assertIn(old, text, f"{name} no longer contains {old!r}: update the test")
        path.write_text(text.replace(old, new, count))
        return c.problems(self.root)

    def test_the_repository_wiring_is_complete(self):
        self.assertEqual(c.problems(ROOT), [])

    def test_firebase_json_must_start_the_auth_emulator(self):
        path = self.root / FIREBASE
        config = json.loads(path.read_text())
        del config["emulators"]["auth"]
        path.write_text(json.dumps(config))
        self.assertEqual(c.problems(self.root), ["firebase.json has no emulators.auth entry with a host and a port"])

    def test_firebase_json_must_start_the_firestore_emulator(self):
        path = self.root / FIREBASE
        config = json.loads(path.read_text())
        del config["emulators"]["firestore"]
        path.write_text(json.dumps(config))
        self.assertEqual(c.problems(self.root), ["firebase.json has no emulators.firestore entry with a host and a port"])

    def test_the_auth_port_must_match_the_one_the_tests_use(self):
        got = self.mutated(FIREBASE, '"port": 9099', '"port": 9199')
        self.assertEqual(got, ["firebase.json emulators.auth port 9199 differs from AUTH_PORT 9099 in FirebaseEmulator.kt"])

    def test_the_firestore_port_must_match_the_one_the_tests_use(self):
        got = self.mutated(HELPER, "FIRESTORE_PORT = 8080", "FIRESTORE_PORT = 8081")
        self.assertEqual(got, ["firebase.json emulators.firestore port 8080 differs from FIRESTORE_PORT 8081 in FirebaseEmulator.kt"])

    def test_the_project_must_be_demo_tally(self):
        got = self.mutated(HELPER, 'PROJECT_ID = "demo-tally"', 'PROJECT_ID = "listicles"')
        self.assertEqual(got, ["FirebaseEmulator.kt PROJECT_ID must be demo-tally (a demo- project never reaches the real Firebase)"])

    def test_ci_must_run_the_ui_tests_inside_the_emulators(self):
        got = self.mutated(CI, EXEC, "echo")
        self.assertEqual(got, [f"ci.yml ui job does not run its tests inside `{EXEC}`"])

    def test_ci_must_start_both_emulators(self):
        got = self.mutated(CI, "--only auth,firestore", "--only firestore")
        self.assertEqual(got, [f"ci.yml ui job does not run its tests inside `{EXEC}`"])

    def test_ci_must_run_the_data_tests_in_the_ui_job(self):
        got = self.mutated(CI, " :core:data:connectedDebugAndroidTest", "")
        self.assertEqual(got, ["ci.yml ui job does not run :core:data:connectedDebugAndroidTest inside the emulators"])

    def test_ci_must_still_run_the_app_tests_in_the_ui_job(self):
        got = self.mutated(CI, ":app:connectedDebugAndroidTest ", "")
        self.assertEqual(got, ["ci.yml ui job does not run :app:connectedDebugAndroidTest inside the emulators"])

    def test_the_ui_job_must_install_the_firebase_cli(self):
        got = self.mutated(CI, "npm ci --silent", "npm install --silent", count=2)
        self.assertEqual(got, ["ci.yml ui job has no `npm ci` step in firebase/ (the emulators come from firebase-tools)"])

    def test_ui_test_failures_must_not_be_swallowed(self):
        got = self.mutated(CI, ":core:data:connectedDebugAndroidTest", ":core:data:connectedDebugAndroidTest || true")
        self.assertEqual(got, [SHAPE, "ci.yml ui job swallows a test failure (`|| true`, `continue-on-error`)"])

    def test_the_diagnostics_fallback_must_still_fail_the_job(self):
        self.assertEqual(self.mutated(CI, "; false)", ")"), [SHAPE])

    def test_a_fallback_that_exits_zero_is_not_accepted(self):
        self.assertEqual(self.mutated(CI, "; false)", "; exit 0)"), [SHAPE])

    def test_the_ui_job_must_run_gradle_and_not_echo_it(self):
        self.assertEqual(self.mutated(CI, "./gradlew --console=plain", "echo --console=plain"), [SHAPE])

    def test_the_tests_must_not_run_after_a_semicolon(self):
        got = self.mutated(CI, "cd .. && ./gradlew", "cd .. ; ./gradlew")
        self.assertEqual(got, [SHAPE])

    def test_a_second_fallback_is_not_accepted(self):
        got = self.mutated(CI, "; false)", "; false) || (true)")
        self.assertEqual(got, [SHAPE])

    def test_the_ui_job_must_not_be_skippable(self):
        got = self.mutated(CI, "      - name: enable KVM\n", "      - name: enable KVM\n        if: github.event_name == 'push'\n")
        self.assertEqual(got, ["ci.yml ui job has a step with `if:` (the job is a required check)"])

    def test_verify_sh_must_run_the_check(self):
        got = self.mutated(VERIFY, "step ui-emulators python3 -I scripts/check_ui_emulators.py\n", "")
        self.assertEqual(got, ["verify.sh has no active step: step ui-emulators python3 -I scripts/check_ui_emulators.py"])

    def test_a_commented_out_verify_step_does_not_count(self):
        got = self.mutated(VERIFY, "step ui-emulators-tests", "# step ui-emulators-tests")
        self.assertEqual(got, ["verify.sh has no active step: step ui-emulators-tests python3 -I scripts/test_check_ui_emulators.py"])

    def test_verify_sh_must_compile_the_data_tests(self):
        got = self.mutated(VERIFY, " :core:data:assembleDebugAndroidTest", "")
        self.assertEqual(got, ["verify.sh build step does not compile :core:data:assembleDebugAndroidTest"])

    def test_the_tasks_job_must_run_the_check_and_its_tests(self):
        got = self.mutated(CI, "run: python3 -I scripts/check_ui_emulators.py", "run: true")
        self.assertEqual(got, ["ci.yml tasks job has no step running: python3 -I scripts/check_ui_emulators.py"])

    def test_the_data_module_must_have_the_test_support_module_on_its_unit_test_classpath(self):
        got = self.mutated(BUILD, 'testImplementation(project(":core:testing"))', "")
        self.assertEqual(got, [":core:data must have testImplementation(project(\":core:testing\")) (#217 item 3)"])

    def test_the_data_module_must_run_unit_tests_on_the_junit_platform(self):
        # R1-02: the :core:testing network block is a JUnit Platform listener; on Gradle's JUnit 4 runner it never installs.
        got = self.mutated(BUILD, "useJUnitPlatform", "useJUnit")
        self.assertEqual(len(got), 1)
        self.assertIn("JUnit Platform", got[0])

    def test_the_smoke_test_must_exist_and_have_a_test(self):
        got = self.mutated(SMOKE, "@Test", "// not a test", count=3)
        self.assertEqual(got, ["core/data androidTest has no @Test that talks to the emulators (EmulatorSmokeTest)"])


if __name__ == "__main__":
    unittest.main()
