"""Checks that relative links and backticked repo paths in every tracked *.md file exist (M0.5-12, review item P12).

Usage: python3 -I scripts/docs_check.py [--root DIR]
Exit status: 0 ok, 1 problems (one line per problem on stdout: file:line kind target), 2 bad usage.

Scanned: all `*.md` files of the repository (docs/, agents/, CLAUDE.md, REVIEW.md, README.md, ...).
Checked:
* markdown links `[text](target)` and reference definitions `[label]: target`: a relative target (fragment and
  query removed) must exist, relative to the file;
* backticked tokens that look like repo paths: they must exist relative to the repository root or to the file.
  A token is a path when it has no spaces, glob or placeholder characters, contains `/`, and either its last
  segment has a file extension or its first segment is a top-level entry of the repository.
  A `:line`, `:a-b` or `#Lnn` suffix is ignored.
Skipped: fenced code blocks (CommonMark: closed by the same character, at least as long), HTML comments, absolute and
external links, links inside code spans.
Known limits: link targets that contain `)`, indented (four-space) code blocks, and bare file names without `/`.

Existence follows git (`git ls-files`: tracked files and untracked files that are not ignored), so a path that only
exists in a gitignored build directory fails here as it would in CI. Outside a git checkout the file system is used.

Planned paths (documented before they exist) go in scripts/docs_check_allowlist.txt, one entry per line:
`path  # reason` (any file may mention it) or `path @file @file  # reason` (only those files may). Use the scoped
form for names that are absent on purpose, so a new mention elsewhere still fails. An entry is stale (a problem)
when the path now exists, or when no file (or one of its listed files) mentions it, so the list cannot rot.
"""

import argparse
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ALLOWLIST = "scripts/docs_check_allowlist.txt"

_HTML_COMMENT = re.compile(r"<!--.*?(?:-->|\Z)", re.S)
_FENCE_OPEN = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")
_CODE_SPAN = re.compile(r"(`+)(.+?)\1")
_LINK = re.compile(r"\[[^\]]*\]\(\s*<?([^)\s>]+)>?(?:\s+[\"'][^)]*[\"'])?\s*\)")
_DEFINITION = re.compile(r"^ {0,3}\[[^\]^][^\]]*\]:\s*<?([^\s>]+)>?(?:\s.*)?$")
_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")
_PATH_CHARS = re.compile(r"^[A-Za-z0-9._][A-Za-z0-9._/-]*$")
_EXTENSION = re.compile(r"\.[A-Za-z][A-Za-z0-9]{0,5}$")
_LINE_SUFFIX = re.compile(r"(?::\d+(?:-\d+)?|#L\d+(?:-L?\d+)?)$")
_SKIP_DIRS = {".git", "node_modules"}


@dataclass(frozen=True)
class Problem:
    kind: str
    file: str
    line: int
    target: str
    note: str = ""

    def __str__(self):
        return f"{self.file}:{self.line} {self.kind} {self.target}" + (f" ({self.note})" if self.note else "")


@dataclass(frozen=True)
class Ref:
    kind: str  # "broken-link" or "missing-path"
    file: str
    line: int
    target: str  # as written (normalised)
    candidates: tuple  # absolute paths, any one existing satisfies the reference


@dataclass(frozen=True)
class Entry:
    target: str
    scope: tuple  # files allowed to mention it; empty means any file
    line: int


class Tree:
    """What exists in the repository: git's view (tracked plus untracked-not-ignored), else the file system."""

    def __init__(self, root):
        self.root = root
        self.files = self._git_files()
        self.dirs = set()
        for f in self.files or ():
            parts = f.split("/")[:-1]
            self.dirs.update("/".join(parts[:i]) for i in range(1, len(parts) + 1))

    def _git_files(self):
        env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}  # a hook's GIT_DIR must not leak in
        try:
            res = subprocess.run(["git", "-C", str(self.root), "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
                                 capture_output=True, env=env, check=False)
        except OSError:
            return None
        if res.returncode != 0:
            return None
        names = (n for n in res.stdout.decode("utf-8", "surrogateescape").split("\0") if n)
        return {n for n in names if os.path.lexists(self.root / n)}  # drops files deleted but still in the index

    def exists(self, path):
        if self.files is None:
            return os.path.exists(path)
        rel = os.path.relpath(os.path.normpath(path), self.root).replace(os.sep, "/")
        return rel == "." or rel in self.files or rel in self.dirs

    def top_level(self):
        if self.files is None:
            return {p.name for p in self.root.iterdir()}
        return {f.split("/")[0] for f in self.files}

    def markdown(self):
        if self.files is not None:
            return sorted(self.root / f for f in self.files if f.endswith(".md"))
        found = []
        for dirpath, dirnames, filenames in os.walk(self.root):
            dirnames[:] = sorted(d for d in dirnames if d not in _SKIP_DIRS)
            found += [Path(dirpath) / f for f in filenames if f.endswith(".md")]
        return sorted(found)


def _blank_comments(text):
    """Replace HTML comments by blank space of the same newlines so line numbers stay right."""
    return _HTML_COMMENT.sub(lambda m: "\n" * m.group(0).count("\n"), text)


def _norm(target):
    t = target[2:] if target.startswith("./") else target
    return t.rstrip("/") if len(t) > 1 else t


def _repo_rel(root, path):
    return _norm(os.path.relpath(os.path.normpath(path), root).replace(os.sep, "/"))


def _looks_like_path(token, top_level):
    if not _PATH_CHARS.match(token) or "/" not in token or token.startswith("/"):
        return False
    segments = [s for s in token.split("/") if s]
    if not segments or any(s == "." for s in segments):
        return False
    return bool(_EXTENSION.search(segments[-1])) or segments[0] in top_level


def _link_ref(doc, rel, n, target):
    if target.startswith(("#", "/")) or _SCHEME.match(target):
        return None
    bare = re.split(r"[#?]", target, maxsplit=1)[0]
    if not bare:
        return None
    return Ref("broken-link", rel, n, _norm(bare), (doc.parent / bare,))


def _refs_in(root, doc, top_level):
    rel = doc.relative_to(root).as_posix()
    text = _blank_comments(doc.read_text(encoding="utf-8"))
    fence = None  # (character, length) of the open fence
    for n, raw in enumerate(text.splitlines(), 1):
        if fence:
            if re.match(rf"^ {{0,3}}{re.escape(fence[0])}{{{fence[1]},}}\s*$", raw):
                fence = None
            continue
        m = _FENCE_OPEN.match(raw)
        if m and not (m.group(1)[0] == "`" and "`" in m.group(2)):
            fence = (m.group(1)[0], len(m.group(1)))
            continue
        d = _DEFINITION.match(raw)
        if d:
            ref = _link_ref(doc, rel, n, d.group(1))
            if ref:
                yield ref
            continue
        prose = _CODE_SPAN.sub(lambda m: " " * len(m.group(0)), raw)
        for m in _LINK.finditer(prose):
            ref = _link_ref(doc, rel, n, m.group(1))
            if ref:
                yield ref
        for m in _CODE_SPAN.finditer(raw):
            bare = _LINE_SUFFIX.sub("", m.group(2).strip())
            if _looks_like_path(bare, top_level):
                yield Ref("missing-path", rel, n, _norm(bare), (root / bare, doc.parent / bare))


def _read_allowlist(path, rel):
    """Returns ([Entry], [Problem])."""
    entries, problems, seen = [], [], set()
    if not path.is_file():
        return entries, problems
    for n, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        spec, _, reason = line.partition("#")
        tokens = spec.split()
        target = _norm(tokens[0])
        scope = tuple(_norm(t[1:]) for t in tokens[1:] if t.startswith("@") and len(t) > 1)
        if len(scope) != len(tokens) - 1:
            problems.append(Problem("bad-allow", rel, n, target, "a scope is `@file`"))
        if target in seen:
            problems.append(Problem("bad-allow", rel, n, target, "duplicate entry"))
            continue
        seen.add(target)
        entries.append(Entry(target, scope, n))
        if not reason.strip():
            problems.append(Problem("bad-allow", rel, n, target, "needs `# reason`"))
    return entries, problems


def check(root, allowlist):
    root = Path(root).resolve()
    allowlist = Path(allowlist)
    try:
        rel_allow = allowlist.resolve().relative_to(root).as_posix()
    except ValueError:
        rel_allow = allowlist.name
    tree = Tree(root)
    top_level = tree.top_level()
    entries, problems = _read_allowlist(allowlist, rel_allow)
    by_target = {e.target: e for e in entries}
    used = set()  # (entry target, file that mentioned it)
    for doc in tree.markdown():
        for ref in _refs_in(root, doc, top_level):
            if any(tree.exists(c) for c in ref.candidates):
                continue
            hits = {_repo_rel(root, c) for c in ref.candidates} & by_target.keys()
            hits = {t for t in hits if not by_target[t].scope or ref.file in by_target[t].scope}
            if hits:
                used |= {(t, ref.file) for t in hits}
                continue
            problems.append(Problem(ref.kind, ref.file, ref.line, ref.target))
    for e in entries:
        if tree.exists(root / e.target):
            problems.append(Problem("stale-allow", rel_allow, e.line, e.target, "exists now, remove the entry"))
        elif e.scope:
            gone = [f for f in e.scope if (e.target, f) not in used]
            if gone:
                problems.append(Problem("stale-allow", rel_allow, e.line, e.target, f"{', '.join(gone)} no longer mention(s) it, remove it from the entry"))
        elif not any(t == e.target for t, _ in used):
            problems.append(Problem("stale-allow", rel_allow, e.line, e.target, "no file mentions it, remove the entry"))
    return problems


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", default=str(Path(__file__).resolve().parent.parent))
    try:
        args = ap.parse_args(argv)
    except SystemExit as e:
        return 2 if e.code else 0
    root = Path(args.root)
    problems = check(root, root / ALLOWLIST)
    for p in problems:
        print(p)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
