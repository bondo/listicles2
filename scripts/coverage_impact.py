#!/usr/bin/env python3
"""Test-impact summary (M1-07, PLAN P19): which changed lines do the unit tests not execute?

Usage: python3 -I scripts/coverage_impact.py --xml <kover report.xml> --base <git ref>

Reads the Kover XML report (JaCoCo format, `./gradlew koverXmlReport`) and the diff between the merge base of <ref> and HEAD and
the working tree (committed, staged, unstaged and untracked changes), and prints a markdown summary on stdout: the changed lines
that have code and ran no instruction, per file. It reports and exits 0; the coverage floors (koverVerify) are the gate.
Two modules with the same package and file name would share one entry (not a case here).
Missing, unreadable or empty coverage data, or a ref that cannot be diffed, is an error (exit 2, nothing on stdout): "nothing
uncovered" only ever means "measured, and covered".
"""

import argparse
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


class CoverageError(Exception):
    """The coverage data or the diff cannot be used."""


def changed_lines(diff_text):
    """{path: {line numbers}} of the added or changed lines of a `git diff -U0` text (new-file numbering)."""
    out = {}
    path = None
    in_header = False  # between `diff --git` and the first hunk: only there is `+++ ` a file name, not added content
    for line in diff_text.splitlines():
        if line.startswith("diff --git "):
            in_header, path = True, None
        elif in_header and line.startswith("+++ "):
            target = line[4:]
            path = None if target == "/dev/null" else target.removeprefix("b/")
        elif m := HUNK.match(line):
            in_header = False
            start, count = int(m.group(1)), 1 if m.group(2) is None else int(m.group(2))
            if path and count:
                out.setdefault(path, set()).update(range(start, start + count))
    return out


def coverage_lines(xml_text):
    """{package path/file: {line: covered}} for every line with code in a Kover (JaCoCo format) report."""
    try:
        root = ET.fromstring(xml_text)  # the DOCTYPE names a DTD that expat never fetches
    except ET.ParseError as e:
        raise CoverageError(f"the coverage report is not valid XML ({e})") from e
    if root.tag != "report":
        raise CoverageError("the file is not a coverage report (no <report> element)")
    found = {}
    for package in root.iter("package"):
        for source in package.iter("sourcefile"):
            lines = {int(ln.get("nr", "0")): int(ln.get("ci", "0")) > 0 for ln in source.iter("line")}
            if lines:
                found.setdefault(f"{package.get('name', '')}/{source.get('name', '')}", {}).update(lines)
    if not found:
        raise CoverageError("no coverage data: the report has no source file with executable lines (did the tests run?)")
    return found


@dataclass
class Impact:
    uncovered: dict  # path -> sorted line numbers
    measured: int  # changed lines that have code
    unmeasured: list  # changed main Kotlin files with no entry in the report


def is_main_kotlin(path):
    return path.endswith(".kt") and "/src/main/" in path


def impact(changed, coverage):
    uncovered, unmeasured, measured = {}, [], 0
    for path in sorted(changed):
        entry = next((v for k, v in coverage.items() if path.endswith("/" + k)), None)
        if entry is None:
            if is_main_kotlin(path):
                unmeasured.append(path)
            continue
        hit = sorted(n for n in changed[path] if n in entry)
        measured += len(hit)
        missed = [n for n in hit if not entry[n]]
        if missed:
            uncovered[path] = missed
    return Impact(uncovered, measured, unmeasured)


def ranges(lines):
    """[1, 2, 3, 5, 7, 8] -> '1-3, 5, 7-8'."""
    parts, i = [], 0
    while i < len(lines):
        j = i
        while j + 1 < len(lines) and lines[j + 1] == lines[j] + 1:
            j += 1
        parts.append(str(lines[i]) if i == j else f"{lines[i]}-{lines[j]}")
        i = j + 1
    return ", ".join(parts)


def render(r):
    total = sum(len(v) for v in r.uncovered.values())
    if total:
        head = f"### Test impact: {total} uncovered changed lines in {len(r.uncovered)} files ({r.measured} changed executable lines)"
    elif r.measured:
        head = f"### Test impact: {r.measured} changed executable lines, all covered"
    else:
        head = "### Test impact: no changed executable lines in the coverage report"
    out = [head]
    if r.uncovered:
        out += [""] + [f"- `{p}`: {ranges(v)}" for p, v in r.uncovered.items()]
    if r.unmeasured:
        out += ["", "Changed files with no coverage data (excluded, not compiled, or no tests run them):"]
        out += [f"- `{p}`" for p in r.unmeasured]
    return "\n".join(out) + "\n"


def git(*args, top=None):
    r = subprocess.run(["git", *(["-C", top] if top else []), *args], capture_output=True, text=True)
    if r.returncode:
        raise CoverageError(r.stderr.strip() or f"git {args[0]} failed")
    return r.stdout


def diff_since(base):
    """Added lines since the merge base of `base` and HEAD, in the working tree; untracked files count as all changed."""
    try:
        top = git("rev-parse", "--show-toplevel").strip()
        merge_base = git("merge-base", base, "HEAD", top=top).strip()
        changed = changed_lines(
            git("diff", "-U0", "--no-color", "--no-ext-diff", "--no-renames", "--src-prefix=a/", "--dst-prefix=b/", "--no-relative", merge_base, top=top)
        )
        for name in git("ls-files", "--others", "--exclude-standard", "-z", top=top).split("\0"):
            file = Path(top) / name
            if name and file.is_file():  # not a nested repository (`dir/`) or a broken link
                changed[name] = set(range(1, len(file.read_text(encoding="utf-8", errors="replace").splitlines()) + 1))
    except (CoverageError, OSError) as e:
        raise CoverageError(f"cannot diff against {base}: {e}") from e
    return changed


def main(argv):
    p = argparse.ArgumentParser(prog="coverage_impact.py", exit_on_error=False)
    p.add_argument("--xml", required=True)
    p.add_argument("--base", required=True)
    try:
        args = p.parse_args(argv)
    except (argparse.ArgumentError, SystemExit):
        print("usage: coverage_impact.py --xml <kover report.xml> --base <git ref>", file=sys.stderr)
        return 2
    try:
        try:
            text = Path(args.xml).read_text(encoding="utf-8")
        except OSError as e:
            raise CoverageError(f"cannot read {args.xml}: {e.strerror} (run ./gradlew koverXmlReport first)") from e
        coverage = coverage_lines(text)
        result = impact(diff_since(args.base), coverage)
    except CoverageError as e:
        print(f"coverage_impact: {e}", file=sys.stderr)
        return 2
    sys.stdout.write(render(result))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
