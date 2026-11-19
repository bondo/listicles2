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
# java.util.Properties: key ends at the first '=', ':' or whitespace; one optional '=' or ':' and blanks follow; # and ! start comments.
LINE_RE = re.compile(r"\s*([^\s=:]+)\s*[=:]?\s*(.*)")


def _values(text):
    """key -> list of raw values of the active lines of a .properties text."""
    found = {}
    for line in text.splitlines():
        if line.lstrip()[:1] in ("#", "!"):
            continue
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
