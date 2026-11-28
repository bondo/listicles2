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
PLUGIN = "build-logic/src/main/kotlin/Conventions.kt"
EXEC = "firebase emulators:exec --only auth,firestore --project demo-tally"


class Wiring(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        for name in (CI, VERIFY, FIREBASE, HELPER, SMOKE, BUILD, PLUGIN):
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
        got = self.mutated(HELPER, 'PROJECT_ID = "demo-tally"', 'PROJECT_ID = "other-project"')
        self.assertEqual(got, ["FirebaseEmulator.kt PROJECT_ID must be demo-tally (a demo- project never reaches the real Firebase)"])

    def test_the_ui_job_is_exactly_the_pinned_one(self):
        # Fail closed (R1-01, R2-01, R2-02, R3-01): the parsed job must equal EXPECTED_UI, so no deny list can be bypassed.
        tasks = ":core:data:connectedDebugAndroidTest"
        mutations = {
            "no emulators:exec": (EXEC, "echo"),
            "only firestore": ("--only auth,firestore", "--only firestore"),
            "another project": ("--project demo-tally", "--project other-project"),
            "no data tests": (" " + tasks, ""),
            "no app tests": (":app:connectedDebugAndroidTest ", ""),
            "dry run": ("--console=plain :app", "--dry-run --console=plain :app"),
            "short dry run": ("--console=plain :app", "-m --console=plain :app"),
            "excluded task": ("--console=plain :app", f"--console=plain -x {tasks} :app"),
            "extra task": (":app:connectedDebugAndroidTest", ":app:connectedDebugAndroidTest :app:assembleRelease"),
            "echo for gradle": ("./gradlew --console=plain", "echo --console=plain"),
            "semicolon for &&": ("cd .. && ./gradlew", "cd .. ; ./gradlew"),
            "fallback exits 0": ("; false)", ")"),
            "fallback exit 0 at the end": ("; false)", "; exit 0)"),
            "fallback exit 0 first": ("(find core", "(exit 0; find core"),
            "second fallback": ("; false)", "; false) || (true)"),
            "|| true": (tasks, tasks + " || true"),
            "trailing true": ('; false)"', '; false)" ; true'),
            "trailing pipe": ('; false)"', '; false)" | tee /dev/null'),
            "block scalar": ("script: cd firebase", "script: |\n            cd firebase"),
            "runner swapped for another action": ("reactivecircus/android-emulator-runner@", "actions/checkout@"),
            "pre-emulator-launch-script": ("          target: google_apis\n", "          target: google_apis\n          pre-emulator-launch-script: x\n"),
            "extra step": ("      - name: enable KVM\n", "      - run: printf x > gradlew\n      - name: enable KVM\n"),
            "quoted if on the runner": ("        with:\n          api-level", '        "if": false\n        with:\n          api-level'),
            "if on a step": ("      - name: enable KVM\n", "      - name: enable KVM\n        if: github.event_name == 'push'\n"),
            "continue-on-error": ("      - name: enable KVM\n", "      - name: enable KVM\n        continue-on-error: true\n"),
            "needs a skipped job": ("  ui:\n    name: ui\n", "  ui:\n    name: ui\n    needs: [never]\n"),
            "quoted if on the job": ("  ui:\n    name: ui\n", "  ui:\n    name: ui\n    'if': false\n"),
            "no npm ci": ("run: npm ci --ignore-scripts --silent\n      - name: enable KVM", "run: npm install --silent\n      - name: enable KVM"),
            "npm ci runs install scripts": (
                "run: npm ci --ignore-scripts --silent\n      - name: enable KVM", "run: npm ci --silent\n      - name: enable KVM"),
            "no ui job": ("  ui:\n    name: ui\n", "  ui2:\n    name: ui\n"),
        }
        for name, (old, new) in mutations.items():
            with self.subTest(name):
                shutil.copy(ROOT / CI, self.root / CI)
                self.assertEqual(self.mutated(CI, old, new), [c.UI_PROBLEM])

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

    def test_the_data_module_must_apply_the_android_library_convention(self):
        # M1-68 part B: :core:testing and the JUnit Platform come from the convention plugin, not the module build file.
        for new in ("alias(libs.plugins.android.library)", "// alias(libs.plugins.tally.android.library)",
                    "alias(libs.plugins.listicles.android.library)"):
            with self.subTest(new):
                shutil.copy(ROOT / BUILD, self.root / BUILD)
                got = self.mutated(BUILD, "alias(libs.plugins.tally.android.library)", new)
                self.assertEqual(got, [c.CONVENTION_PROBLEM])

    def test_the_plugin_must_put_the_test_support_module_on_every_unit_test_classpath(self):
        for old, new in (('dependencies.add("testImplementation", ', '// dependencies.add("testImplementation", '),
                         ('dependencies.add("testImplementation", ', 'dependencies.add("implementation", '),
                         ('TEST_SUPPORT = ":core:testing"', 'TEST_SUPPORT = ":core:other"')):
            with self.subTest(new):
                shutil.copy(ROOT / PLUGIN, self.root / PLUGIN)
                self.assertEqual(self.mutated(PLUGIN, old, new), [c.CLASSPATH_PROBLEM])

    def test_the_plugin_must_run_unit_tests_on_the_junit_platform(self):
        # R1-02: the :core:testing network block is a JUnit Platform listener; on Gradle's JUnit 4 runner it never installs.
        for old, new in (("useJUnitPlatform()", "useJUnit()"), ("useJUnitPlatform()", "// useJUnitPlatform()")):
            with self.subTest(new):
                shutil.copy(ROOT / PLUGIN, self.root / PLUGIN)
                self.assertEqual(self.mutated(PLUGIN, old, new), [c.JUNIT_PROBLEM])

    def test_a_module_level_junit_line_does_not_stand_in_for_the_plugin(self):
        # M1-68 part B: the old :core:data form, as it was or weakened, does not count; only the plugin's call does.
        self.mutated(PLUGIN, "        useJUnitPlatform()\n", "")
        build = self.root / BUILD
        build.write_text(build.read_text() + "android { testOptions { unitTests.all { it.useJUnitPlatform() } } }\n")
        self.assertEqual(c.problems(self.root), [c.JUNIT_PROBLEM])
        for old, new in (("useJUnitPlatform", "useJUnit"), ("unitTests.all {", "// unitTests.all {")):
            with self.subTest(new):
                self.assertEqual(self.mutated(BUILD, old, new), [c.JUNIT_PROBLEM])

    def test_the_smoke_test_must_exist_and_have_a_test(self):
        got = self.mutated(SMOKE, "@Test", "// not a test", count=3)
        self.assertEqual(got, ["core/data androidTest has no @Test that talks to the emulators (EmulatorSmokeTest)"])


if __name__ == "__main__":
    unittest.main()
