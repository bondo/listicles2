"""Tests for check 1 on command lines in scripts/guards.sh (task M1-71). Run: python3 -I -m unittest discover -s scripts/hooks

Owner decision (#15 comment 7092471489): jest, vitest and mocha options that rewrite or skip tests (snapshot update,
--passWithNoTests), filter them by name or path (-t, --testPathIgnorePatterns, positional path filters, mocha --grep and kin) or run
only changed ones (jest -o, --changedSince, --findRelatedTests, vitest --changed) fail on a command line, directly or after an npm
`--` tail, with no `justified:` escape hatch (check 1 has none). --shard is allowed. Each denied option is tried in a shell script,
in a package.json script and after `npm test --`; the allowed look-alikes next to them must pass.
"""

import json
import unittest

import test_guards_sh as base

MARK = "guard: test-runner option that skips or rewrites tests"
FLAG = "guard: unjustified CLI flag"

# runner -> options that must fail after it, on its command line or in an npm `--` tail that reaches it
DENIED = {
    "jest": ["-u", "--updateSnapshot", "--update-snapshot", "--updateSnapshot=true", "'-u'", "--ci -u", "-iu", "--passWithNoTests",
             "--pass-with-no-tests", "-t smoke", "-t=smoke", "--testNamePattern smoke", "--testNamePattern=smoke",
             "--test-name-pattern=smoke", "--testPathIgnorePatterns gen", "--testPathIgnorePatterns=gen", "--testPathPattern a",
             "--testPathPatterns=a", "-o", "--onlyChanged", "--only-changed", "--changedSince=main", "--changedSince main",
             "--findRelatedTests a.js", "--lastCommit", "-f", "--onlyFailures", "-c jest.config.cjs -u",
             # self-review: a value letter ends a group only before a number or a non-letter; inline JSON config; a path filter module
             "-wu", "-cu", "--config='{\"passWithNoTests\":true}'", "-c '{\"testPathIgnorePatterns\":[\"gen\"]}'", "--filter=./f.js",
             # R1-01: a group is read as yargs-parser reads it (digits and other letters are flags too); R1-02: --u is the short alias
             "-w2u", "-i2u", "-1u", "-x9u", "-cjest.config.cjs", "-u2", "--u", "--o", "--f", "--ci --u", "--u=true", "--c='{\"a\":1}'"],
    "vitest": ["run -u", "run --update", "--update", "run --passWithNoTests", "run -t smoke", "run --testNamePattern=smoke",
               "run --changed", "--changed HEAD~1", "run --exclude gen", "run -cu",
               "run -w2u", "run -1u", "run -c.u", "run --u", "run --t smoke"],
    "mocha": ["--grep smoke", "-g smoke", "--fgrep smoke", "-f smoke", "--invert", "-i", "--passWithNoTests", "--ignore gen",
              "--exclude=gen", "-tg smoke", "--g smoke", "--i", "--f smoke", "--i --g slow", "-1g smoke"],
}
# runner -> forms that must pass (the --shard of the owner decision, other options and their values, redirections)
ALLOWED = {
    "jest": ["", "--ci --coverage", "--shard 1/3", "--shard=2/3", "--testTimeout 5000", "--testTimeout=5000", "--runInBand", "-i",
             "-w 2", "-w2", "--maxWorkers=50%", "--maxWorkers 2", "-c jest.config.cjs", "--config=jest.config.cjs --ci",
             "--ci > out.log", "--reporters default", "--testSequencer=./seq.js", "--no-cache", "-w4 --ci", "-c=jest.config.cjs",
             "--env node", "--cacheDirectory d", "-w 2u", "--w=2", "--seed -1", "-w2 --ci"],
    "vitest": ["", "run", "watch", "run --shard 1/2", "run --coverage", "--config vitest.config.ts run", "run --testTimeout=5000"],
    "mocha": ["", "'test/**/*.spec.js'", "-t 5000 test", "--timeout 5000", "-u bdd test", "--forbid-only --recursive test",
              "-R spec test", "--spec test/a.spec.js"],
}
# command positions: a path filter after jest or vitest fails here
POSITIONAL = ["jest src/a", "npx jest a.test.ts", "jest --ci src", "jest -- src", "jest --maxWorkers 2 src", "jest -i src",
              "jest $FILES", "./node_modules/.bin/jest src", "CI=1 npx jest src", "npx --yes jest src", "yarn jest src",
              "pnpm exec jest src", "node --experimental-vm-modules node_modules/jest/bin/jest.js src", "vitest run src", "vitest src",
              "vitest related a.ts", "vitest list", "vitest bench", "bunx vitest run src",
              # R1-03: a version suffix, wrappers with option values, shell keywords and quoted assignments before the runner
              "npx jest@30 src", "npx -y jest@29 src", "npx vitest@2 run src", "timeout 60 jest src", "timeout -s KILL 60 jest src",
              "nice -n 5 jest src", "sudo -u bob jest src", "env -u CI jest src", "bun run jest src", "yarn run jest src",
              'FOO="a b" jest src', "FOO='a b c' npx jest src", "if true; then jest src; fi", "for d in a; do jest src; done",
              "{ jest src; }", "! jest src", "(jest src)", "while jest src; do :; done", "x=$(npx jest src)",
              "jest --testSequencer ./seq.js"]  # fail closed: a value of an unlisted option is read as a path filter; write it with =


class RunnerCase(base.GuardsCase):
    def put(self, rel, text):
        self.repo.write(rel, text, raw=True)
        self.repo.git("add", "-A")
        self.repo.git("commit", "-q", "--allow-empty", "-m", "c")

    def pkg(self, entries, extra=""):
        return ('{\n  "name": "t",\n  "scripts": {\n' + ",\n".join(f"    {json.dumps(k)}: {json.dumps(v)}" for k, v in entries)
                + "\n  }" + extra + "\n}\n")

    def each_line_fails(self, rel, lines, mark=MARK, first=1):
        """lines[i] is on line first + i of rel; every one must be reported with mark."""
        rc, out = self.repo.guards()
        self.assertNotEqual(rc, 0, out)
        for i, line in enumerate(lines):
            with self.subTest(line=line):
                self.assertIn(f"{mark}: {rel}:{first + i}:", out)


class DirectTests(RunnerCase):
    def test_each_denied_option_fails_in_a_shell_script(self):
        lines = [f"npx {r} {o}" for r, opts in DENIED.items() for o in opts]
        self.put("scripts/test.sh", "\n".join(lines) + "\n")
        self.each_line_fails("scripts/test.sh", lines)

    def test_each_denied_option_fails_in_a_package_json_script(self):
        entries = [(f"t{i}", f"{r} {o}") for i, (r, o) in enumerate((r, o) for r, opts in DENIED.items() for o in opts)]
        self.put("tools/package.json", self.pkg(entries))
        self.each_line_fails("tools/package.json", [v for _, v in entries], first=4)

    def test_workflow_makefile_and_folded_yaml_forms_fail(self):
        self.put(".github/workflows/ci.yml", "jobs:\n  a:\n    steps:\n      - run: cd firebase && npx jest -u\n"
                 "      - run: >\n          npx vitest run\n          --changed\n")
        self.put("Makefile", "test:\n\t@npx mocha --grep smoke\n")
        rc, out = self.repo.guards()
        self.assertNotEqual(rc, 0, out)
        for where in [".github/workflows/ci.yml:4:", ".github/workflows/ci.yml:6:", "Makefile:2:"]:
            with self.subTest(where=where):
                self.assertIn(f"{MARK}: {where}", out)

    def test_positional_path_filters_fail(self):
        self.put("scripts/test.sh", "\n".join(POSITIONAL) + "\n")
        self.each_line_fails("scripts/test.sh", POSITIONAL)
        entries = [("test", "jest src"), ("v", "vitest run src"), ("j", "npx jest@30 src"), ("q", 'FOO="a b" jest src')]
        self.put("scripts/test.sh", "true\n")
        self.put("tools/package.json", self.pkg(entries))
        self.each_line_fails("tools/package.json", [v for _, v in entries], first=4)

    def test_a_json_value_ends_the_command(self):
        """Round 1 fix: a package.json script ends at the closing quote of its value, so the next key is no path filter."""
        self.put("firebase/package.json", '{\n  "scripts": { "test": "jest --runInBand", "format": "prettier --check ." },\n'
                 '  "x": { "jest": "30.5.2", "y": "z" }\n}\n')
        self.assertPasses()
        lines = ['  "scripts": { "test": "jest src", "format": "prettier --check ." },', '  "a": { "t": "npx jest@30 -u" },',
                 '  "b": { "t": "jest --ci", "u": "jest -- src" },']
        self.put("firebase/package.json", "{\n" + "\n".join(lines) + "\n}\n")
        self.each_line_fails("firebase/package.json", lines, first=2)

    def test_a_reason_does_not_waive_it(self):
        lines = ["npx jest -u # justified: snapshots are regenerated on purpose", "jest src # justified: only this folder runs here"]
        self.put("scripts/test.sh", "\n".join(lines) + "\n")
        self.each_line_fails("scripts/test.sh", lines)

    def test_staged_mode_reads_the_index(self):
        self.repo.write("scripts/test.sh", "npx jest --passWithNoTests\n", raw=True)
        self.repo.git("add", "scripts/test.sh")
        self.assertFails(MARK + ": scripts/test.sh:1:", "--staged")

    def test_allowed_options_and_neighbouring_lines_pass(self):
        lines = [f"npx {r} {o}".rstrip() for r, opts in ALLOWED.items() for o in opts]
        lines += ["jest --ci 2>&1 | tee out.log", "grep -c jest package.json", "echo vitest", "npm i -D jest", "npm install -D vitest@2 -E",
                  "npx eslint . && npx jest --ci", "cd firebase && npm ci", "timeout 60 jest --ci", "npx jest@30 --ci",
                  "sudo -u bob jest --ci", "if true; then jest --ci; fi", 'FOO="a b" jest --ci', "nice -n 5 echo jest"]
        self.put("scripts/test.sh", "\n".join(lines) + "\n")
        self.put("tools/package.json", self.pkg(
            [("test", "jest --ci"), ("v", "vitest run --shard 1/2"), ("m", "mocha 'test/**/*.spec.js'"),
             ("e", 'firebase emulators:exec --only firestore "jest --runInBand"')],
            ',\n  "devDependencies": {\n    "jest": "30.5.2",\n    "ts-jest": "29.4.0",\n    "@vitest/coverage-v8": "2.1.0",\n'
            '    "@types/mocha": "10.0.0"\n  }'))
        self.assertPasses()


class NpmTailTests(RunnerCase):
    """An npm `--` tail is appended to the script it runs (task M1-65 resolves it). A tail that reaches jest or mocha is read with that
    runner's options; any other tail keeps the 2c union check, and its long runner options fail with no escape hatch."""

    def setUp(self):
        super().setUp()
        self.put("tools/package.json", self.pkg([("test", "jest"), ("m", "npx mocha --recursive"), ("v", "vitest run"),
                                                 ("lint", "eslint .")]))

    def test_each_denied_option_fails_after_the_tail(self):
        lines = [f"cd tools && npm test -- {o}" for o in DENIED["jest"]]
        lines += [f"npm run m -- {o}" for o in DENIED["mocha"]]
        lines += ["npm test -- src", "npm test -- --ci src", "npm test -- -- --quiet", "npm t -- -u", "npm run test -- -u",
                  "npm -s test -- -u", "npm run m -- test/a.spec.js",
                  "npm run m -- --spec test/a.spec.js", "npm run m -- --spec=test/a.spec.js",
                  "npm test -- -w2u", "npm test -- -1u", "npm test -- --u", "npm test -- --o", "npm run m -- --i", "npm run m -- --g=smoke"]
        self.put("scripts/test.sh", "\n".join(lines) + "\n")
        self.each_line_fails("scripts/test.sh", lines)

    def test_an_unresolved_tail_fails_on_long_runner_options_even_with_a_reason(self):
        lines = [f"npm run v -- {o} # justified: three words here" for o in
                 ["--update", "--passWithNoTests", "--testNamePattern=smoke", "--changed", "--exclude=gen"]]
        lines += ["yarn test -- --updateSnapshot # justified: three words here",
                  "npm run lint -- --onlyChanged # justified: three words here", "npx jest -- --grep x"]
        self.put("scripts/test.sh", "\n".join(lines) + "\n")
        self.each_line_fails("scripts/test.sh", lines)

    def test_unresolved_short_runner_options_keep_the_2c_check(self):
        self.put("scripts/test.sh", "npm run v -- -u\n")
        self.assertFails(FLAG + ": scripts/test.sh:1:")
        self.put("scripts/test.sh", "npm run v -- -t smoke # justified: three words here\n")
        self.assertPasses()

    def test_allowed_tails_pass(self):
        lines = ["cd tools && npm test -- --ci", "npm test -- -i", "npm test -- --shard 1/3", "npm test -- --shard=1/3",
                 "npm test -- --testTimeout=5000", "npm test -- -w 2", "npm test -- --maxWorkers 2 --coverage",
                 "npm run m -- -t 5000", "npm run m -- --timeout 5000", "npm run m -- -R dot",
                 "npm run lint -- --max-warnings 0", "npm run lint -- -f json"]
        self.put("scripts/test.sh", "\n".join(lines) + "\n")
        self.assertPasses()


if __name__ == "__main__":
    unittest.main()
