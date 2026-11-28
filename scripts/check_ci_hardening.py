"""CI hardening rules (M1-44, issues 189 and 127). Fails closed: a rule that cannot be read is a problem.

  * every job in ci.yml and status.yml has `timeout-minutes`, a whole number from 1 to 60 (GitHub's default is 6 hours),
  * python and node come from actions/setup-python and actions/setup-node, not from the runner image: a job that runs python3, pip,
    a shell script that runs python3, node, npm or npx (or a script that runs node) has the setup step before its first such step,
    one python minor and one node major in every job,
  * `npm ci` runs with --ignore-scripts, in the workflows and in verify.sh (the lockfile's install scripts are not needed: the
    emulators and the rules tests run without them, re2 is only an optional dependency of the hosting emulator),
  * the gitleaks download uses --proto =https, --proto-redir =https and --retry, the archive checksum is checked, and the scan is
    `gitleaks git` (`detect` is deprecated),
  * the pip lock files (issue 189 item 5, M1-74): scripts/requirements-ci.in and requirements-lint.in hold the exact top-level pins, the
    .txt next to each is the pip-compile --generate-hashes lock, every entry `name==X.Y.Z` with at least one sha256 hash and nothing
    else (no -r, -e, URL or index line), every .in pin is locked at its version, and the only `pip install` in the workflows and
    verify.sh is `pip install --require-hashes -r scripts/requirements-ci.txt` or the same for requirements-lint.txt,
  * every `uses:` in every workflow is a 40-character commit sha followed by a version tag comment (`# v4.39.3`), so a moved tag changes nothing,
  * codeql.yml (M1-73, issue 189 item 7, owner decision Q6 A): weekly (one cron with a fixed weekday), push to main and pull_request only;
    java-kotlin is analysed once, with `build-mode: manual` and a ./gradlew step between init and analyze, and never on a pull request;
    actions, javascript-typescript and python are analysed once each on pull requests with `build-mode: none`; every job has exactly
    contents: read and security-events: write; the codeql-action steps share one pinned version. Default setup must be off before the
    first upload (owner task M1-O9), which no file can show,
  * verify.sh and the CI `tasks` job run this check and its tests, and docs/adr/0003-gradle-dependency-verification.md records that
    Gradle dependency verification is checksum-only (issue 189 item 6).
Run: python3 -I scripts/check_ci_hardening.py  (exit 1 and one line per problem).
"""

import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS = (".github/workflows/ci.yml", ".github/workflows/status.yml")
CODEQL = ".github/workflows/codeql.yml"
MAX_TIMEOUT = 60
PYTHON_VERSION = "3.13"  # what the runner image shipped before the pin; 3.12 fails a hook test (chr() raises OverflowError there)
NODE_VERSION = "22"
SETUP_PYTHON = "actions/setup-python@"
SETUP_NODE = "actions/setup-node@"
# Scripts that start node themselves; a job that runs them needs the node pin although its commands never say `node`.
NODE_SCRIPTS = ("test_wireframes_safety.py", "test_firebase_ts.py")
ADR = "docs/adr/0003-gradle-dependency-verification.md"
ADR_PHRASES = ("Status: accepted", "verify-signatures", "checksum")
CHECK_CMD = "python3 -I scripts/check_ci_hardening.py"
TESTS_CMD = "python3 -I scripts/test_check_ci_hardening.py"
VERIFY_STEPS = (f"step ci-hardening-tests {TESTS_CMD}", f"step ci-hardening {CHECK_CMD}")
PYTHON_WORD = re.compile(r"(?<![\w./-])(?:python3?|pip3?)(?![\w-])")
NODE_WORD = re.compile(r"(?<![\w./-])(?:node|npm|npx)(?![\w-])")
# Gradle tasks that run python3 in an Exec (checkUnitTestResults finalizes the unit-test tasks, checkJavaApiLevel in build-logic ModuleChecks.kt,
# which each JVM library module's tallyChecks and so the root's detekt run):
# a job that runs one of them needs the python pin although its commands never say `python3`. A fixed list, held to the build files by
# the tests; `check` and `build` stay out (they would match build/ paths).
GRADLE_PYTHON_TASKS = ("testDebugUnitTest", "verifyRoborazziDebug", "recordRoborazziDebug", "checkJavaApiLevel", "tallyChecks", "detekt")
GRADLE_PYTHON = re.compile(r"gradlew\b[\s\S]*(?<![\w])(?:" + "|".join(GRADLE_PYTHON_TASKS) + r")(?![\w])")
# setup-python's interpreter has no PyYAML (the runner image's had) and most gate scripts import yaml.
LOCK_STEMS = ("scripts/requirements-ci", "scripts/requirements-lint")  # each has a .in (top-level pins) and a .txt (the hash lock)
INSTALL_CI = "pip install --require-hashes -r scripts/requirements-ci.txt"
INSTALL_LINT = "pip install --require-hashes -r scripts/requirements-lint.txt"
INSTALLS = (INSTALL_CI, INSTALL_LINT)
# pip, pip3, pip3.13 or -m pip / -mpip, then any options (also with values) before `install`, within one command (no pipe, `;` or `&`)
PIP_INSTALL = re.compile(r"(?:(?<![\w./-])pip(?:3(?:\.\d+)?)?(?![\w.-])|-m\s*pip(?:3(?:\.\d+)?)?(?![\w.-]))[^\n;&|]*?(?<![\w.-])install\b")
IN_PIN = re.compile(r"([A-Za-z0-9][A-Za-z0-9._-]*)==([0-9][A-Za-z0-9.!+_-]*)")
LOCK_ENTRY = re.compile(r"([A-Za-z0-9][A-Za-z0-9._-]*)==([0-9][A-Za-z0-9.!+_-]*)((?: --hash=sha256:[0-9a-f]{64})+)")
SHELL_SCRIPT = re.compile(r"scripts/[\w.-]+\.sh")
USES_LINE = re.compile(r"^\s*(?:-\s+)?uses:\s*(?P<ref>\S+)(?P<rest>.*)$")
PINNED = re.compile(r"[\w.-]+/[\w./-]+@[0-9a-f]{40}")
TAG_COMMENT = re.compile(r"\s+#\s*v\d+(?:\.\d+)+\b")
CODEQL_ACTION = "github/codeql-action/"
CODEQL_LANGUAGES = ("actions", "javascript-typescript", "python", "java-kotlin")
CODEQL_PERMISSIONS = {"contents": "read", "security-events": "write"}
CODEQL_TRIGGERS = {"pull_request", "push", "schedule"}
WEEKLY_CRON = re.compile(r"\d+ \d+ \* \* [0-7]")
NOT_A_PULL_REQUEST = "github.event_name != 'pull_request'"
MATRIX_LANGUAGE = "${{ matrix.language }}"


def _steps(job):
    return [s for s in (job or {}).get("steps") or [] if isinstance(s, dict)]


def _is_use(step, prefix):
    return str(step.get("uses", "")).startswith(prefix)


def _code(step):
    """The commands a step runs (run, and the script of an action that takes one), comment lines removed."""
    text = str(step.get("run", "")) + "\n" + str((step.get("with") or {}).get("script", ""))
    return "\n".join(ln for ln in text.splitlines() if not ln.strip().startswith("#"))


def _runs_python(text):
    return bool(PYTHON_WORD.search(text) or GRADLE_PYTHON.search(text))


def _needs_python(code, root):
    if _runs_python(code):
        return True
    for script in SHELL_SCRIPT.findall(code):
        path = root / script
        if path.is_file() and _runs_python(path.read_text()):
            return True
    return False


def _needs_node(code):
    return bool(NODE_WORD.search(code)) or any(s in code for s in NODE_SCRIPTS)


def _load(root, name):
    return yaml.safe_load((root / name).read_text()) or {}


def _setup_problems(where, steps, prefix, tool, want, version_key, needs, install=None):
    first = next((i for i, s in enumerate(steps) if needs(_code(s))), None)
    if first is None:
        return []
    setups = [i for i, s in enumerate(steps) if _is_use(s, prefix)]
    if not setups:
        return [f"{where} runs {tool} but has no {prefix.rstrip('@')} step: it would use the runner image's {tool}"]
    problems = []
    if setups[0] > first:
        problems.append(f"{where}: {prefix.rstrip('@')} must come before the first step that runs {tool} ({steps[first].get('name', first)})")
    for i in setups:
        got = (steps[i].get("with") or {}).get(version_key)
        if str(got) != want:
            problems.append(f"{where}: {version_key} must be {want} (one {tool} version in every job), not {got!r}")
    if install:
        found = [i for i, s in enumerate(steps) if s.get("run") == install]
        if not found:
            problems.append(f"{where}: no step runs `{install}` (requirements-ci.txt: PyYAML, hash-locked, which setup-python's {tool} lacks)")
        elif found[0] > first:
            problems.append(f"{where}: `{install}` must come before the first step that runs {tool} ({steps[first].get('name', first)})")
    return problems


def _logical_lines(text):
    """The requirement lines of a pip file: comments dropped, backslash continuations joined, whitespace collapsed."""
    out, cur = [], ""
    for raw in text.splitlines():
        line = re.split(r"(?:^|\s)#", raw, maxsplit=1)[0].strip()
        if not line:
            if cur:
                out.append(cur)
            cur = ""
            continue
        cur = f"{cur} {line.removesuffix(chr(92)).strip()}".strip()
        if not line.endswith("\\"):
            out.append(cur)
            cur = ""
    return out + ([cur] if cur else [])


def _norm(name):
    return re.sub(r"[-_.]+", "-", name).lower()  # PEP 503: pip-compile writes PyYAML as pyyaml


def requirements_problems(root):
    problems = []
    for stem in LOCK_STEMS:
        name_in, name_txt = stem + ".in", stem + ".txt"
        base_in, base_txt = name_in.rsplit("/", 1)[1], name_txt.rsplit("/", 1)[1]
        pins = {}
        if not (root / name_in).is_file():
            problems.append(f"{name_in} is missing (the top-level pins of {base_txt}, which pip-compile --generate-hashes writes)")
        else:
            lines = _logical_lines((root / name_in).read_text())
            for ln in lines:
                m = IN_PIN.fullmatch(ln)
                if m:
                    pins[_norm(m.group(1))] = (m.group(1), m.group(2))
                else:
                    problems.append(f"{base_in}: `{ln}` must be an exact pin, name==X.Y.Z")
            if stem.endswith("-ci") and (len(lines) != 1 or not re.fullmatch(r"PyYAML==\d+\.\d+\.\d+", lines[0])):
                problems.append(f"{base_in} must hold exactly one line, PyYAML==X.Y.Z (the other scripts use the standard library)")
        locked = {}
        if not (root / name_txt).is_file():
            problems.append(f"{name_txt} is missing (the hash lock: pip-compile --generate-hashes {base_in})")
            continue
        for ln in _logical_lines((root / name_txt).read_text()):
            m = LOCK_ENTRY.fullmatch(ln)
            if m:
                locked[_norm(m.group(1))] = m.group(2)
            else:
                problems.append(f"{base_txt}: `{ln[:70]}` must be name==X.Y.Z with at least one --hash=sha256:<64 hex> and nothing else")
        for key, (name, version) in pins.items():
            if locked.get(key) != version:
                problems.append(f"{base_txt}: {name}=={version} of {base_in} is not locked at that version (recompile it with pip-compile --generate-hashes)")
    return problems


def _pip_install_problems(where, code):
    return [f"{where}: only `{INSTALL_CI}` or `{INSTALL_LINT}` may run pip install (hash-locked, issue 189 item 5), not `{ln.strip()}`"
            for ln in code.splitlines() if PIP_INSTALL.search(ln) and ln.strip() not in INSTALLS]


def workflow_problems(root):
    problems = []
    for name in (*WORKFLOWS, CODEQL):
        if name == CODEQL and not (root / name).is_file():
            continue  # codeql_problems reports the missing file
        base = name.rsplit("/", 1)[1]
        for job_name, job in (_load(root, name).get("jobs") or {}).items():
            where = f"{base} job {job_name}"
            timeout = (job or {}).get("timeout-minutes")
            if type(timeout) is not int or not 1 <= timeout <= MAX_TIMEOUT:
                problems.append(f"{where}: timeout-minutes must be a whole number from 1 to {MAX_TIMEOUT}, not {timeout!r}")
            steps = _steps(job)
            problems += _setup_problems(where, steps, SETUP_PYTHON, "python", PYTHON_VERSION, "python-version", lambda c: _needs_python(c, root), INSTALL_CI)
            problems += _setup_problems(where, steps, SETUP_NODE, "node", NODE_VERSION, "node-version", _needs_node)
            for step in steps:
                code = _code(step)
                problems += _pip_install_problems(where, code)
                for line in code.splitlines():
                    if re.search(r"\bnpm\s+ci\b", line) and "--ignore-scripts" not in line:
                        problems.append(f"{where}: `npm ci` needs --ignore-scripts")
                if "gitleaks" in code:
                    problems += _gitleaks_problems(where, code)
    return problems


def _parsed_uses(workflow):
    """Every `uses` value the YAML parser sees, on jobs (reusable workflows) and on steps, whatever the spelling of the line."""
    values = []
    for job in (workflow.get("jobs") or {}).values():
        values += [job.get("uses")] if isinstance(job, dict) else []
        values += [s.get("uses") for s in _steps(job)]
    return [v for v in values if v is not None]


def pin_problems(root):
    """Every `uses:` of a remote action is `owner/repo@<40 hex> # vX.Y` on a line of its own (a local ./ action has no sha).
    The line rule accepts refs; every `uses` the YAML parser sees must be one of them, so anything the line rule cannot read
    (flow style, quoted key, a value on the next line) fails closed."""
    problems = []
    for path in sorted((root / ".github/workflows").glob("*.y*ml")):
        accepted = []
        for line in path.read_text().splitlines():
            m = USES_LINE.match(line)
            if not m or m["ref"].startswith("./"):
                continue
            if PINNED.fullmatch(m["ref"]) and TAG_COMMENT.match(m["rest"]):
                accepted.append(m["ref"])
            else:
                problems.append(f"{path.name}: {m['ref']} must be pinned to a commit sha with a version tag comment (`@<40 hex> # v1.2.3`)")
        for ref in _parsed_uses(yaml.safe_load(path.read_text()) or {}):
            if str(ref).startswith("./"):
                continue
            if str(ref) in accepted:
                accepted.remove(str(ref))
            else:
                problems.append(f"{path.name}: unreadable uses: {ref!r} (write `uses: owner/repo@<40 hex> # v1.2.3` on its own line, no flow or quoted key)")
    return problems


def _codeql_languages(job, init):
    raw = str((init.get("with") or {}).get("languages", ""))
    if raw == MATRIX_LANGUAGE:
        return [str(x) for x in ((job.get("strategy") or {}).get("matrix") or {}).get("language") or []]
    return [raw]


def _codeql_job_problems(where, job):
    problems = []
    if (job.get("permissions") or {}) != CODEQL_PERMISSIONS:
        got = job.get("permissions")
        problems.append(f"{where}: permissions must be exactly contents: read and security-events: write (upload needs no more), not {got!r}")
    steps = _steps(job)
    inits = [i for i, s in enumerate(steps) if _is_use(s, CODEQL_ACTION + "init@")]
    analyzes = [i for i, s in enumerate(steps) if _is_use(s, CODEQL_ACTION + "analyze@")]
    if len(inits) != 1 or len(analyzes) != 1 or inits[0] > analyzes[0]:
        return problems + [f"{where}: needs one codeql-action init step before one analyze step"], []
    init, last = steps[inits[0]], analyzes[0]
    langs = _codeql_languages(job, init)
    mode = (init.get("with") or {}).get("build-mode")
    if "java-kotlin" in langs:
        who = f"{where} (java-kotlin)"
        if mode != "manual":
            problems.append(f"{who}: build-mode must be manual (a Gradle build CodeQL traces), not {mode!r}")
        if job.get("if") != NOT_A_PULL_REQUEST:
            problems.append(f"{who}: `if: {NOT_A_PULL_REQUEST}` keeps it off pull_request (weekly and pushes to main only), not {job.get('if')!r}")
        builds = [_code(s) for s in steps[inits[0] + 1 : last] if "./gradlew" in _code(s)]
        if not builds:
            problems.append(f"{who}: no step runs ./gradlew between codeql-action init and analyze")
        elif not all("--no-build-cache" in b and "--build-cache" not in b and "caching=true" not in b for b in builds):
            problems.append(f"{who}: the traced ./gradlew build must pass --no-build-cache (a task restored from the cache starts no compiler)")
        if re.search(r"(?<![\w-])(?:-I|--init-script)(?![\w-])|init\.d", "\n".join(_code(s) for s in steps)):
            problems.append(f"{who}: no init script (-I, --init-script, init.d): it could turn the build cache back on past --no-build-cache")
        if not any(_is_use(s, "actions/setup-java@") for s in steps[: inits[0]]):
            problems.append(f"{who}: actions/setup-java must come before codeql-action init")
    else:
        if mode != "none":
            problems.append(f"{where}: build-mode must be none (no build for these languages), not {mode!r}")
        if "if" in job:
            problems.append(f"{where}: must run on pull_request, so no job-level if")
    return problems, langs


def codeql_problems(root):
    path = root / CODEQL
    if not path.is_file():
        return [f"{CODEQL} is missing (advanced CodeQL setup, M1-73, issue 189 item 7)"]
    wf = _load(root, CODEQL)
    on = wf.get("on", wf.get(True))
    problems = []
    if not isinstance(on, dict) or set(on) != CODEQL_TRIGGERS:
        problems.append(f"codeql.yml triggers must be exactly {sorted(CODEQL_TRIGGERS)}, not {sorted(on) if isinstance(on, dict) else on!r}")
    else:
        if ((on["push"] or {}).get("branches")) != ["main"]:
            problems.append("codeql.yml trigger push must be branches: [main]")
        pr = on["pull_request"] or {}
        if set(pr) - {"types"} or ("types" in pr and not {"opened", "synchronize", "reopened"} <= set(pr["types"] or [])):
            problems.append("codeql.yml trigger pull_request: no branches, paths or -ignore filter; types, if any, include opened, synchronize, reopened")
        cron = on["schedule"]
        if not (isinstance(cron, list) and len(cron) == 1 and isinstance(cron[0], dict) and WEEKLY_CRON.fullmatch(str(cron[0].get("cron")))):
            problems.append("codeql.yml trigger schedule must be one weekly cron (fixed minute, hour and weekday)")
    seen = []
    for job_name, job in (wf.get("jobs") or {}).items():
        found, langs = _codeql_job_problems(f"codeql.yml job {job_name}", job or {})
        problems += found
        seen += langs
    for lang in CODEQL_LANGUAGES:
        if seen.count(lang) == 0:
            problems.append(f"codeql.yml does not analyse {lang}")
        elif seen.count(lang) > 1:
            problems.append(f"codeql.yml must analyse {lang} exactly once, not {seen.count(lang)} times")
    problems += [f"codeql.yml analyses {lang!r}, which is not one of {list(CODEQL_LANGUAGES)}" for lang in dict.fromkeys(seen) if lang not in CODEQL_LANGUAGES]
    versions = set(re.findall(r"uses:\s*github/codeql-action/[\w-]+@(\S+)", path.read_text()))
    if len(versions) > 1:
        problems.append("codeql.yml: all codeql-action steps must use one pinned version, not " + ", ".join(sorted(versions)))
    return problems


def _gitleaks_problems(where, code):
    problems = []
    for flag in ("--proto =https", "--proto-redir =https", "--retry"):
        if flag not in code:
            problems.append(f"{where}: the gitleaks download needs curl {flag}")
    if "sha256sum -c" not in code:
        problems.append(f"{where}: the gitleaks archive must be checked with sha256sum -c")
    if "gitleaks detect" in code or "gitleaks git" not in code:
        problems.append(f"{where}: run `gitleaks git` (`gitleaks detect` is deprecated)")
    if re.search(r"gitleaks git\b.*--source", code):
        problems.append(f"{where}: `gitleaks git` takes the repository as an argument, not --source (unknown flag)")
    return problems


def verify_problems(root):
    lines = [ln.strip() for ln in (root / "scripts/verify.sh").read_text().splitlines() if ln.strip() and not ln.strip().startswith("#")]
    problems = [f"verify.sh has no active step: {want}" for want in VERIFY_STEPS if want not in lines]
    problems += _pip_install_problems("verify.sh", "\n".join(lines))
    problems += [f"verify.sh: `npm ci` needs --ignore-scripts: {ln}" for ln in lines if re.search(r"\bnpm\s+ci\b", ln) and "--ignore-scripts" not in ln]
    tasks = _steps((_load(root, WORKFLOWS[0]).get("jobs") or {}).get("tasks"))
    problems += [f"ci.yml tasks job has no step running: {cmd}" for cmd in (TESTS_CMD, CHECK_CMD) if not any(s.get("run") == cmd for s in tasks)]
    return problems


def adr_problems(root):
    path = root / ADR
    if not path.is_file():
        return [f"ADR missing: {ADR} (issue 189 item 6: Gradle dependency verification is checksum-only)"]
    text = path.read_text()
    return [f"ADR {ADR} does not mention {p!r}" for p in ADR_PHRASES if p not in text]


def problems(root=ROOT):
    root = Path(root)
    return workflow_problems(root) + pin_problems(root) + codeql_problems(root) + requirements_problems(root) + verify_problems(root) + adr_problems(root)


def main(root=ROOT):
    found = problems(root)
    for p in found:
        print(f"check_ci_hardening: {p}")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
