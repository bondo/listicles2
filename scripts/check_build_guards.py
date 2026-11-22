"""Build guards (M1-51, issue 257, checklist follow-up 4 in docs/ANDROID-BEST-PRACTICES.md): the targetSdk floor.

Every `targetSdk` in a Gradle build file (`*.gradle.kts`, `*.gradle`) is a literal at or above TARGET_SDK_FLOOR, the Play minimum for new
apps and updates (36 since 2026-08-31). A value this script cannot read (an expression, a variable, a preview) fails too, and so does a
tree with no targetSdk at all, so a moved or renamed build file cannot make the check pass vacuously. Comments and strings are ignored.

The manifest guard (follow-up 5, M1-58) and the catalog-only coordinates guard (follow-up 3, M1-59) are added to this script by their own PRs.

Run: python3 -I scripts/check_build_guards.py [repo root]   (exit 1 and one `build-guards: ...` line per problem; one line when fine)
"""

import os
import re
import sys

# Play: from 2026-08-31 new apps and updates must target API 36 or higher. Raise when the date changes; never lower.
TARGET_SDK_FLOOR = 36

PRUNE = {"build", ".gradle", "node_modules", ".git", ".idea", ".kotlin"}


def walk(root):
    """Relative paths (with `/`) of all files under root, without build output and tool directories."""
    for base, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in PRUNE)
        for f in sorted(files):
            yield os.path.relpath(os.path.join(base, f), root).replace(os.sep, "/")


def gradle_files(root):
    return [p for p in walk(root) if p.endswith(".gradle.kts") or p.endswith(".gradle")]


def read(root, rel):
    with open(os.path.join(root, *rel.split("/")), encoding="utf-8", errors="replace") as f:
        return f.read()


# -- source text without comments --------------------------------------------------------------------------------------------------

def strip(text, blank_strings=False):
    """The text with every comment replaced by spaces (newlines kept, so offsets and lines stay); with blank_strings also the
    contents of string literals. Reads Kotlin (`"..."` with `${...}`, `\"\"\"...\"\"\"`) and Groovy (`'...'`) strings."""
    out = list(text)
    n = len(text)

    def blank(a, b):
        for k in range(a, b):
            if out[k] != "\n":
                out[k] = " "

    def code(i, nested):
        depth = 0
        while i < n:
            c = text[i]
            if text.startswith("//", i):
                j = text.find("\n", i)
                j = n if j < 0 else j
                blank(i, j)
                i = j
            elif text.startswith("/*", i):
                j = text.find("*/", i + 2)
                j = n if j < 0 else j + 2
                blank(i, j)
                i = j
            elif c in "\"'":
                i = string(i)
            elif nested and c == "{":
                depth += 1
                i += 1
            elif nested and c == "}":
                if depth == 0:
                    return i + 1
                depth -= 1
                i += 1
            else:
                i += 1
        return i

    def string(i):
        start = i
        q = text[i]
        triple = text.startswith(q * 3, i)
        i += 3 if triple else 1
        while i < n:
            c = text[i]
            if triple and text.startswith(q * 3, i):
                i += 3
                break
            if not triple and c == "\\":
                i += 2
                continue
            if not triple and c == q:
                i += 1
                break
            if not triple and c == "\n":  # an unterminated string ends at the line
                break
            if q == '"' and c == "$" and text.startswith("{", i + 1):
                i = code(i + 2, True)
                continue
            i += 1
        if blank_strings:
            blank(start + 1, max(start + 1, i - 1))
        return i

    code(0, False)
    return "".join(out)


def line_of(text, offset):
    return text.count("\n", 0, offset) + 1


# -- 2. targetSdk floor ----------------------------------------------------------------------------------------------------------------

TARGET_STATEMENT = re.compile(r"(?:^|[{;])[ \t]*(targetSdk(?:Version|Preview)?)\b(?=[ \t]*[=({]|[ \t]+[\w\"'])", re.M)
TARGET_ASSIGN = re.compile(r"[ \t]*=[ \t]*(\d+)(?=[ \t]*(?:$|;|\}))", re.M)
TARGET_CALL = re.compile(r"[ \t]*\([ \t]*(\d+)[ \t]*\)")
TARGET_GROOVY = re.compile(r"[ \t]+(\d+)(?=[ \t]*(?:$|;|\}))", re.M)
TARGET_BLOCK = re.compile(r"[ \t\r\n]*\{[ \t\r\n]*version[ \t]*=[ \t]*release[ \t]*\([ \t]*(\d+)[ \t]*\)")


def scan_target_sdk(root):
    """(problems, [(path, line, value)]) over every statement that sets a targetSdk in a Gradle file."""
    problems, values = [], []
    for p in gradle_files(root):
        text = strip(read(root, p), blank_strings=True)
        for m in TARGET_STATEMENT.finditer(text):
            name, end = m.group(1), m.end()
            line = line_of(text, m.start(1))
            if name == "targetSdkPreview":
                problems.append(
                    f"{p}:{line}: targetSdkPreview: a preview target is not accepted by Play; use a released targetSdk of at least {TARGET_SDK_FLOOR}"
                )
                continue
            r = TARGET_ASSIGN.match(text, end) or TARGET_CALL.match(text, end) or TARGET_GROOVY.match(text, end) or TARGET_BLOCK.match(text, end)
            if not r:
                problems.append(f"{p}:{line}: {name} is not a plain integer, so the floor of {TARGET_SDK_FLOOR} cannot be checked; write the number")
                continue
            value = int(r.group(1))
            values.append((p, line, value))
            if value < TARGET_SDK_FLOOR:
                problems.append(f"{p}:{line}: targetSdk {value} is below the Play minimum {TARGET_SDK_FLOOR}")
    return problems, values


def target_sdk_values(root):
    return scan_target_sdk(root)[1]


def target_sdk_problems(root):
    problems, values = scan_target_sdk(root)
    if not values and not problems:
        problems.append("no targetSdk found in any Gradle build file (the floor check would pass vacuously)")
    return problems


def main(argv):
    root = os.path.abspath(argv[1]) if len(argv) > 1 else os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
    problems = target_sdk_problems(root)
    if problems:
        for p in problems:
            print(f"build-guards: {p}")
        return 1
    sdk = min(v for _p, _l, v in target_sdk_values(root))
    print(f"build-guards: ok (targetSdk {sdk}, floor {TARGET_SDK_FLOOR})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
