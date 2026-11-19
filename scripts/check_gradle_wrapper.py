"""Checks that the Gradle wrapper pins its distribution by checksum.

gradle/wrapper/gradle-wrapper.properties needs `distributionSha256Sum=<64 lowercase hex>` next to a
https://services.gradle.org/distributions/ `distributionUrl`: the wrapper then refuses a zip whose sha256 differs,
so a tampered or corrupted download cannot become the build tool. The value is the one published at
`<distributionUrl>.sha256` on services.gradle.org. Offline, this check cannot compare the two; a wrong sum fails the
wrapper's own download check on the next cold build (CI), and scripts/merge_ready.py accepts a Dependabot bump of both lines.
Run: python3 -I scripts/check_gradle_wrapper.py  (exit 1 and one line per problem).
"""

import re
import sys
from pathlib import Path

PROPS = ("gradle", "wrapper", "gradle-wrapper.properties")
SUM_KEY = "distributionSha256Sum"
URL_KEY = "distributionUrl"
SUM_RE = re.compile(r"[0-9a-f]{64}")
URL_RE = re.compile(r"https\\://services\.gradle\.org/distributions/gradle-[\w.-]+-(?:bin|all)\.zip")
# java.util.Properties: lines end only at \n, \r or \r\n and the only blanks are space, tab and form feed (not str.splitlines(),
# str.lstrip() or \s, which also act on \v, \x1c-\x1e, U+0085, U+2028/9, NBSP and other Unicode characters Java treats as plain text).
# The key ends at the first '=', ':' or blank; one optional '=' or ':' and blanks follow; # and ! start comments.
BLANKS = " \t\f"
LINE_BREAK = re.compile(r"\r\n|\r|\n")
LINE_RE = re.compile(r"[ \t\f]*([^ \t\f=:]+)[ \t\f]*[=:]?[ \t\f]*(.*)")


def _continues(line):
    """True if the line ends in an odd number of backslashes: java.util.Properties joins it with the next line."""
    return (len(line) - len(line.rstrip("\\"))) % 2 == 1


def _logical_lines(text):
    """The logical lines of a .properties text: comment and blank lines dropped, continued lines joined (leading blanks of the
    continuation line removed, as Java does), so a key folded into the previous property is not seen as a key of its own."""
    physical = iter(LINE_BREAK.split(text))
    for raw in physical:
        line = raw.lstrip(BLANKS)
        if not line or line[0] in "#!":
            continue
        while _continues(line):
            line = line[:-1] + next(physical, "").lstrip(BLANKS)
        yield line


def _values(text):
    """key -> list of raw values of the active logical lines of a .properties text."""
    found = {}
    for line in _logical_lines(text):
        match = LINE_RE.fullmatch(line)
        if match:
            found.setdefault(match.group(1), []).append(match.group(2))
    return found


def check_properties(text):
    values = _values(text)
    problems = []
    sums = values.get(SUM_KEY, [])
    if not sums:
        problems.append(f"{SUM_KEY} is missing")
    elif len(sums) > 1:
        problems.append(f"{SUM_KEY} is set more than once")
    elif not SUM_RE.fullmatch(sums[0]):
        shown = f"got {sums[0]!r}" if sums[0].strip() else "got an empty value"
        problems.append(f"{SUM_KEY} must be 64 lowercase hex characters (sha256), {shown}")
    elif len(set(sums[0])) == 1:
        problems.append(f"{SUM_KEY} is a placeholder (one repeated digit), not a real checksum")
    urls = values.get(URL_KEY, [])
    if not urls:
        problems.append(f"{URL_KEY} is missing")
    elif not all(URL_RE.fullmatch(u) for u in urls):
        problems.append(f"{URL_KEY} must be a https://services.gradle.org/distributions/ zip (the checksum is the one published there)")
    return problems


def main(root):
    path = Path(root).joinpath(*PROPS)
    if not path.is_file():
        print(f"gradle-wrapper: {'/'.join(PROPS)} not found")
        return 1
    problems = check_properties(path.read_text(encoding="utf-8"))
    for p in problems:
        print(f"gradle-wrapper: {p}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent))
