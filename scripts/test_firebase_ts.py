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
COOLDOWN_ECOSYSTEMS = ("gradle", "npm", "pip", "github-actions")
COOLDOWN_DAYS = 7
REQUIRED_DEV = {
    "@eslint/js", "@firebase/rules-unit-testing", "@types/jest", "@types/node", "eslint", "firebase", "firebase-tools", "jest",
    "prettier", "semver", "ts-jest", "typescript", "typescript-eslint",
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
# firebase and @firebase/rules-unit-testing: firebase 13 and rules-unit-testing 6 need Node >=24.12 (CI runs Node 22), so their majors
# wait for the Node 24 follow-up (issue 161); minor and patch updates flow, grouped so both packages move in one PR.
MAJOR = ["version-update:semver-major"]
ALL_TYPES = ["version-update:semver-major", "version-update:semver-minor", "version-update:semver-patch"]
IGNORE_POLICY = {"typescript": MAJOR, "firebase": MAJOR, "@firebase/rules-unit-testing": MAJOR, "@types/node": MAJOR}
# One Dependabot group holds exactly these two packages, ahead of the catch-all npm-minor-patch group (a dependency joins the first group
# it matches), for every update type: their peer ranges are tied (rules-unit-testing N needs firebase ^N), so they must arrive together.
SDK_GROUP = "firebase-sdk"
SDK_PATTERNS = ["firebase", "@firebase/rules-unit-testing"]
# tsconfig compilerOptions allowlist: anything else (skipLibCheck, strict: false, a lone strict flag turned off) is a problem.
# isolatedModules must be true (issue 210 item 7): with module nodenext ts-jest warns TS151002 on every run unless it compiles each file
# on its own. ts-jest then only transpiles; tsc --noEmit, which verify.sh and CI run before Jest, stays the type check.
TS_OPTIONS = {
    "target", "lib", "module", "strict", "noEmit", "types", "noUncheckedIndexedAccess", "noImplicitOverride", "noImplicitReturns",
    "isolatedModules",
}
# firebase 12.19 and later declarations reference the Temporal namespace, which TypeScript 6 provides only through lib esnext.temporal.
# Setting lib replaces the default (lib.es2022.full: es2022, dom, dom.iterable, dom.asynciterable, webworker.importscripts, scripthost),
# so the list is the subset of that default that firebase's types need (es2022, dom, dom.iterable), plus esnext.temporal.
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


REQUIRED_CHECKS = (
    "wrapper", "static", "unit", "firebase", "ui", "screenshots", "guards", "secrets", "tasks", "python-lint", "workflow-lint",
)  # kept in sync with the ruleset on main (docs/BRANCH-PROTECTION.md sections 2 and 6; issue 184)


def documented_checks(text):
    """The check names in the first "Required checks (N): `a`, `b`, ..." line (or the PLAN item 6 list), sorted."""
    m = re.search(r"(?:Required checks \(\d+\):|all \d+ checks green \()([^.;]*?)(?:;|\.|\))", text, re.S)
    return sorted(set(re.findall(r"`([a-z][a-z-]*)`", m.group(1)))) if m else []


def documented_count(text):
    """The N in "Required checks (N):" or "all N checks green", or None."""
    m = re.search(r"(?:Required checks \(|all )(\d+)(?:\)| checks green)", text)
    return int(m.group(1)) if m else None


def plan_item4_checks(text):
    """Check names that open a bullet in PLAN section 5 item 4 (the CI list)."""
    m = re.search(r"(?ms)^4\. \*\*CI \(GitHub Actions\).*?(?=^5\. )", text)
    return sorted(set(re.findall(r"(?m)^   \* `([a-z][a-z-]*)`", m.group(0)))) if m else []


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


def dependabot_cooldown_problems(cfg, ecosystems=COOLDOWN_ECOSYSTEMS, days=COOLDOWN_DAYS):
    """Problems with the cooldown (issue 186): every update entry, and every ecosystem in `ecosystems`, must delay a new release by at
    least `days` days (a whole number) through cooldown.default-days. Security updates are not delayed by cooldown."""
    updates = cfg.get("updates", [])
    problems = [f"no update entry for {eco}" for eco in ecosystems if not any(u.get("package-ecosystem") == eco for u in updates)]
    for u in updates:
        where = f"{u.get('package-ecosystem')} {u.get('directory')}"
        got = (u.get("cooldown") or {}).get("default-days")
        if not isinstance(got, int) or isinstance(got, bool) or got < days:
            problems.append(f"{where}: cooldown.default-days must be a whole number >= {days}, got {got!r}")
    return problems


def dependabot_group_problems(cfg):
    """Problems with the groups of the npm entry for /firebase: the SDK group holds exactly SDK_PATTERNS for every update type, and
    comes before every other group, because a dependency joins the first group that matches it."""
    entries = [e for e in cfg.get("updates", []) if e.get("package-ecosystem") == "npm" and e.get("directory") == "/firebase"]
    if len(entries) != 1:
        return [f"expected one npm entry for /firebase, found {len(entries)}"]
    groups = entries[0].get("groups") or {}
    if SDK_GROUP not in groups:
        return [f"no {SDK_GROUP} group"]
    problems = []
    group = groups[SDK_GROUP]
    if group.get("patterns") != SDK_PATTERNS:
        problems.append(f"{SDK_GROUP} patterns are {group.get('patterns')!r}, expected {SDK_PATTERNS!r}")
    if group.get("update-types") not in (None, ALL_TYPES, ["major", "minor", "patch"]):
        problems.append(f"{SDK_GROUP} update-types are {group.get('update-types')!r}, expected all of major, minor and patch")
    if set(group) - {"patterns", "update-types"}:
        problems.append(f"{SDK_GROUP} has keys {sorted(group)}")
    if list(groups)[0] != SDK_GROUP:
        problems.append(f"{SDK_GROUP} must be the first group, order is {list(groups)}")
    return problems


def ci_node_version(workflow_text):
    """The Node the CI firebase job's setup-node installs, as a concrete version to test engines against, or None when it cannot be
    resolved. A bare major (`22`) means the newest 22.x, so it maps to major.999.999 (engines ranges are lower bounds in practice)."""
    body = job(workflow_text, "firebase")
    m = body and re.search(r"^\s+node-version:\s*[\"']?([^\s\"'#]+)", body, re.M)
    if not m:
        return None
    value = m.group(1)
    if re.fullmatch(r"\d+(?:\.x)?", value):
        return value.split(".")[0] + ".999.999"
    return value if re.fullmatch(r"\d+\.\d+\.\d+", value) else None


ENGINES_JS = (
    "const semver = require('semver'); const lock = JSON.parse(require('fs').readFileSync(0, 'utf8')); const node = process.argv[1];"
    "const bad = Object.entries(lock.packages ?? {}).flatMap(([name, pkg]) => { const range = pkg.engines?.node;"
    "return range !== undefined && !semver.satisfies(node, range) ? [name + ' ' + range] : []; });"
    "console.log(JSON.stringify(bad));"
)


def lockfile_engine_offenders(lock, node_version):
    """Packages in a package-lock (as a dict) whose engines.node range excludes node_version, as `name range` strings."""
    done = subprocess.run(["node", "-e", ENGINES_JS, node_version], cwd=FB, input=json.dumps(lock), capture_output=True, text=True, check=False)
    assert done.returncode == 0, done.stdout + done.stderr
    return json.loads(done.stdout)


def tsconfig_problems(cfg):
    problems = []
    opts = cfg.get("compilerOptions", {})
    if opts.get("strict") is not True:
        problems.append("strict is not true")
    if opts.get("noEmit") is not True:
        problems.append("noEmit is not true")
    if opts.get("noUncheckedIndexedAccess") is not True:
        problems.append("noUncheckedIndexedAccess is not true")
    if opts.get("isolatedModules") is not True:
        problems.append("isolatedModules is not true")
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
    """A throwaway directory inside firebase/ (so the project tsconfig, ESLint and Prettier configs apply) holding one TypeScript file.
    `options` are compilerOptions laid over the project's."""

    def __init__(self, source, name="sample.ts", options=None):
        self.dir = tempfile.mkdtemp(prefix="fixture-tmp-", dir=FB)
        self.file = os.path.join(self.dir, name)
        with open(self.file, "w", encoding="utf-8") as f:
            f.write(source)
        with open(os.path.join(self.dir, "tsconfig.json"), "w", encoding="utf-8") as f:
            json.dump({"extends": "../tsconfig.json", "include": ["./*.ts"], "exclude": [], "compilerOptions": options or {}}, f)

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


def jest(options=None):
    """Jest with the project's jest.config.cjs (preset ts-jest) on one passing test, as npm test runs it but without the emulator, and
    without the cache, so ts-jest compiles (and would warn) on every run."""
    with Fixture('export {};\n\ntest("adds", () => {\n    expect(1 + 1).toBe(2);\n});\n', "sample.test.ts", options) as fx:
        return tool("jest", "--no-cache", "--rootDir", fx.dir)


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
        fb, rut = rule("firebase"), rule("@firebase/rules-unit-testing")
        full = [ts, fb, rut, node]
        self.assertEqual(dependabot_ignore_problems(cfg(full)), [])
        bad = {
            "no ignore": {"updates": [{"package-ecosystem": "npm", "directory": "/firebase"}]},
            "typescript missing": cfg([fb, rut, node]),
            "firebase missing": cfg([ts, rut, node]),
            "rules-unit-testing missing": cfg([ts, fb, node]),
            "@types/node missing": cfg([ts, fb, rut]),
            "extra package": cfg([*full, rule("eslint")]),
            "firebase-tools ignored for major": cfg([*full, rule("firebase-tools", (major,))]),
            "firebase-tools ignored for all": cfg([*full, rule("firebase-tools", ALL_TYPES)]),
            "firebase ignored for all": cfg([ts, rule("firebase", ALL_TYPES), rut, node]),
            "firebase ignored for minor only": cfg([ts, rule("firebase", (minor,)), rut, node]),
            "firebase minor and patch frozen": cfg([ts, rule("firebase", (minor, patch)), rut, node]),
            "firebase version ignore": cfg([ts, {"dependency-name": "firebase", "versions": [">=13.0.0"]}, rut, node]),
            "firebase version ignore beside major": cfg([*full, {"dependency-name": "firebase", "versions": [">=12.19.0"]}]),
            "rules-unit-testing ignored for all": cfg([ts, fb, rule("@firebase/rules-unit-testing", ALL_TYPES), node]),
            "rules-unit-testing minor only": cfg([ts, fb, rule("@firebase/rules-unit-testing", (minor,)), node]),
            "@types/node minor and patch": cfg([ts, fb, rut, rule("@types/node", (minor, patch))]),
            "@types/node ignored for all": cfg([ts, fb, rut, rule("@types/node", ALL_TYPES)]),
            "@types/node no update types": cfg([ts, fb, rut, {"dependency-name": "@types/node"}]),
            "typescript ignored for all": cfg([rule("typescript", ALL_TYPES), fb, rut, node]),
            "typescript minor only": cfg([rule("typescript", (minor,)), fb, rut, node]),
            "typescript version ignore": cfg([{"dependency-name": "typescript", "versions": [">=7"]}, fb, rut, node]),
            "firebase twice": cfg([*full, fb]),
            "other directory": cfg(full, directory="/"),
            "other ecosystem": cfg(full, eco="pip"),
        }
        for name, c in bad.items():
            with self.subTest(name):
                self.assertNotEqual(dependabot_ignore_problems(c), [])

    def test_dependabot_group_check_rejects_a_missing_split_or_late_sdk_group(self):
        def cfg(groups, directory="/firebase"):
            return {"updates": [{"package-ecosystem": "npm", "directory": directory, "groups": groups}]}

        sdk = {"patterns": list(SDK_PATTERNS)}
        rest = {"update-types": ["minor", "patch"]}
        self.assertEqual(dependabot_group_problems(cfg({SDK_GROUP: sdk, "npm-minor-patch": rest})), [])
        self.assertEqual(dependabot_group_problems(cfg({SDK_GROUP: {**sdk, "update-types": ["major", "minor", "patch"]}, "npm-minor-patch": rest})), [])
        bad = {
            "no groups": {"updates": [{"package-ecosystem": "npm", "directory": "/firebase"}]},
            "no sdk group": cfg({"npm-minor-patch": rest}),
            "sdk group after the catch-all": cfg({"npm-minor-patch": rest, SDK_GROUP: sdk}),
            "firebase only": cfg({SDK_GROUP: {"patterns": ["firebase"]}, "npm-minor-patch": rest}),
            "rules-unit-testing only": cfg({SDK_GROUP: {"patterns": ["@firebase/rules-unit-testing"]}, "npm-minor-patch": rest}),
            "extra pattern": cfg({SDK_GROUP: {"patterns": [*SDK_PATTERNS, "firebase-tools"]}, "npm-minor-patch": rest}),
            "wildcard pattern": cfg({SDK_GROUP: {"patterns": ["*firebase*"]}, "npm-minor-patch": rest}),
            "minor and patch only": cfg({SDK_GROUP: {**sdk, "update-types": ["minor", "patch"]}, "npm-minor-patch": rest}),
            "major only": cfg({SDK_GROUP: {**sdk, "update-types": ["major"]}, "npm-minor-patch": rest}),
            "extra key": cfg({SDK_GROUP: {**sdk, "dependency-type": "development"}, "npm-minor-patch": rest}),
            "other directory": cfg({SDK_GROUP: sdk, "npm-minor-patch": rest}, directory="/"),
        }
        for name, c in bad.items():
            with self.subTest(name):
                self.assertNotEqual(dependabot_group_problems(c), [])

    def test_ci_node_version_is_read_from_the_firebase_job_only(self):
        def wf(version, job_name="firebase"):
            return f"jobs:\n  {job_name}:\n    steps:\n      - uses: actions/setup-node@x\n        with:\n          node-version: {version}\n"

        self.assertEqual(ci_node_version(wf("22")), "22.999.999")
        self.assertEqual(ci_node_version(wf("'24'")), "24.999.999")
        self.assertEqual(ci_node_version(wf("24.x")), "24.999.999")
        self.assertEqual(ci_node_version(wf("24.12.1")), "24.12.1")
        for bad in ("lts/*", "latest", "22.x.x", ">=22", "$NODE"):
            with self.subTest(bad):
                self.assertIsNone(ci_node_version(wf(bad)))
        self.assertIsNone(ci_node_version(wf("22", job_name="unit")), "another job's node-version must not count")
        self.assertIsNone(ci_node_version("jobs:\n  firebase:\n    steps: []\n"))

    def test_engines_check_rejects_a_lockfile_that_needs_a_newer_node(self):
        def lock(*ranges):
            return {"packages": {"": {"name": "x"}, **{f"node_modules/p{i}": {"engines": {"node": r}} for i, r in enumerate(ranges)}}}

        self.assertEqual(lockfile_engine_offenders(lock(">=20.0.0", "^22.13.0 || >=24", "18 || 20 || >=22"), "22.999.999"), [])
        self.assertEqual(lockfile_engine_offenders({"packages": {"node_modules/p": {"version": "1.0.0"}}}, "22.999.999"), [])
        # The case of PR 156 round 1: firebase 13 and rules-unit-testing 6 declare node >=24.12.0 while CI ran Node 22.
        self.assertEqual(lockfile_engine_offenders(lock(">=20.0.0", ">=24.12.0"), "22.999.999"), ["node_modules/p1 >=24.12.0"])
        self.assertEqual(lockfile_engine_offenders(lock(">=24.12.0"), "24.11.9"), ["node_modules/p0 >=24.12.0"])
        self.assertEqual(lockfile_engine_offenders(lock(">=24.12.0"), "24.12.0"), [])
        self.assertEqual(lockfile_engine_offenders(lock("^20.19.0 || ^22.13.0 || >=24"), "22.5.0"), ["node_modules/p0 ^20.19.0 || ^22.13.0 || >=24"])

    def test_tsconfig_allowlist_rejects_every_weakening(self):
        good = {
            "compilerOptions": {
                "strict": True, "noEmit": True, "noUncheckedIndexedAccess": True, "isolatedModules": True, "lib": TS_LIB, "types": ["jest"],
            },
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
            "isolatedModules off": {**good, "compilerOptions": {**opts, "isolatedModules": False}},
            "isolatedModules missing": {**good, "compilerOptions": {k: v for k, v in opts.items() if k != "isolatedModules"}},
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
        self.assertTrue(scripts["test"].startswith("firebase emulators:exec --only firestore --project demo-tally"))

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

    def test_javascript_rules_test_is_gone_and_the_typescript_suite_has_every_part(self):
        """M1-52 (see #202): every operation as each of three clients on the PLAN section 3 paths, the deny suite, the PLAN pin
        and the mutant check. npm test checks what they do; this also runs where that step is skipped (SKIP_FIREBASE)."""
        self.assertFalse(os.path.exists(os.path.join(FB, "test", "rules.test.js")))
        parts = {
            "harness.ts": ('export const CLIENT_NAMES = ["anonymous", "unverified", "verified"] as const;',
                           'export const OPS = ["get", "list", "group", "create", "update", "delete"] as const;',
                           "export const PATHS = [...TEMPLATES.map(instantiate), UNPLANNED];"),
            "rules.test.ts": ("expect(h.TEMPLATES).toEqual([", "await assertFails(h.attempt(admin.firestore(), dbs[client], probe));"),
            "mutants.test.ts": ("...h.methodMutants(h.UNPLANNED),", "h.mutate(h.RULES, mutant)", "expect(got).toEqual(want);"),
            "harness.test.ts": ("planTemplates throws on %s", "expected: %s", "a collection no probe touches"),
        }
        for name, needles in parts.items():
            lines = [ln for ln in read("firebase", "test", name).splitlines() if not ln.strip().startswith("//")]
            for needle in needles:
                with self.subTest(file=name, part=needle):
                    self.assertTrue(any(needle in ln for ln in lines), needle)

    def test_dependabot_ignores_only_the_major_updates_of_typescript_firebase_rules_unit_testing_and_types_node(self):
        self.assertEqual(dependabot_ignore_problems(yaml.safe_load(read(".github", "dependabot.yml"))), [])

    def test_dependabot_groups_firebase_and_rules_unit_testing_ahead_of_the_catch_all(self):
        self.assertEqual(dependabot_group_problems(yaml.safe_load(read(".github", "dependabot.yml"))), [])

    def test_dependabot_cooldown_check_rejects_a_missing_short_or_malformed_cooldown(self):
        base = [{"package-ecosystem": e, "directory": "/", "cooldown": {"default-days": 7}} for e in COOLDOWN_ECOSYSTEMS]
        self.assertEqual(dependabot_cooldown_problems({"updates": base}), [])
        self.assertEqual(dependabot_cooldown_problems({"updates": [*base[:3], {**base[3], "cooldown": {"default-days": 10}}]}), [])
        bad = {
            "no cooldown on one": {"updates": [*base[:3], {"package-ecosystem": "github-actions", "directory": "/"}]},
            "short": {"updates": [*base[:3], {**base[3], "cooldown": {"default-days": 6}}]},
            "zero": {"updates": [*base[:3], {**base[3], "cooldown": {"default-days": 0}}]},
            "string": {"updates": [*base[:3], {**base[3], "cooldown": {"default-days": "7"}}]},
            "bool": {"updates": [*base[:3], {**base[3], "cooldown": {"default-days": True}}]},
            "only semver keys": {"updates": [*base[:3], {**base[3], "cooldown": {"semver-major-days": 14}}]},
            "empty cooldown": {"updates": [*base[:3], {**base[3], "cooldown": {}}]},
            "ecosystem missing": {"updates": base[:3]},
            "no updates": {},
        }
        for name, c in bad.items():
            with self.subTest(name):
                self.assertNotEqual(dependabot_cooldown_problems(c), [])

    def test_every_dependabot_ecosystem_has_a_seven_day_cooldown(self):
        self.assertEqual(dependabot_cooldown_problems(yaml.safe_load(read(".github", "dependabot.yml"))), [])

    def test_ci_node_satisfies_every_engines_range_in_the_lockfile(self):
        node = ci_node_version(read(".github", "workflows", "ci.yml"))
        self.assertIsNotNone(node, "the ci.yml firebase job needs a literal node-version (22, 22.x or 22.1.2)")
        lock = json.loads(read("firebase", "package-lock.json"))
        self.assertEqual(lockfile_engine_offenders(lock, node), [], f"packages whose engines.node excludes the CI Node {node}")

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
        for name in REQUIRED_CHECKS:
            self.assertIsNotNone(job(text, name), name)
            self.assertRegex(text, rf"(?m)^    name: {name}$")

    def test_every_ci_job_is_a_required_check(self):
        text = read(".github", "workflows", "ci.yml")
        jobs = re.findall(r"(?m)^  ([A-Za-z][\w-]*):\n", text.split("\njobs:\n", 1)[1])
        self.assertEqual(sorted(jobs), sorted(REQUIRED_CHECKS))

    def test_docs_list_exactly_the_required_checks(self):
        for parts in (("docs", "BRANCH-PROTECTION.md"), ("docs", "PLAN.md")):
            with self.subTest(doc=parts[-1]):
                text = read(*parts)
                self.assertEqual(documented_checks(text), sorted(REQUIRED_CHECKS))
                self.assertIn(f"{len(REQUIRED_CHECKS)} checks", text)
                self.assertEqual(documented_count(text), len(REQUIRED_CHECKS))
                self.assertNotRegex(text, r"\b8 checks")

    def test_plan_ci_list_has_a_bullet_for_every_required_check(self):
        self.assertEqual(plan_item4_checks(read("docs", "PLAN.md")), sorted(REQUIRED_CHECKS))

    def test_count_and_item4_parsers_have_negative_cases(self):
        names = ", ".join(f"`{n}`" for n in REQUIRED_CHECKS)
        self.assertEqual(documented_count(f"Required checks (10): {names}."), 10)
        self.assertNotEqual(documented_count(f"Required checks (9): {names}."), len(REQUIRED_CHECKS))
        self.assertNotEqual(documented_count(f"all 8 checks green ({names})"), len(REQUIRED_CHECKS))
        self.assertIsNone(documented_count("no count here"))
        item = "4. **CI (GitHub Actions)**, required:\n   * `static`: x\n   * `unit`: y\n5. next\n   * `ui`: z\n"
        self.assertEqual(plan_item4_checks(item), ["static", "unit"])
        self.assertEqual(plan_item4_checks("nothing"), [])

    def test_documented_checks_parser_rejects_a_missing_or_extra_name(self):
        base = "x\nRequired checks (10): " + ", ".join(f"`{n}`" for n in REQUIRED_CHECKS) + ".\n"
        self.assertEqual(documented_checks(base), sorted(REQUIRED_CHECKS))
        short = base.replace("`workflow-lint`", "`unit`")
        self.assertNotEqual(documented_checks(short), sorted(REQUIRED_CHECKS))
        self.assertNotEqual(documented_checks(base.replace("`tasks`", "`tasks`, `extra`")), sorted(REQUIRED_CHECKS))
        self.assertEqual(documented_checks("no list here"), [])


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

    def test_ts_jest_prints_no_hybrid_module_warning_with_the_project_tsconfig(self):
        """Issue 210 item 7. The control without isolatedModules shows that the warning would be printed and seen."""
        code, out = jest()
        self.assertEqual(code, 0, out)
        self.assertIn("1 passed", out)
        self.assertNotIn("TS151002", out)
        code, out = jest(options={"isolatedModules": False})
        self.assertEqual(code, 0, out)
        self.assertIn("TS151002", out)

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
