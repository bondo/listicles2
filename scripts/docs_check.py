"""Checks that relative links and backticked repo paths in docs/**/*.md exist (M0.5-12, review item P12).

Usage: python3 -I scripts/docs_check.py [--root DIR]
Exit status: 0 ok, 1 problems (one line per problem on stdout: file:line kind target), 2 bad usage.

Checked:
* markdown links `[text](target)`: a relative target (fragment and query removed) must exist, relative to the doc;
* backticked tokens that look like repo paths: they must exist relative to the repository root or to the doc.
  A token is a path when it has no spaces, glob or placeholder characters, contains `/`, and either its last
  segment has a file extension or its first segment is a top-level entry of the repository.
  A `:line`, `:a-b` or `#Lnn` suffix is ignored.
Skipped: fenced code blocks, HTML comments, absolute and external links, links inside code spans.

Planned paths (documented before they exist) go in scripts/docs_check_allowlist.txt, one `path  # reason` per line.
An entry is stale (a problem) when the path now exists or no doc mentions it, so the list cannot rot.
"""

import argparse
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

ALLOWLIST = "scripts/docs_check_allowlist.txt"

_HTML_COMMENT = re.compile(r"<!--.*?(?:-->|\Z)", re.S)
_FENCE = re.compile(r"^\s*(```|~~~)")
_CODE_SPAN = re.compile(r"(`+)(.+?)\1")
_LINK = re.compile(r"\[[^\]]*\]\(\s*<?([^)\s>]+)>?(?:\s+[\"'][^)]*[\"'])?\s*\)")
_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")
_PATH_CHARS = re.compile(r"^[A-Za-z0-9._][A-Za-z0-9._/-]*$")
_EXTENSION = re.compile(r"\.[A-Za-z][A-Za-z0-9]{0,5}$")
_LINE_SUFFIX = re.compile(r"(?::\d+(?:-\d+)?|#L\d+(?:-L?\d+)?)$")


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
    target: str  # as written (normalised), used for the allowlist
    candidates: tuple  # absolute paths, any one existing satisfies the reference


def _blank_comments(text):
    """Replace HTML comments by blank space of the same newlines so line numbers stay right."""
    return _HTML_COMMENT.sub(lambda m: "\n" * m.group(0).count("\n"), text)


def _norm(target):
    t = target[2:] if target.startswith("./") else target
    return t.rstrip("/") if len(t) > 1 else t


def _looks_like_path(token, top_level):
    if not _PATH_CHARS.match(token) or "/" not in token or token.startswith("/"):
        return False
    segments = [s for s in token.split("/") if s]
    if not segments or any(s == "." for s in segments):
        return False
    return bool(_EXTENSION.search(segments[-1])) or segments[0] in top_level


def _refs_in(root, doc, top_level):
    rel = doc.relative_to(root).as_posix()
    text = _blank_comments(doc.read_text(encoding="utf-8"))
    in_fence = False
    for n, raw in enumerate(text.splitlines(), 1):
        if _FENCE.match(raw):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        spans = [(m.start(), m.end(), m.group(2).strip()) for m in _CODE_SPAN.finditer(raw)]
        prose = _CODE_SPAN.sub(lambda m: " " * len(m.group(0)), raw)
        for m in _LINK.finditer(prose):
            target = m.group(1)
            if target.startswith(("#", "/")) or _SCHEME.match(target):
                continue
            bare = re.split(r"[#?]", target, maxsplit=1)[0]
            if not bare:
                continue
            yield Ref("broken-link", rel, n, _norm(bare), ((doc.parent / bare),))
        for _, _, token in spans:
            bare = _LINE_SUFFIX.sub("", token)
            if not _looks_like_path(bare, top_level):
                continue
            yield Ref("missing-path", rel, n, _norm(bare), (root / bare, doc.parent / bare))


def _repo_rel(root, path):
    return _norm(os.path.relpath(os.path.normpath(path), root).replace(os.sep, "/"))


def _read_allowlist(path):
    """Returns ({path: line number}, [Problem])."""
    entries, problems = {}, []
    if not path.is_file():
        return entries, problems
    rel = path.name if path.parent.name == "" else f"{path.parent.name}/{path.name}"
    for n, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        target, _, reason = line.partition("#")
        target = _norm(target.strip())
        if target in entries:
            problems.append(Problem("bad-allow", rel, n, target, "duplicate entry"))
            continue
        entries[target] = n
        if not reason.strip():
            problems.append(Problem("bad-allow", rel, n, target, "needs `# reason`"))
    return entries, problems


def check(root, allowlist):
    root = Path(root).resolve()
    allowlist = Path(allowlist)
    docs = sorted((root / "docs").rglob("*.md")) if (root / "docs").is_dir() else []
    top_level = {p.name for p in root.iterdir()}
    allowed, problems = _read_allowlist(allowlist)
    used = set()
    for doc in docs:
        for ref in _refs_in(root, doc, top_level):
            if any(c.exists() for c in ref.candidates):
                continue
            hit = {_repo_rel(root, c) for c in ref.candidates} & allowed.keys()
            if hit:
                used |= hit
                continue
            problems.append(Problem(ref.kind, ref.file, ref.line, ref.target))
    try:
        rel_allow = allowlist.resolve().relative_to(root).as_posix()
    except ValueError:
        rel_allow = allowlist.name
    for target, n in allowed.items():
        if (root / target).exists():
            problems.append(Problem("stale-allow", rel_allow, n, target, "exists now, remove the entry"))
        elif target not in used:
            problems.append(Problem("stale-allow", rel_allow, n, target, "no doc mentions it, remove the entry"))
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
