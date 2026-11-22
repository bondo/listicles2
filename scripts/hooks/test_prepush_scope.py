"""Run: python3 -I -m unittest discover -s scripts/hooks
Tests prepush_scope.py: the pre-push hook skips the Android build for diffs that cannot affect it. Unknown paths build (fail closed).
`--hook-tests` (owner decision 7075952806 item 1 on #15): the hook suite runs only when the push changes a file it reads, runs or
imports; HookSuiteInputs derives that set from the hook code itself. Unknown or empty ranges run it."""

import ast
import functools
import os
import posixpath
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import prepush_scope  # noqa: E402  # justified: must follow the sys.path insert above

import gitenv  # noqa: E402, F401  # justified: after the sys.path insert, imported for its side effect, drops GIT_DIR and friends (see gitenv.py)

ZERO = "0" * 40


class Classify(unittest.TestCase):
    def test_non_android_paths_skip(self):
        for p in ("docs/PLAN.md", "handoff/x.md", "README.md", "REVIEW.md", "scripts/verify.sh", "scripts/hooks/x.py",
                  ".githooks/pre-push", ".claude/settings.json", ".github/workflows/ci.yml", "agents/roles.yaml",
                  "firebase/firestore.rules", "metrics/sessions/a.json", "CLAUDE.md"):
            self.assertEqual(prepush_scope.classify([p]), "skip", p)

    def test_kotlin_and_gradle_script_files_build_under_any_skip_prefix(self):
        """R1-01: spotless and detekt check **/*.kt and **/*.gradle.kts wherever they are, so a skip prefix must not hide them."""
        for p in ("firebase/x/src/A.kt", "scripts/x/build.gradle.kts", "docs/sample/src/A.kt", "agents/Tool.kt", "metrics/a.kts",
                  ".github/settings.gradle.kts"):
            self.assertEqual(prepush_scope.classify([p]), "android", p)
        self.assertEqual(prepush_scope.classify(["docs/a.md", "firebase/x/A.kt"]), "android")

    def test_names_that_only_look_like_kotlin_still_skip(self):
        for p in ("docs/kt.md", "docs/a.kt.md", "scripts/notes-kts.txt", "docs/kt/readme.md"):
            self.assertEqual(prepush_scope.classify([p]), "skip", p)

    def test_android_paths_build(self):
        for p in ("app/src/main/java/A.kt", "core/domain/src/main/kotlin/B.kt", "build.gradle.kts", "settings.gradle.kts",
                  "gradle/libs.versions.toml", "gradle.properties", "gradlew", "config/detekt/detekt.yml", "app/src/main/res/values/strings.xml"):
            self.assertEqual(prepush_scope.classify([p]), "android", p)

    def test_markdown_inside_modules_still_builds(self):
        self.assertEqual(prepush_scope.classify(["app/src/main/assets/notes.md"]), "android")
        self.assertEqual(prepush_scope.classify(["core/domain/README.md"]), "android")

    def test_mixed_builds(self):
        self.assertEqual(prepush_scope.classify(["docs/PLAN.md", "app/src/main/java/A.kt"]), "android")

    def test_unknown_path_builds(self):
        self.assertEqual(prepush_scope.classify(["newdir/file.txt"]), "android")
        self.assertEqual(prepush_scope.classify(["scripts/../app/A.kt"]), "android")

    def test_empty_diff_skips(self):
        self.assertEqual(prepush_scope.classify([]), "skip")


class RepoCase(unittest.TestCase):
    def setUp(self):
        self.repo = tempfile.mkdtemp()
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.email", "t@example.com")
        self.git("config", "user.name", "t")
        self.git("config", "core.hooksPath", "/dev/null")
        self.commit("README.md", "a")
        self.base = self.rev()

    def git(self, *a):
        return subprocess.run(["git", *a], cwd=self.repo, capture_output=True, text=True, check=True).stdout.strip()

    def rev(self):
        return self.git("rev-parse", "HEAD")

    def commit(self, path, content):
        full = os.path.join(self.repo, path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w") as f:
            f.write(content)
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "c")

    def scope(self, local, remote, extra_env=None):
        line = f"refs/heads/b {local} refs/heads/b {remote}\n"
        r = subprocess.run([sys.executable, "-I", os.path.join(HERE, "prepush_scope.py")], input=line, cwd=self.repo,
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.strip()


class Cli(RepoCase):
    def test_docs_only_push_skips(self):
        self.commit("docs/a.md", "x")
        self.commit("scripts/t.sh", "x")
        self.assertEqual(self.scope(self.rev(), self.base), "skip")

    def test_code_change_in_any_pushed_commit_builds(self):
        self.commit("app/src/main/A.kt", "x")
        self.commit("docs/a.md", "x")
        self.assertEqual(self.scope(self.rev(), self.base), "android")

    def test_unknown_remote_sha_builds(self):
        self.commit("docs/a.md", "x")
        self.assertEqual(self.scope(self.rev(), "1" * 40), "android")

    def test_new_branch_without_origin_main_builds(self):
        self.commit("docs/a.md", "x")
        self.assertEqual(self.scope(self.rev(), ZERO), "android")

    def test_new_branch_uses_merge_base_with_origin_main(self):
        self.git("update-ref", "refs/remotes/origin/main", self.base)
        self.commit("docs/a.md", "x")
        self.assertEqual(self.scope(self.rev(), ZERO), "skip")
        self.commit("app/src/main/A.kt", "x")
        self.assertEqual(self.scope(self.rev(), ZERO), "android")

    def test_moving_an_android_file_into_a_skip_directory_builds(self):
        """R10-53: rename detection hides the source path; the build lost a file."""
        self.commit("app/src/main/kotlin/Foo.kt", "class Foo")
        base = self.rev()
        os.makedirs(os.path.join(self.repo, "docs"))
        self.git("mv", "app/src/main/kotlin/Foo.kt", "docs/Foo.kt")
        self.git("commit", "-q", "-m", "move")
        self.assertEqual(self.scope(self.rev(), base), "android")

    def test_branch_delete_skips(self):
        self.assertEqual(self.scope(ZERO, self.base), "skip")

    def test_garbage_input_builds(self):
        r = subprocess.run([sys.executable, "-I", os.path.join(HERE, "prepush_scope.py")], input="nonsense\n", cwd=self.repo,
                           capture_output=True, text=True)
        self.assertEqual((r.returncode, r.stdout.strip()), (0, "android"))

    def test_no_input_builds(self):
        r = subprocess.run([sys.executable, "-I", os.path.join(HERE, "prepush_scope.py")], input="", cwd=self.repo,
                           capture_output=True, text=True)
        self.assertEqual((r.returncode, r.stdout.strip()), (0, "android"))



class HookTestsScope(unittest.TestCase):
    """hook_tests_scope: `run` when a changed path can affect the hook suite, `skip` otherwise; unknown means run."""

    def test_hook_inputs_run(self):
        for p in ("scripts/hooks/test_x.py", "scripts/hooks/pretooluse_guard.py", "scripts/guards.sh", ".githooks/pre-push",
                  ".githooks/pre-commit", ".claude/settings.json", ".claude/agents/ci-triage.md", "scripts/verify.sh",
                  "scripts/statusline.sh", "scripts/mark-ready.sh", "scripts/update-branch.sh", "scripts/linters.pins",
                  ".github/workflows/ci.yml", ".github/CODEOWNERS", "agents/roles.yaml", "agents/prompts/reviewer.md", "CLAUDE.md",
                  "REVIEW.md", "docs/PLAN.md", "docs/ORCHESTRATION.md", "docs/tasks.toml", "handoff/TEMPLATE.md", ".gitignore",
                  "core/domain/build.gradle.kts", "core/newmodule/build.gradle.kts", ".gitattributes", ".gitmodules",
                  "app/src/androidTest/kotlin/dk/bjarkebjarke/tally/TallyAppTest.kt"):
            self.assertEqual(prepush_scope.hook_tests_scope([p]), "run", p)

    def test_a_python_file_anywhere_runs_because_the_suite_checks_every_lint_suppression(self):
        for p in ("firebase/tools/x.py", "app/gen.py", "docs/sample.py", "x.py"):
            self.assertEqual(prepush_scope.hook_tests_scope([p]), "run", p)

    def test_app_docs_and_other_non_inputs_skip(self):
        for p in ("app/src/main/java/A.kt", "app/src/main/res/values/strings.xml", "app/src/main/res/values-da/strings.xml",
                  "app/build.gradle.kts", "core/domain/src/main/kotlin/B.kt", "docs/FOLLOW-UPS.md", "docs/product/spec.md",
                  "docs/PLAN.md.bak", "handoff/tooling-x.md", "firebase/firestore.rules", "gradle/libs.versions.toml", "README.md",
                  "metrics/sessions/a.json", "app/src/androidTest/kotlin/dk/bjarkebjarke/tally/OtherTest.kt"):
            self.assertEqual(prepush_scope.hook_tests_scope([p]), "skip", p)
        self.assertEqual(prepush_scope.hook_tests_scope(["app/src/main/java/A.kt", "docs/product/spec.md"]), "skip")

    def test_one_input_among_non_inputs_runs(self):
        self.assertEqual(prepush_scope.hook_tests_scope(["app/src/main/java/A.kt", "docs/a.md", "scripts/guards.sh"]), "run")

    def test_empty_and_odd_paths_run(self):
        self.assertEqual(prepush_scope.hook_tests_scope([]), "run")
        for p in ("", "/scripts/guards.sh", "docs/../scripts/guards.sh", "app/../.githooks/pre-push", "./scripts/guards.sh"):
            self.assertEqual(prepush_scope.hook_tests_scope(["docs/a.md", p]), "run", repr(p))


class HookTestsCli(RepoCase):
    """`--hook-tests` reads the same pre-push stdin and prints `run` or `skip`; anything unknown or empty prints `run`."""

    def hooks(self, stdin):
        r = subprocess.run([sys.executable, "-I", os.path.join(HERE, "prepush_scope.py"), "--hook-tests"], input=stdin, cwd=self.repo,
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.strip()

    def push_line(self, local, remote):
        return f"refs/heads/b {local} refs/heads/b {remote}\n"

    def test_app_and_docs_only_push_skips(self):
        self.commit("app/src/main/A.kt", "x")
        self.commit("docs/product/a.md", "x")
        self.assertEqual(self.hooks(self.push_line(self.rev(), self.base)), "skip")

    def test_a_hook_file_in_any_pushed_commit_runs(self):
        for path in ("scripts/hooks/test_new.py", "scripts/guards.sh", ".githooks/pre-push", ".claude/settings.json", "scripts/verify.sh"):
            with self.subTest(path):
                base = self.rev()
                self.commit(path, "x" + path)
                self.commit("app/src/main/A.kt", path)
                self.assertEqual(self.hooks(self.push_line(self.rev(), base)), "run")

    def test_a_deleted_hook_file_runs(self):
        self.commit("scripts/hooks/test_old.py", "x")
        base = self.rev()
        self.git("rm", "-q", "scripts/hooks/test_old.py")
        self.git("commit", "-q", "-m", "rm")
        self.assertEqual(self.hooks(self.push_line(self.rev(), base)), "run")

    def test_a_hook_file_moved_out_of_the_suite_runs(self):
        self.commit("scripts/hooks/helper.md", "x")
        base = self.rev()
        os.makedirs(os.path.join(self.repo, "docs"))
        self.git("mv", "scripts/hooks/helper.md", "docs/helper.md")
        self.git("commit", "-q", "-m", "move")
        self.assertEqual(self.hooks(self.push_line(self.rev(), base)), "run")

    def test_an_empty_range_runs(self):
        self.assertEqual(self.hooks(self.push_line(self.base, self.base)), "run")

    def test_a_non_ascii_hook_file_runs(self):
        """Self-review major: git quotes such paths in --name-only output, so the quoted name matched no input and skipped."""
        for path in ("scripts/hooks/test_\u00e9.py", "scripts/hooks/n\u00f8te.md", "docs/a b\tc.md"):
            with self.subTest(path):
                base = self.rev()
                self.commit(path, "x")
                expected = "skip" if path.startswith("docs/") else "run"
                self.assertEqual(self.hooks(self.push_line(self.rev(), base)), expected)

    def test_a_branch_delete_runs(self):
        self.assertEqual(self.hooks(self.push_line(ZERO, self.base)), "run")

    def test_unknown_ranges_run(self):
        self.commit("app/src/main/A.kt", "x")
        self.assertEqual(self.hooks(self.push_line(self.rev(), "1" * 40)), "run")  # remote commit not here
        self.assertEqual(self.hooks(self.push_line(self.rev(), ZERO)), "run")  # new branch, no origin/main
        self.assertEqual(self.hooks(self.push_line("2" * 40, self.base)), "run")  # unreadable local commit
        self.assertEqual(self.hooks("nonsense\n"), "run")
        self.assertEqual(self.hooks(""), "run")
        self.assertEqual(self.hooks("\n"), "run")

    def test_new_branch_uses_merge_base_with_origin_main(self):
        self.git("update-ref", "refs/remotes/origin/main", self.base)
        self.commit("app/src/main/A.kt", "x")
        self.assertEqual(self.hooks(self.push_line(self.rev(), ZERO)), "skip")
        self.commit("scripts/hooks/x.py", "x")
        self.assertEqual(self.hooks(self.push_line(self.rev(), ZERO)), "run")

    def test_one_of_two_pushed_refs_with_a_hook_change_runs(self):
        self.commit("app/src/main/A.kt", "x")
        app = self.rev()
        self.commit("scripts/guards.sh", "x")
        self.assertEqual(self.hooks(self.push_line(app, self.base) + self.push_line(self.rev(), app)), "run")

    def test_the_android_scope_is_unchanged_by_the_flag(self):
        self.commit("scripts/hooks/x.py", "x")
        self.assertEqual(self.scope(self.rev(), self.base), "skip")  # hook tests run, Gradle does not


def path_of(base, args, rows_of, names):
    """The repo-relative paths an os.path.join-style argument list names: constants and module-level string names as written,
    f-strings with X for each substitution, a variable of an enclosing loop over literal rows expanded (starred or not), any other
    value as the placeholder segment X. None when a starred argument cannot be read (the caller reports it)."""
    variants = [[base] if base else []]
    for a in args:
        var = a.value if isinstance(a, ast.Starred) else a
        rows = rows_of(var.id) if isinstance(var, ast.Name) else None
        if rows is not None:
            variants = [v + list(row) for v in variants for row in rows]
        elif isinstance(a, ast.Starred):
            return None
        elif isinstance(a, ast.Constant) and isinstance(a.value, str):
            variants = [v + [a.value] for v in variants]
        elif isinstance(a, ast.Name) and a.id in names:
            variants = [v + [names[a.id]] for v in variants]
        elif isinstance(a, ast.JoinedStr):
            text = "".join(x.value if isinstance(x, ast.Constant) else "X" for x in a.values)
            variants = [v + [text] for v in variants]
        else:
            variants = [v + ["X"] for v in variants]
    return [posixpath.normpath("/".join(v)) if v else "." for v in variants]


def literal_rows(loop):
    """The rows of `for v in (("a", "b"), ...)` or `for v in ("a", ...)`, or None when the iterable is not such a literal."""
    if not isinstance(loop.iter, (ast.Tuple, ast.List)):
        return None
    rows = [[e.value for e in t.elts] if isinstance(t, ast.Tuple) else [t.value] if isinstance(t, ast.Constant) else None
            for t in loop.iter.elts]
    return rows if all(r is not None and all(isinstance(x, str) for x in r) for r in rows) else None


def rows_of(var, call, parent):
    """The literal rows of the innermost `for var in ...` around `call`; None when a function parameter or nothing binds it first."""
    n = parent.get(id(call))
    while n is not None:
        if isinstance(n, ast.For) and isinstance(n.target, ast.Name) and n.target.id == var:
            return literal_rows(n)
        if isinstance(n, (ast.FunctionDef, ast.Lambda)) and var in {a.arg for a in n.args.args + n.args.kwonlyargs}:
            return None
        n = parent.get(id(n))
    return None


PATH_WRAPPERS = ("os.path.normpath", "os.path.realpath", "os.path.abspath")
DEFAULT_ROOTS = {"ROOT": ".", "SCRIPT_ROOT": ".", "HERE": "scripts/hooks"}


def is_file_dir(node):
    """os.path.dirname(__file__), optionally with abspath or realpath around __file__: the directory of a hook file."""
    if not (isinstance(node, ast.Call) and ast.unparse(node.func) == "os.path.dirname" and len(node.args) == 1):
        return False
    inner = node.args[0]
    if isinstance(inner, ast.Call) and ast.unparse(inner.func) in PATH_WRAPPERS[1:] and len(inner.args) == 1:
        inner = inner.args[0]
    return isinstance(inner, ast.Name) and inner.id == "__file__"


def base_of(node, roots):
    """The repo-relative directory an expression names when it is a root (a root name, a hook file's directory, a normalising
    wrapper or a literal os.path.join on one of those), else None."""
    if isinstance(node, ast.Name) and node.id in roots:
        return roots[node.id]
    if is_file_dir(node):
        return "scripts/hooks"
    if isinstance(node, ast.Call) and ast.unparse(node.func) in PATH_WRAPPERS and len(node.args) == 1:
        return base_of(node.args[0], roots)
    if isinstance(node, ast.Call) and ast.unparse(node.func) == "os.path.join" and node.args:
        base = base_of(node.args[0], roots)
        rest = node.args[1:]
        if base is not None and all(isinstance(a, ast.Constant) and isinstance(a.value, str) for a in rest):
            return posixpath.normpath("/".join([base] + [a.value for a in rest]))
    return None


def hook_code_reads(sources):
    """Repo paths named by the hook code in `sources` ({file name: source}): calls to a `read(...)` helper and os.path.join on a
    root. A root is ROOT, SCRIPT_ROOT (the repo root), HERE or a hook file's own directory (scripts/hooks), or a module-level name
    defined as one of those. A name resolves only through its innermost enclosing `for`; only the `read` helper's own pass-through
    of its *parts is exempt. Every other use of a root (f-string, pathlib, cwd=ROOT, a bare __file__, a join that names the whole
    repo) is a root use (R1-02). Returns (paths as {path: [file]}, unreadable as [file:line], root uses as {file: [line]})."""
    paths, unreadable, root_uses = {}, [], {}
    for name, src in sorted(sources.items()):
        tree = ast.parse(src)
        parent = {id(c): n for n in ast.walk(tree) for c in ast.iter_child_nodes(n)}
        names = {t.id: n.value.value for n in tree.body if isinstance(n, ast.Assign) and isinstance(n.value, ast.Constant)
                 and isinstance(n.value.value, str) for t in n.targets if isinstance(t, ast.Name)}
        roots, defined = dict(DEFAULT_ROOTS), set()
        for n in tree.body:  # module-level root definitions, in order (ROOT may be defined from HERE)
            if isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name):
                base = base_of(n.value, roots)
                if base in (".", "scripts/hooks"):
                    roots[n.targets[0].id] = base
                    defined |= {id(c) for c in ast.walk(n.value)}
        helper_args = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "read" and node.args.vararg:
                helper_args |= {id(c) for c in ast.walk(node) if isinstance(c, ast.Call)
                                and any(isinstance(a, ast.Starred) and getattr(a.value, "id", None) == node.args.vararg.arg for a in c.args)}

        for node in ast.walk(tree):
            if id(node) in defined:
                continue
            up1 = parent.get(id(node))
            up2 = parent.get(id(up1)) if up1 is not None else None
            bare_file = isinstance(node, ast.Name) and node.id == "__file__" and not is_file_dir(up1) and not is_file_dir(up2)
            rootish = (isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load) and node.id in roots) or is_file_dir(node) or bare_file
            is_base = isinstance(up1, ast.Call) and ast.unparse(up1.func) == "os.path.join" and up1.args and up1.args[0] is node
            if rootish and not is_base:
                root_uses.setdefault(name, []).append(node.lineno)
            if not isinstance(node, ast.Call) or id(node) in helper_args:
                continue
            f = node.func
            resolve = functools.partial(rows_of, call=node, parent=parent)
            if isinstance(f, ast.Name) and f.id == "read":
                found = path_of("", node.args, resolve, names)
            elif ast.unparse(f) == "os.path.join" and node.args and base_of(node.args[0], roots) is not None:
                base = base_of(node.args[0], roots)
                found = path_of("" if base == "." else base, node.args[1:], resolve, names)
            else:
                continue
            if found is None:
                unreadable.append(f"{name}:{node.lineno}")
                continue
            for p in found:
                if p == ".":
                    root_uses.setdefault(name, []).append(node.lineno)
                else:
                    paths.setdefault(p, []).append(name)
    return paths, unreadable, {f: sorted(lines) for f, lines in root_uses.items()}


def hook_sources():
    out = {}
    for n in os.listdir(HERE):
        if n.endswith(".py"):
            with open(os.path.join(HERE, n), encoding="utf-8") as f:
                out[n] = f.read()
    return out


# Uses of a root (ROOT, SCRIPT_ROOT, HERE, any name defined from __file__ as the repo root or scripts/hooks, a bare __file__, or a
# join that resolves to the repo root) other than as the base of a resolvable os.path.join, counted per file (R1-02). A new one fails
# HookSuiteInputs until it is listed here with a reason, so a read the parse cannot follow (f-string, pathlib, cwd=ROOT) fails closed.
ROOT_USES = {
    "pretooluse_guard.py": (1, "SCRIPT_ROOT is a candidate project root for resolving command paths; it reads no repo file"),
    "run_hook_tests.py": (2, "the runner starts itself (__file__) in each shard"),
    "test_gitenv_isolation.py": (2, "discovers suites in scripts/hooks (HERE) with cwd=ROOT; their own reads are checked in their files"),
    "test_guards_sh.py": (1, "git grep for lint suppressions over every *.py: hook_tests_scope runs for any .py path"),
    "test_mark_ready.py": (3, "imports from scripts/hooks; cwd=ROOT runs the scripts/mark-ready.sh wrapper and git ls-files on it"),
    "test_update_branch.py": (4, "imports from scripts/hooks; cwd=ROOT runs the scripts/update-branch.sh wrapper and git ls-files on it"),
    "test_prepush_scope.py": (2, "imports from and lists scripts/hooks (HERE): scripts/ prefix"),
    "test_run_hook_tests.py": (2, "units and stale_weights of scripts/hooks (HERE): scripts/ prefix"),
}
# Directories the hook code lists rather than reads; each maps to a representative path it then reads.
LISTED_DIRS = {"core": "core/X/build.gradle.kts", "scripts/hooks": "scripts/hooks/X"}


class HookSuiteInputs(unittest.TestCase):
    """The hook_tests_scope set is derived from the hook code: every repo path it reads, runs or copies must make the suite run.
    Any other use of a root (cwd=ROOT, f-string or pathlib paths, a bare __file__) fails until ROOT_USES lists it with a reason.
    Not seen by this parse: what a run script reads in turn (scripts/ is a prefix for that reason) and guards.sh on the whole repo
    (test_guards_sh's self-check), which pre-push runs on every push anyway. CI runs the full suite on every PR as the backstop."""

    def test_every_repo_path_the_hook_code_reads_runs_the_suite(self):
        paths, unreadable, root_uses = hook_code_reads(hook_sources())
        self.assertEqual(unreadable, [], "write these reads with literal path parts so the scope can be checked")
        for p, files in paths.items():
            self.assertFalse(p == "." or p.startswith("../"), p)
            probe = LISTED_DIRS.get(p, p)
            self.assertEqual(prepush_scope.hook_tests_scope([probe]), "run", f"{p} (read by {', '.join(sorted(set(files)))})")
        self.assertEqual({f: len(lines) for f, lines in root_uses.items()}, {k: n for k, (n, _) in ROOT_USES.items()},
                         "a root used outside a resolvable os.path.join: list it in ROOT_USES with a reason, or make the read resolvable")

    def test_the_parse_finds_the_known_reads(self):
        paths, _, _ = hook_code_reads(hook_sources())
        for p in ("docs/PLAN.md", "docs/ORCHESTRATION.md", "scripts/verify.sh", ".claude/settings.json", ".githooks/pre-push",
                  "scripts/statusline.sh", "scripts/guards.sh", "core/X/build.gradle.kts", ".claude/agents/X.md", "REVIEW.md", ".gitignore",
                  "scripts/X", "agents/prompts/reviewer.md", "CLAUDE.md", "app/src/androidTest/kotlin/dk/bjarkebjarke/tally/TallyAppTest.kt"):
            self.assertIn(p, paths)

    def test_a_new_read_outside_the_scope_is_reported(self):
        src = ("import os\nROOT = '.'\nHERE = '.'\n"
               "def read(*parts):\n    return open(os.path.join(ROOT, *parts)).read()\n"
               "read('docs', 'new.md')\nos.path.join(ROOT, 'app', 'x.txt')\nos.path.join(HERE, '..', '..', 'firebase', 'a.json')\n"
               "for p in (('docs', 'a.md'), ('docs', 'b.md')):\n    read(*p)\nread(*other)\nread('docs', name)\n"
               "for n in ('c.md', 'd.md'):\n    read('docs', n)\nNEW = 'docs/e.md'\nread(NEW)\nread('docs', f'{n}.txt')\n")
        paths, unreadable, _ = hook_code_reads({"test_new.py": src})
        self.assertEqual(sorted(paths), ["app/x.txt", "docs/X", "docs/X.txt", "docs/a.md", "docs/b.md", "docs/c.md", "docs/d.md", "docs/e.md",
                                        "docs/new.md", "firebase/a.json"])
        self.assertEqual(unreadable, ["test_new.py:11"])
        for p in paths:
            self.assertEqual(prepush_scope.hook_tests_scope([p]), "skip", p)

    def test_a_name_resolves_only_through_its_own_enclosing_loop(self):
        """Self-review: a parameter or listdir name took the rows of an unrelated loop, and a second loop on the same name hid the first."""
        src = "\n".join([
            "def read(*parts):", "    return parts",
            "for n in ('a.md',):", "    pass",
            "def f(n):", "    return read('docs', n)",
            "for p in (('docs', 'b.md'),):", "    read(*p)",
            "for p in (('docs', 'c.md'),):", "    read(*p)",
            "for n in ('d.md', 'e.md'):", "    for m in ('x',):", "        read('docs', n)",
        ])
        paths, unreadable, _ = hook_code_reads({"test_new.py": src})
        self.assertEqual(sorted(paths), ["docs/X", "docs/b.md", "docs/c.md", "docs/d.md", "docs/e.md"])
        self.assertEqual(unreadable, [])

    def test_root_uses_the_parse_cannot_follow_are_reported(self):
        """R1-02: f-string, pathlib and cwd=ROOT forms read the repo without a resolvable join; they must fail closed, not vanish."""
        src = "\n".join([
            "import os, pathlib, subprocess",
            "HERE = os.path.dirname(os.path.abspath(__file__))",
            "ROOT = os.path.normpath(os.path.join(HERE, '..', '..'))",
            "BASE = os.path.realpath(os.path.join(os.path.dirname(__file__), '..', '..'))",
            "TOOL = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'tool.py')",
            "open(f'{ROOT}/docs/FOLLOW-UPS.md')",
            "pathlib.Path(ROOT, 'docs', 'FOLLOW-UPS.md')",
            "pathlib.Path(BASE) / 'firebase' / 'firestore.rules'",
            "subprocess.run(['grep', '-q', 'x', 'docs/FOLLOW-UPS.md'], cwd=ROOT)",
            "os.listdir(HERE)",
            "print(__file__)",
            "os.path.join(ROOT, 'docs', 'a.md')",
            "def f():",
            "    return os.path.join(HERE, '..', '..')",
            "subprocess.run([TOOL])",
        ])
        paths, unreadable, root_uses = hook_code_reads({"test_new.py": src})
        self.assertEqual(root_uses, {"test_new.py": [6, 7, 8, 9, 10, 11, 14]})
        self.assertEqual(sorted(paths), ["docs/a.md", "scripts/hooks/tool.py"])
        self.assertEqual(unreadable, [])

    def test_imported_attribute_and_derived_roots_are_reported_or_resolved(self):
        """R2-01: an imported root alias, a module's ROOT or __file__, a dirname of a path constant, __spec__, sys.path[0],
        sys.argv[0] and globals()['__file__'] reach the repo too: resolved into a path where possible, else a root use."""
        src = "\n".join([
            "from test_guard_wrapper_forms import ROOT as R",
            "import test_guard_wrapper_forms as w",
            "import os, sys, prepush_scope",
            "HERE = os.path.dirname(os.path.abspath(__file__))",
            "GUARDS = os.path.join(HERE, '..', 'guards.sh')",
            "os.path.join(R, 'docs', 'FOLLOW-UPS.md')",
            "os.path.join(w.ROOT, 'docs', 'FOLLOW-UPS.md')",
            "os.path.dirname(prepush_scope.__file__)",
            "os.path.join(os.path.dirname(GUARDS), '..', 'docs', 'a.md')",
            "globals()['__file__']",
            "__spec__.origin",
            "sys.path[0]",
            "os.path.dirname(sys.argv[0])",
            "print(R)",
        ])
        paths, unreadable, root_uses = hook_code_reads({"test_new.py": src})
        self.assertEqual(sorted(paths), ["docs/FOLLOW-UPS.md", "docs/a.md", "scripts/guards.sh"])
        self.assertEqual(root_uses, {"test_new.py": [7, 8, 10, 11, 12, 13, 14]})
        self.assertEqual(unreadable, [])
        for p in ("docs/FOLLOW-UPS.md", "docs/a.md"):
            self.assertEqual(prepush_scope.hook_tests_scope([p]), "skip", p)  # so HookSuiteInputs would fail on them

    def test_only_the_read_helper_itself_passes_its_parts_through_unreported(self):
        """Self-review: any *parts helper hid its joins, and calls to it other than `read` were never collected."""
        src = "\n".join([
            "import os", "ROOT = '.'",
            "def read(*parts):", "    return open(os.path.join(ROOT, *parts)).read()",
            "def load(*parts):", "    return open(os.path.join(ROOT, *parts)).read()",
            "load('app', 'x.txt')",
        ])
        paths, unreadable, _ = hook_code_reads({"test_new.py": src})
        self.assertEqual(paths, {})
        self.assertEqual(unreadable, ["test_new.py:6"])


class PathsMode(unittest.TestCase):
    """`--paths`: newline-separated paths on stdin (the staged files, for the pre-commit hook); same fail-closed classification."""

    def scope(self, text):
        r = subprocess.run([sys.executable, "-I", os.path.join(HERE, "prepush_scope.py"), "--paths"], input=text,
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.strip()

    def test_prose_and_scripts_skip(self):
        self.assertEqual(self.scope("docs/a.md\nscripts/hooks/x.py\nagents/roles.yaml\n"), "skip")

    def test_one_android_path_among_docs_builds(self):
        self.assertEqual(self.scope("docs/a.md\napp/src/main/A.kt\n"), "android")

    def test_gradle_and_config_paths_build(self):
        for p in ("build.gradle.kts", "gradle/libs.versions.toml", "config/detekt/detekt.yml", ".editorconfig"):
            self.assertEqual(self.scope(p + "\n"), "android", p)

    def test_no_paths_builds_because_unknown_means_build(self):
        self.assertEqual(self.scope(""), "android")
        self.assertEqual(self.scope("\n\n"), "android")

    def test_parent_directory_escape_builds(self):
        self.assertEqual(self.scope("docs/../app/A.kt\n"), "android")

    def test_without_the_flag_the_stdin_is_still_pre_push_lines(self):
        self.assertEqual(self.scope("refs/heads/b 1 refs/heads/b 2\n"), "android")  # a pre-push line is not a docs path


if __name__ == "__main__":
    unittest.main()
