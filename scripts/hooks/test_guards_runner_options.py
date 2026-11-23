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
                 '  "b": { "t": "jest --ci", "u": "jest -- src" },',
                 # R2-02: the options of every mention of a runner on the line are read, also behind a wrapper cmdat does not name
                 '  "c": { "test": "jest --runInBand", "e2e": "cross-env CI=1 jest -u" },',
                 '  "d": { "a": "jest --ci", "b": "nyc jest --passWithNoTests" },', '  "e": { "a": "mocha", "b": "c8 mocha --grep x" },']
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


# Task M1-81, owner decision #15 comment 7102820038 (the full proposal of PR 358 comment 7102517597). playwright and cypress use
# commander: kebab-case long names, grouped short options (-xu), and a value letter takes the rest of its group (-j2, -gsmoke).
PW_DENIED = ["-u", "--update-snapshots", "--update-snapshots=none", "-u missing", "-xu", "--ignore-snapshots", "--pass-with-no-tests",
             "--list", "tests/login.spec.ts", "login", "-- tests/a.spec.ts", "--workers 2 src", "-j2 src", "--project chromium login",
             "-g smoke", "-gsmoke", "-xg smoke", "--grep=smoke", "--grep-invert slow", "-gv slow", "--test-list t.txt",
             "--test-list-invert=t.txt", "--no-deps", "-c tests/e2e", "--config=tests/e2e", "--config tests/e2e", "-c pw.ts",
             "-ctests", "-c playwright.config.json", "--last-failed", "--only-changed", "--only-changed=main", "--only-changed main"]
PW_ALLOWED = ["", "--shard 1/3", "--shard=2/3", "-j 4", "-j4", "--workers=50%", "--reporter list", "--reporter=html", "--output out",
              "--trace on", "--timeout 0", "--global-timeout 600000", "--max-failures 1", "-x", "--repeat-each 3",
              "--tsconfig tsconfig.e2e.json", "--update-source-method patch", "--quiet", "--headed", "--debug", "--ui",
              "--ui-host 0.0.0.0 --ui-port 8080", "--forbid-only", "--fail-on-flaky-tests", "--fully-parallel",
              "-c playwright.config.ts", "--config=e2e/playwright.config.mts", "-cplaywright.config.cjs", "--config pw.config.js",
              "--project chromium", "--project=firefox", "--retries 2", "--reporter=list > out.log"]
CY_DENIED = ["-s a.cy.ts", "--spec a.cy.ts", "--spec=cypress/e2e/**", "-qs a.cy.ts", "a.cy.ts", "--browser chrome a.cy.ts",
             "-- a.cy.ts", "-c specPattern=x", "--config specPattern=cypress/e2e/smoke/**", "--config=e2e.specPattern=x",
             "-c video=false,excludeSpecPattern=x", "--config '{\"e2e\":{\"specPattern\":\"x\"}}'", "-cspecPattern=x",
             "-e grep=smoke", "--env grepTags=@smoke", "--env=grepInvert=true", "-e a=1,grepUntagged=true",
             "--env '{\"grepFilterSpecs\":true}'", "-e GREP=x", "--env grepOmitFiltered=true", "-egrep=x"]
CY_ALLOWED = ["", "--browser chrome", "-b firefox", "--headed", "--headless", "-C cypress.config.ts", "--config-file=cypress.ci.config.ts",
              "-c video=false", "--config baseUrl=http://localhost:5000", "-c '{\"video\":false}'", "-e apiUrl=http://x",
              "--env token=abc", "-p 8080", "-P e2e", "-r junit", "--reporter-options mochaFile=out.xml", "-o toConsole=true", "-q",
              "--record --key abc", "--record false", "--parallel --group ci --ci-build-id 7", "-t nightly", "--tag a,b",
              "--auto-cancel-after-failures 2", "--no-exit", "--runner-ui", "--no-runner-ui", "--e2e", "--component",
              "--quiet > out.log"]


class PlaywrightCypressTests(RunnerCase):
    """Task M1-81: `playwright test` and `cypress run` options that rewrite or skip tests, filter them or run only changed ones fail,
    directly, in a package.json script and after an npm `--` tail resolved to them (read with the runner's own letters and positional
    rule), with no escape hatch. The allowed options, their values and the non-test subcommands pass."""

    def lines(self, prefix, opts):
        return [f"{prefix} {o}".rstrip() for o in opts]

    def test_each_denied_option_fails_on_a_direct_call(self):
        lines = self.lines("npx playwright test", PW_DENIED) + self.lines("npx cypress run", CY_DENIED)
        lines += ["CI=1 npx playwright test src", "npx playwright@1.49.1 test --list", "./node_modules/.bin/cypress run --spec x.cy.ts",
                  "playwright test -u", "cypress run -s a.cy.ts", "timeout 600 npx playwright test --last-failed",
                  "npx playwright test --ci -u # justified: goldens are regenerated here"]
        self.put("scripts/test.sh", "\n".join(lines) + "\n")
        self.each_line_fails("scripts/test.sh", lines)

    def test_each_denied_option_fails_in_a_package_json_script_and_a_workflow(self):
        opts = [("playwright test", o) for o in PW_DENIED if "'" not in o] + [("cypress run", o) for o in CY_DENIED if "'" not in o]
        entries = [(f"t{i}", f"{c} {o}") for i, (c, o) in enumerate(opts)]
        self.put("tools/package.json", self.pkg(entries))
        self.put(".github/workflows/e2e.yml", "jobs:\n  a:\n    steps:\n      - run: npx playwright test --update-snapshots\n"
                 "      - run: >\n          npx cypress run\n          --spec a.cy.ts\n")
        self.each_line_fails("tools/package.json", [v for _, v in entries], first=4)
        rc, out = self.repo.guards()
        for where in [".github/workflows/e2e.yml:4:", ".github/workflows/e2e.yml:6:"]:
            with self.subTest(where=where):
                self.assertIn(f"{MARK}: {where}", out)

    def test_a_runner_inside_a_quoted_command_has_its_options_read(self):
        lines = ['bash -c "npx playwright test --last-failed"', "sh -c 'cypress run --spec a.cy.ts'"]
        self.put("scripts/test.sh", "\n".join(lines) + "\n")
        self.each_line_fails("scripts/test.sh", lines)

    def test_allowed_options_and_other_subcommands_pass(self):
        lines = self.lines("npx playwright test", PW_ALLOWED) + self.lines("npx cypress run", CY_ALLOWED)
        lines += ["npx playwright install --with-deps chromium", "npx playwright show-report out", "npx playwright --version",
                  "npx cypress open", "npx cypress verify", "npx cypress install", "npx cypress info", "npx cypress cache clear",
                  "npm i -D @playwright/test cypress", "npx eslint e2e && npx playwright test --forbid-only"]
        self.put("scripts/test.sh", "\n".join(lines) + "\n")
        self.put("tools/package.json", self.pkg(
            [("e2e", "playwright test --forbid-only"), ("cy", "cypress run --browser chrome"), ("pw", "npx playwright test")],
            ',\n  "devDependencies": {\n    "@playwright/test": "1.49.1",\n    "cypress": "13.17.0"\n  }'))
        self.assertPasses()

    def test_a_resolved_tail_is_read_with_the_runner_own_rules(self):
        self.put("tools/package.json", self.pkg([("e2e", "npx playwright test"), ("cy", "cypress run")]))
        lines = self.lines("npm run e2e --", PW_DENIED) + self.lines("npm run cy --", CY_DENIED)
        self.put("scripts/test.sh", "\n".join(lines) + "\n")
        self.each_line_fails("scripts/test.sh", lines)
        ok = self.lines("npm run e2e --", [o for o in PW_ALLOWED if o]) + self.lines("npm run cy --", [o for o in CY_ALLOWED if o])
        # jest and mocha letters are no longer read here (commander refuses them); a word after one is still a positional filter
        ok += ["npm run e2e -- -t", "npm run e2e -- -o", "npm run cy -- -u", "npm run cy -- -f"]
        self.put("scripts/test.sh", "\n".join(ok) + "\n")
        self.assertPasses()

    def test_an_unresolved_tail_fails_on_their_long_names_even_with_a_reason(self):
        lines = [f"yarn e2e -- {o} # justified: three words here" for o in
                 ["--last-failed", "--update-snapshots", "--ignore-snapshots", "--grep-invert=x", "--no-deps", "--list",
                  "--test-list=t.txt"]]
        self.put("scripts/test.sh", "\n".join(lines) + "\n")
        self.each_line_fails("scripts/test.sh", lines)


class PlaywrightCypressSelfReviewTests(RunnerCase):
    """PR 358 self-review: a quoted value with blanks is one word, a mention of a runner is read only with its test subcommand, the
    `@playwright/test` package name is playwright, and a tail resolved to runners with two parsers is read as mri."""

    def test_a_quoted_value_with_blanks_is_one_word(self):
        ok = ['npx playwright test --project="Mobile Chrome"', "npx playwright test --project 'Mobile Chrome'",
              "npx playwright test --project=Mobile\\ Chrome --shard 1/2", 'npx cypress run --record --group "UI - Chrome"',
              'npx cypress run --tag "nightly, smoke"', "npx cypress run -c '{\"video\": false}'", 'npx jest --testTimeout "5000"']
        self.put("scripts/test.sh", "\n".join(ok) + "\n")
        self.put("tools/package.json", self.pkg([("e2e", 'playwright test --project="Mobile Chrome"'), ("u", "jest --ci")]))
        self.assertPasses()
        bad = ['npx cypress run --env "grep=a b"', "npx cypress run -c '{\"e2e\": {\"specPattern\": \"x\"}}'",
               "sh -c 'cypress run --env \"{ \\\"grep\\\": \\\"x\\\" }\"'", 'npx playwright test "tests/a b.spec.ts"',
               'npx playwright test --grep "a b"', 'npx playwright test --project "Mobile Chrome" src', 'npx jest "src a"']
        self.put("tools/package.json", self.pkg([("u", "jest --ci")]))
        self.put("scripts/test.sh", "\n".join(bad) + "\n")
        self.each_line_fails("scripts/test.sh", bad)
        entries = [("e2e", 'playwright test --project="Mobile Chrome" login'), ("cy", 'cypress run --env "grep=x y"')]
        self.put("scripts/test.sh", "true\n")
        self.put("tools/package.json", self.pkg(entries))
        self.each_line_fails("tools/package.json", [v for _, v in entries], first=4)

    def test_a_mention_is_read_only_with_the_test_subcommand(self):
        ok = ["npx eslint e2e/playwright -c .eslintrc.json", "ls cypress/fixtures -s", "npx cypress open --spec x",
              "npx playwright show-report -c x", "npx playwright test -c"]
        self.put("scripts/test.sh", "\n".join(ok) + "\n")
        self.assertPasses()

    def test_the_playwright_package_name_is_playwright(self):
        bad = ["npx @playwright/test test login", "npx @playwright/test@1.49.1 test -u", 'bash -c "npx @playwright/test test --list"']
        self.put("scripts/test.sh", "\n".join(bad) + "\n")
        self.each_line_fails("scripts/test.sh", bad)

    def test_a_tail_resolved_to_two_parsers_is_read_as_mri(self):
        self.put("firebase/package.json", self.pkg([("test", "jest")]))
        self.put("tools/package.json", self.pkg([("test", "playwright test")]))
        bad = ["npm test -- -j2u", "npm test -- -u", "npm test -- --last-failed", "npm test -- src", "npm test -- -g smoke"]
        self.put("scripts/test.sh", "\n".join(bad) + "\n")
        self.each_line_fails("scripts/test.sh", bad)
        self.put("scripts/test.sh", "npm test -- --shard 1/2\n")
        self.assertPasses()


class PlaywrightCypressReviewRound1Tests(RunnerCase):
    """PR 358 R1-01: playwright run through node and its cli.js is playwright; R1-02: the npx -p/--package value is no command."""

    BAD = ["node node_modules/@playwright/test/cli.js test -u", "node node_modules/playwright/cli.js test --last-failed",
           "node node_modules/playwright/cli.js test login", 'bash -c "node node_modules/playwright/cli.js test -u"',
           "npx -p @playwright/test playwright test tests/a.spec.ts", "npx --package @playwright/test playwright test login",
           "npx -p playwright playwright test login", "npx -p cypress cypress run a.cy.ts", "npm exec -p cypress -- cypress run a.cy.ts"]

    def test_node_cli_js_and_npx_package_forms_fail(self):
        self.put("scripts/test.sh", "\n".join(self.BAD) + "\n")
        self.each_line_fails("scripts/test.sh", self.BAD)
        entries = [("t", "node node_modules/@playwright/test/cli.js test -u"), ("u", "npx -p @playwright/test playwright test login")]
        self.put("scripts/test.sh", "true\n")
        self.put("tools/package.json", self.pkg(entries))
        self.each_line_fails("tools/package.json", [v for _, v in entries], first=4)

    def test_their_allowed_forms_pass(self):
        ok = ["node node_modules/playwright/cli.js install chromium", "npx -p @playwright/test playwright test --shard 1/2",
              "node node_modules/@playwright/test/cli.js test --project chromium", "npx -p cypress cypress run --browser chrome"]
        self.put("scripts/test.sh", "\n".join(ok) + "\n")
        self.assertPasses()


if __name__ == "__main__":
    unittest.main()
