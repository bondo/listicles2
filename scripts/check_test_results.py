"""Fails when a test class in a module's test sources has no result XML (silently skipped, e.g. no JUnit 4 engine).

Usage: python3 -I scripts/check_test_results.py <test-src-dir> <results-dir> [--filtered]
"""

import re
import sys
from pathlib import Path

PACKAGE = re.compile(r"^package\s+([\w.]+)", re.M)
# A top-level class declaration: starts in column 0, modifiers first.
CLASS = re.compile(r"^((?:\w+\s+)*?)class\s+(\w+)", re.M)
TEST_ANNOTATION = re.compile(r"@(?:Test|ParameterizedTest|TestFactory|RepeatedTest)\b")
# Classes that cannot produce a result XML of their own.
NOT_RUNNABLE = {"abstract", "private", "sealed", "annotation", "enum", "data", "inner"}


def test_classes(src: Path) -> list[str]:
    """Fully qualified names of runnable top-level classes whose own body holds a test annotation."""
    found = []
    for f in sorted(src.rglob("*.kt")):
        text = f.read_text(encoding="utf-8")
        package = PACKAGE.search(text)
        prefix = f"{package.group(1)}." if package else ""
        decls = list(CLASS.finditer(text))
        for i, d in enumerate(decls):
            end = decls[i + 1].start() if i + 1 < len(decls) else len(text)
            if set(d.group(1).split()) & NOT_RUNNABLE:
                continue
            if TEST_ANNOTATION.search(text[d.start() : end]):
                found.append(prefix + d.group(2))
    return found


def missing(src: Path, results: Path) -> list[str]:
    """Test classes without a TEST-<class>.xml in the results directory."""
    return [c for c in test_classes(src) if not (results / f"TEST-{c}.xml").is_file()]


def main(argv: list[str]) -> int:
    if argv[-1:] == ["--filtered"]:
        # A filtered run (--tests) runs a subset on purpose; skipped classes are expected.
        print("check_test_results: filtered test run, skipping the check")
        return 0
    if len(argv) != 2:
        print("usage: check_test_results.py <test-src-dir> <results-dir>", file=sys.stderr)
        return 2
    src, results = Path(argv[0]), Path(argv[1])
    if not src.is_dir():
        print(f"check_test_results: no test sources at {src}", file=sys.stderr)
        return 2
    absent = missing(src, results)
    for c in absent:
        print(f"check_test_results: {c} has no result XML in {results}: the test was silently skipped", file=sys.stderr)
    return 1 if absent else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
