"""Tests for M0.5-08: the Firebase rules tests are strict TypeScript (tsc --noEmit), linted by ESLint strictTypeChecked and
formatted by Prettier, all three wired into scripts/verify.sh and the existing `firebase` job of ci.yml.
Wiring and config have negative cases; the behaviour tests run the real tools on deliberate violations and check that each
fails for the right reason, and on clean code and check that it passes. Needs `npm ci` in firebase/ first.
Run: python3 -I scripts/test_firebase_ts.py"""

import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest

import yaml

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
FB = os.path.join(ROOT, "firebase")
BIN = os.path.join(FB, "node_modules", ".bin")
EXACT = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
REQUIRED_DEV = {
    "@eslint/js", "@firebase/rules-unit-testing", "@types/jest", "@types/node", "eslint", "firebase", "firebase-tools", "jest",
    "prettier", "ts-jest", "typescript", "typescript-eslint",
}
SCRIPTS = {
    "typecheck": "tsc --noEmit -p tsconfig.json",
    "lint": "eslint --max-warnings 0 .",
    "format:check": "prettier --check .",
}
# Every verify.sh step and CI step this task adds. verify.sh runs them in this order: install first, the rules emulator test last.
NPM = "bash -c 'cd firebase && npm {} --silent'"
VERIFY = [NPM.format(c) for c in ("ci", "run typecheck", "run lint", "run format:check")] + ["python3 -I scripts/test_firebase_ts.py", NPM.format("test")]
CI = ["npm ci --silent", "npm run typecheck --silent", "npm run lint --silent", "npm run format:check --silent", "npm test --silent"]
CI_ROOT_CMD = "python3 -I scripts/test_firebase_ts.py"
# Dependabot ignores these npm packages in /firebase, and nothing else: semver-major only. typescript: TypeScript 7 is not supported by
# ts-jest (typescript <7) or typescript-eslint (typescript <6.1). @types/node: 26 declares APIs that the Node 22 used in CI lacks.
# firebase is NOT ignored: firebase, @firebase/rules-unit-testing and the Temporal lib in tsconfig were bumped together (issue 106).
MAJOR = ["version-update:semver-major"]
ALL_TYPES = ["version-update:semver-major", "version-update:semver-minor", "version-update:semver-patch"]
IGNORE_POLICY = {"typescript": MAJOR, "@types/node": MAJOR}
# tsconfig compilerOptions allowlist: anything else (skipLibCheck, strict: false, a lone strict flag turned off) is a problem.
TS_OPTIONS = {"target", "lib", "module", "strict", "noEmit", "types", "noUncheckedIndexedAccess", "noImplicitOverride", "noImplicitReturns"}
# firebase 13 declarations reference the Temporal namespace, which TypeScript 6 provides only through lib esnext.temporal. Setting lib
# replaces the default libs, so dom and dom.iterable (the default for target es2022, which firebase's types need) are listed too.
TS_LIB = ["es2022", "dom", "dom.iterable", "esnext.temporal"]
CLEAN_TS = 'export function add(a: number, b: number): number {\n    return a + b;\n}\n'
# Each violation must fail tsc and name its error code.
TSC_VIOLATIONS = {
    "TS2322": 'export const n: number = "not a number";\n',
    "TS7006": "export function f(x) {\n    return x;\n}\n",
    "TS18047": "export function f(s: string | null): number {\n    return s.length;\n}\n",
    "TS2532": "export function f(a: number[]): number {\n    return a[0] + 1;\n}\n",
}
# One strictTypeChecked rule each; recommended-only configs would miss the last four.
ESLINT_VIOLATIONS = {
    "@typescript-eslint/no-explicit-any": "export const x: any = 1;\n",
    "@typescript-eslint/no-floating-promises": "export function f(): void {\n    Promise.resolve(1);\n}\n",
    "@typescript-eslint/no-non-null-assertion": "export function f(s: string | null): number {\n    return s!.length;\n}\n",
    "@typescript-eslint/no-unnecessary-condition": "export function f(s: string): boolean {\n    return s === undefined;\n}\n",
    "@typescript-eslint/restrict-template-expressions": "export function f(o: object): string {\n    return `${o}`;\n}\n",
    "@typescript-eslint/no-unsafe-assignment": "export function f(j: string): number {\n    const v = JSON.parse(j);\n    return v;\n}\n",
}
PRETTIER_BAD = "export const a = {b:1,\n  c:2};\n"


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


def active_lines(text):
    return [ln.strip() for ln in text.splitlines() if ln.strip() and not ln.strip().startswith("#")]


def runs(text, command):
    """True if an active line is exactly the command as a verify.sh `step <name> <cmd>` or a workflow `run: <cmd>`."""
    pattern = re.compile(rf"^(?:step\s+[\w-]+\s+|(?:-\s+)?run:\s+){re.escape(command)}$")
    return any(pattern.match(ln) for ln in active_lines(text))


def top_level_step(text, command):
    """Like runs(), but the line must not be indented, so a step moved into the --fast branch does not count."""
    return runs("\n".join(ln for ln in text.splitlines() if ln == ln.lstrip()), command)


def job(text, name):
    m = re.search(rf"^  {re.escape(name)}:\n(.*?)(?=^  [A-Za-z][\w-]*:\n|\Z)", text, re.S | re.M)
    return m.group(1) if m else None


def ordered(text, commands):
    """True if every command is an active step and they appear in the given order."""
    lines = active_lines(text)
    at = -1
    for cmd in commands:
        hits = [i for i, ln in enumerate(lines) if i > at and re.match(rf"^(?:step\s+[\w-]+\s+|(?:-\s+)?run:\s+){re.escape(cmd)}$", ln)]
        if not hits:
            return False
        at = hits[0]
    return True


def dependabot_ignore_problems(cfg, policy=IGNORE_POLICY):
    """Problems with the ignore rules of the npm entry for /firebase: each package in `policy` must have exactly one rule that
    ignores exactly the listed update types (a version-specific rule is no substitute), and no other package may be ignored."""
    entries = [e for e in cfg.get("updates", []) if e.get("package-ecosystem") == "npm" and e.get("directory") == "/firebase"]
    if len(entries) != 1:
        return [f"expected one npm entry for /firebase, found {len(entries)}"]
    problems = []
    seen = []
    for rule in entries[0].get("ignore", []):
        name = rule.get("dependency-name")
        seen.append(name)
        if name not in policy:
            problems.append(f"{name} must not be ignored")
        elif rule != {"dependency-name": name, "update-types": policy[name]}:
            problems.append(f"{name} must be ignored for {policy[name]} only, got {rule}")
    problems += [f"{name} has no ignore rule" for name in policy if seen.count(name) == 0]
    problems += [f"{name} has {seen.count(name)} ignore rules" for name in policy if seen.count(name) > 1]
    return problems


def tsconfig_problems(cfg):
    problems = []
    opts = cfg.get("compilerOptions", {})
    if opts.get("strict") is not True:
        problems.append("strict is not true")
    if opts.get("noEmit") is not True:
        problems.append("noEmit is not true")
    if opts.get("noUncheckedIndexedAccess") is not True:
        problems.append("noUncheckedIndexedAccess is not true")
    if opts.get("lib") != TS_LIB:
        problems.append(f"lib is {opts.get('lib')!r}, expected {TS_LIB!r}")
    extra = set(opts) - TS_OPTIONS
    if extra:
        problems.append(f"compilerOptions keys outside the allowlist: {sorted(extra)}")
    if cfg.get("include") != ["**/*.ts"]:
        problems.append(f"include is {cfg.get('include')!r}")
    if cfg.get("exclude") != ["node_modules"]:
        problems.append(f"exclude is {cfg.get('exclude')!r}")
    if set(cfg) - {"compilerOptions", "include", "exclude"}:
        problems.append(f"top-level keys are {sorted(cfg)}")
    return problems


def tool(name, *args, cwd=FB):
    done = subprocess.run([os.path.join(BIN, name), *args], cwd=cwd, capture_output=True, text=True, check=False)
    return done.returncode, done.stdout + done.stderr


class Fixture:
    """A throwaway directory inside firebase/ (so the project tsconfig, ESLint and Prettier configs apply) holding one TypeScript file."""

    def __init__(self, source):
        self.dir = tempfile.mkdtemp(prefix="fixture-tmp-", dir=FB)
        self.file = os.path.join(self.dir, "sample.ts")
        with open(self.file, "w", encoding="utf-8") as f:
            f.write(source)
        with open(os.path.join(self.dir, "tsconfig.json"), "w", encoding="utf-8") as f:
            json.dump({"extends": "../tsconfig.json", "include": ["./*.ts"], "exclude": []}, f)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        shutil.rmtree(self.dir, ignore_errors=True)


def tsc(source):
    with Fixture(source) as fx:
        return tool("tsc", "--noEmit", "-p", os.path.join(fx.dir, "tsconfig.json"))


def eslint(source):
    with Fixture(source) as fx:
        return tool("eslint", "--max-warnings", "0", fx.file)


def prettier(source):
    with Fixture(source) as fx:
        return tool("prettier", "--check", fx.file)


class HelperNegativeCases(unittest.TestCase):
    def test_commented_out_or_masked_command_does_not_count(self):
        cmd = "bash -c 'cd firebase && npm run typecheck --silent'"
        self.assertFalse(runs(f"# step t {cmd}\n", cmd))
        self.assertFalse(runs(f"step t {cmd} || true\n", cmd))
        self.assertFalse(runs(f"      - run: {cmd} ; true\n", cmd))
        self.assertTrue(runs(f"step t {cmd}\n", cmd))
        self.assertTrue(runs(f"        run: {cmd}\n", cmd))

    def test_step_in_a_branch_is_not_top_level(self):
        self.assertFalse(top_level_step('if [ "$FAST" = 0 ]; then\n  step t python3 -I x.py\nfi\n', "python3 -I x.py"))
        self.assertTrue(top_level_step("step t python3 -I x.py\n", "python3 -I x.py"))

    def test_order_matters(self):
        self.assertTrue(ordered("step a one\nstep b two\n", ["one", "two"]))
        self.assertFalse(ordered("step b two\nstep a one\n", ["one", "two"]))
        self.assertFalse(ordered("step a one\n", ["one", "two"]))

    def test_dependabot_check_rejects_a_missing_wrong_or_misplaced_ignore(self):
        major, minor, patch = ALL_TYPES[0], ALL_TYPES[1], ALL_TYPES[2]

        def rule(name, types=None):
            return {"dependency-name": name, "update-types": list(types or IGNORE_POLICY.get(name, MAJOR))}

        def cfg(rules, eco="npm", directory="/firebase"):
            return {"updates": [{"package-ecosystem": eco, "directory": directory, "ignore": rules}]}

        ts, node = rule("typescript"), rule("@types/node")
        fb = rule("firebase", ALL_TYPES)
        full = [ts, node]
        self.assertEqual(dependabot_ignore_problems(cfg(full)), [])
        bad = {
            "no ignore": {"updates": [{"package-ecosystem": "npm", "directory": "/firebase"}]},
            "typescript missing": cfg([node]),
            "@types/node missing": cfg([ts]),
            "extra package": cfg([*full, rule("eslint")]),
            "firebase-tools ignored for major": cfg([*full, rule("firebase-tools", (major,))]),
            "firebase-tools ignored for all": cfg([*full, rule("firebase-tools", ALL_TYPES)]),
            "firebase ignored for all": cfg([*full, fb]),
            "firebase ignored for major only": cfg([*full, rule("firebase", (major,))]),
            "firebase ignored for minor and patch": cfg([*full, rule("firebase", (minor, patch))]),
            "firebase version ignore": cfg([*full, {"dependency-name": "firebase", "versions": [">=12.19.0"]}]),
            "@firebase/rules-unit-testing ignored": cfg([*full, rule("@firebase/rules-unit-testing", ALL_TYPES)]),
            "@types/node minor and patch": cfg([ts, rule("@types/node", (minor, patch))]),
            "@types/node ignored for all": cfg([ts, rule("@types/node", ALL_TYPES)]),
            "@types/node no update types": cfg([ts, {"dependency-name": "@types/node"}]),
            "typescript ignored for all": cfg([rule("typescript", ALL_TYPES), node]),
            "typescript minor only": cfg([rule("typescript", (minor,)), node]),
            "typescript version ignore": cfg([{"dependency-name": "typescript", "versions": [">=7"]}, node]),
            "typescript twice": cfg([*full, ts]),
            "other directory": cfg(full, directory="/"),
            "other ecosystem": cfg(full, eco="pip"),
        }
        for name, c in bad.items():
            with self.subTest(name):
                self.assertNotEqual(dependabot_ignore_problems(c), [])

    def test_tsconfig_allowlist_rejects_every_weakening(self):
        good = {
            "compilerOptions": {"strict": True, "noEmit": True, "noUncheckedIndexedAccess": True, "lib": TS_LIB, "types": ["jest"]},
            "include": ["**/*.ts"],
            "exclude": ["node_modules"],
        }
        self.assertEqual(tsconfig_problems(good), [])
        opts = good["compilerOptions"]
        mutations = {
            "strict off": {**good, "compilerOptions": {**opts, "strict": False}},
            "strict missing": {**good, "compilerOptions": {k: v for k, v in opts.items() if k != "strict"}},
            "noImplicitAny off": {**good, "compilerOptions": {**opts, "noImplicitAny": False}},
            "skipLibCheck": {**good, "compilerOptions": {**opts, "skipLibCheck": True}},
            "allowJs": {**good, "compilerOptions": {**opts, "allowJs": True}},
            "noEmit off": {**good, "compilerOptions": {**opts, "noEmit": False}},
            "no unchecked access flag": {**good, "compilerOptions": {k: v for k, v in opts.items() if k != "noUncheckedIndexedAccess"}},
            "lib missing": {**good, "compilerOptions": {k: v for k, v in opts.items() if k != "lib"}},
            "lib without temporal": {**good, "compilerOptions": {**opts, "lib": ["es2022", "dom", "dom.iterable"]}},
            "lib without dom": {**good, "compilerOptions": {**opts, "lib": ["es2022", "esnext.temporal"]}},
            "lib with extra entry": {**good, "compilerOptions": {**opts, "lib": [*TS_LIB, "esnext"]}},
            "narrow include": {**good, "include": ["test/other.ts"]},
            "wider exclude": {**good, "exclude": ["node_modules", "test"]},
            "files": {**good, "files": ["a.ts"]},
        }
        for name, cfg in mutations.items():
            with self.subTest(name):
                self.assertNotEqual(tsconfig_problems(cfg), [])


class Config(unittest.TestCase):
    def test_dependencies_are_pinned_exactly_and_complete(self):
        dev = json.loads(read("firebase", "package.json"))["devDependencies"]
        self.assertEqual(REQUIRED_DEV - set(dev), set())
        for name, version in dev.items():
            self.assertRegex(version, EXACT, name)
        # ts-jest declares typescript >=4.3 <7 and typescript-eslint <6.1: the TypeScript major is 6, not the current 7.
        self.assertTrue(dev["typescript"].startswith("6."), dev["typescript"])

    def test_scripts_are_exactly_the_agreed_commands(self):
        scripts = json.loads(read("firebase", "package.json"))["scripts"]
        for name, command in SCRIPTS.items():
            self.assertEqual(scripts.get(name), command, name)
        self.assertIn("jest --runInBand", scripts["test"])
        self.assertTrue(scripts["test"].startswith("firebase emulators:exec --only firestore --project demo-listicles"))

    def test_tsconfig_is_strict(self):
        self.assertEqual(tsconfig_problems(json.loads(read("firebase", "tsconfig.json"))), [])

    def test_eslint_config_uses_strict_type_checked_and_turns_nothing_off(self):
        text = read("firebase", "eslint.config.mjs")
        self.assertIn("strictTypeChecked", text)
        self.assertIn("projectService", text)
        self.assertIn("@typescript-eslint/consistent-type-assertions", text)
        self.assertRegex(text, r'assertionStyle:\s*"never"')
        for word in ('"off"', "'off'", '"warn"', "'warn'", "ignores", "disable", "reportUnused"):
            self.assertNotIn(word, text, word)

    def test_prettier_config_is_only_the_print_width(self):
        self.assertEqual(json.loads(read("firebase", ".prettierrc.json")), {"printWidth": 100})
        self.assertFalse(os.path.exists(os.path.join(FB, ".prettierignore")))

    def test_jest_runs_typescript_through_ts_jest(self):
        text = read("firebase", "jest.config.cjs")
        self.assertIn("ts-jest", text)
        self.assertNotIn("isolatedModules", text)
        self.assertNotIn("diagnostics", text)
        for word in ("testMatch", "testPathIgnorePatterns", "testRegex", "modulePathIgnorePatterns"):
            self.assertNotIn(word, text, word)

    def test_javascript_rules_test_is_gone_and_the_typescript_one_keeps_every_case(self):
        self.assertFalse(os.path.exists(os.path.join(FB, "test", "rules.test.js")))
        text = read("firebase", "test", "rules.test.ts")
        for path in ("users/alice", "households/h1", "households/h1/members/alice", "households/h1/lists/l1",
                     "households/h1/lists/l1/items/i1", "households/h1/invites/inv1", "anything/else"):
            self.assertIn(f'"{path}"', text, path)
        for case in ("anonymous", "signed-in", "default deny (%s)", "%s: get", "%s: create/overwrite",
                     "%s: update and delete an existing doc", "list and add on a collection"):
            self.assertIn(case, text, case)
        self.assertEqual(len(re.findall(r"assertFails\(", text)), 6)

    def test_dependabot_ignores_only_the_major_updates_of_typescript_and_types_node_and_no_firebase_update(self):
        self.assertEqual(dependabot_ignore_problems(yaml.safe_load(read(".github", "dependabot.yml"))), [])

    def test_fixture_directories_are_gitignored(self):
        self.assertIn("firebase/fixture-tmp-*/", active_lines(read(".gitignore")))


class VerifyAndCiWiring(unittest.TestCase):
    def test_verify_runs_install_checks_tests_and_rules_in_order_even_in_fast_mode(self):
        verify = read("scripts", "verify.sh")
        for cmd in VERIFY[:5]:
            self.assertTrue(top_level_step(verify, cmd), cmd)
        self.assertTrue(ordered(verify, VERIFY), "steps missing or out of order")

    def test_rules_emulator_step_alone_may_be_skipped(self):
        verify = read("scripts", "verify.sh")
        self.assertRegex(verify, r'if \[ "\$\{SKIP_FIREBASE:-0\}" = 1 \]; then\n[^\n]*\n(?:else|fi)')
        self.assertTrue(runs(verify.split('SKIP_FIREBASE:-0}" = 1 ]')[1], VERIFY[5]))

    def test_ci_firebase_job_runs_each_check_in_order_in_the_firebase_directory(self):
        body = job(read(".github", "workflows", "ci.yml"), "firebase")
        self.assertIsNotNone(body, "ci.yml needs its firebase job")
        for cmd in CI:
            self.assertTrue(runs(body, cmd), cmd)
        self.assertTrue(ordered(body, CI), "steps missing or out of order")
        self.assertTrue(runs(body, CI_ROOT_CMD))
        self.assertNotRegex(body, r"(?m)^\s*if:")
        self.assertNotIn("continue-on-error", body)
        self.assertNotIn("|| true", body)

    def test_ci_has_no_new_job_and_keeps_the_required_check_names(self):
        text = read(".github", "workflows", "ci.yml")
        for name in ("wrapper", "static", "unit", "firebase", "ui", "guards", "secrets", "tasks"):
            self.assertIsNotNone(job(text, name), name)
            self.assertRegex(text, rf"(?m)^    name: {name}$")


class Behaviour(unittest.TestCase):
    def test_clean_code_passes_all_three_tools(self):
        for name, run in (("tsc", tsc), ("eslint", eslint), ("prettier", prettier)):
            with self.subTest(name):
                code, out = run(CLEAN_TS)
                self.assertEqual(code, 0, out)

    def test_each_type_error_fails_tsc_with_its_code(self):
        for code_name, source in TSC_VIOLATIONS.items():
            with self.subTest(code=code_name):
                code, out = tsc(source)
                self.assertNotEqual(code, 0, out)
                self.assertIn(code_name, out)

    def test_each_strict_type_checked_violation_fails_eslint_with_its_rule(self):
        for rule, source in ESLINT_VIOLATIONS.items():
            with self.subTest(rule=rule):
                code, out = eslint(source)
                self.assertNotEqual(code, 0, out)
                self.assertIn(rule, out)

    def test_type_assertions_are_rejected_in_both_syntaxes(self):
        rule = "@typescript-eslint/consistent-type-assertions"
        angle = "export function f(x: unknown): number {\n    return <number>x;\n}\n"
        as_form = "export function f(x: unknown): number {\n    return x as number;\n}\n"
        for name, source in (("angle bracket", angle), ("as", as_form)):
            with self.subTest(name):
                code, out = eslint(source)
                self.assertNotEqual(code, 0, out)
                self.assertIn(rule, out)
        self.assertEqual(tsc(angle)[0], 0, "tsc alone accepts the angle-bracket assertion, so only ESLint can reject it")

    def test_unformatted_code_fails_prettier(self):
        code, out = prettier(PRETTIER_BAD)
        self.assertNotEqual(code, 0, out)

    def test_the_project_itself_passes_all_three(self):
        for args in (("tsc", "--noEmit", "-p", "tsconfig.json"), ("eslint", "--max-warnings", "0", "."), ("prettier", "--check", ".")):
            with self.subTest(tool=args[0]):
                code, out = tool(*args)
                self.assertEqual(code, 0, out)


class NoLeftovers(unittest.TestCase):
    """Alphabetical class order puts this after Behaviour, which creates the fixture directories."""
    def test_no_fixture_directory_is_left_behind(self):
        self.assertEqual([d for d in os.listdir(FB) if d.startswith("fixture-tmp-")], [])


if __name__ == "__main__":
    unittest.main()
