"""Build guards (M1-51 and M1-58, issue 257, checklist follow-ups 4 and 5 in docs/ANDROID-BEST-PRACTICES.md): the targetSdk floor and the
manifest cleartext and backup rules.

1. targetSdk floor. Every `targetSdk` in a Gradle build file (`*.gradle.kts`, `*.gradle`) is a literal at or above TARGET_SDK_FLOOR, the Play minimum for new
apps and updates (36 since 2026-08-31). A value this script cannot read (an expression, a variable, a preview) fails too, and so does any
other way of setting it (a qualifier or call chain it does not know), and so does a tree with no targetSdk at all, so a moved or renamed
build file cannot make the check pass vacuously. Comments and strings are ignored.

2. Manifest. No `android:usesCleartextTraffic` or `cleartextTrafficPermitted` other than "false" (every manifest and every network security
   config under `res/xml*`), and an `<application>` whose `allowBackup` is not "false" (a missing one counts as true in the main manifest;
   an overlay manifest inherits it) must have both `android:dataExtractionRules` and `android:fullBackupContent`, each `@xml/<name>` with
   that file present. A value that is not a literal, an unreadable file, and a tree with no manifest that has an `<application>` fail too.
   The one scope exception: files of a `src/androidTest/` source set are not checked for cleartext (the test APK talks plain HTTP to the
   Auth emulator on 10.0.2.2 and is never shipped); every other source set is.

The catalog-only coordinates guard (follow-up 3, M1-59) is added to this script by its own PR.

Run: python3 -I scripts/check_build_guards.py [repo root]   (exit 1 and one `build-guards: ...` line per problem; one line when fine)
"""

import os
import re
import sys
import xml.etree.ElementTree as ET

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


# -- targetSdk floor ----------------------------------------------------------------------------------------------------------------

# A statement that sets a target: `targetSdk = 36`, `targetSdk(36)`, `android.defaultConfig.targetSdk = 36`, `this.targetSdk = 36` and the
# setters `setTargetSdk(36)`, `setTargetSdkVersion(36)` (R1-01). A read (`val x = android.defaultConfig.targetSdk`, `f(x.targetSdk)`) is not
# at the start of a statement, so it never matches.
TARGET_STATEMENT = re.compile(
    r"(?:^|[{;])[ \t]*(?:\w+\??\.)*(setTargetSdk(?:Version)?|targetSdk(?:Version|Preview)?)\b(?=[ \t]*[=({]|[ \t]+[\w\"'])", re.M
)
# Every mention of the name. One that is followed by `=`, `(`, `{` or a literal and was not read as a statement above could set a target in
# a form the pattern above does not know (`getByName("x").targetSdk = 30`, `a!!.targetSdk = 30`, a chain split over lines), so it fails
# closed (R2-01) instead of hiding a low value next to a plain one. A read (`f(x.targetSdk)`, `x.targetSdk == 36`, `targetSdk: Int`) is not.
TARGET_TOKEN = re.compile(r"(?<![\w$])(?:setTargetSdk(?:Version)?|targetSdk(?:Version|Preview)?)\b")
TARGET_SETS = re.compile(r"[ \t\r\n]*(?:=(?!=)|\(|\{)|[ \t]+[\d\"']")
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
        statements = {m.start(1) for m in TARGET_STATEMENT.finditer(text)}
        for m in TARGET_TOKEN.finditer(text):
            if m.start() not in statements and TARGET_SETS.match(text, m.end()):
                problems.append(
                    f"{p}:{line_of(text, m.start())}: {m.group()} is set in a form this guard cannot read; "
                    f"write `targetSdk = <number>` as its own statement, so the floor of {TARGET_SDK_FLOOR} can be checked"
                )
    return problems, values


def target_sdk_values(root):
    return scan_target_sdk(root)[1]


def target_sdk_problems(root):
    problems, values = scan_target_sdk(root)
    if not values and not problems:
        problems.append("no targetSdk found in any Gradle build file (the floor check would pass vacuously)")
    return problems


# -- 3. manifest -------------------------------------------------------------------------------------------------------------------------

def local(name):
    return name.rsplit("}", 1)[-1]


def attrs(element):
    return {local(k): v for k, v in element.attrib.items()}


def xml_resource_dirs(p):
    parts = p.split("/")
    return len(parts) >= 3 and parts[-2].startswith("xml") and parts[-3] == "res" and p.endswith(".xml")


def module_of(p):
    """The directory above `src/<set>/` of a source file, or its own directory (`""` is the repository root)."""
    parts = p.split("/")
    for i in range(len(parts) - 2):
        if parts[i] == "src":
            return "/".join(parts[:i])
    return "/".join(parts[:-1])


def is_overlay(p):
    return re.search(r"(^|/)src/(?!main/)[^/]+/AndroidManifest\.xml$", p) is not None


def is_android_test(p):
    """True for a file of a module's `src/androidTest/` source set: it goes into the test APK only, which is never shipped."""
    return "/src/androidTest/" in "/" + p


def load_manifests(root):
    """(application manifests as {path: root element}, other problems, number of manifest files seen)."""
    found, problems, seen = {}, [], 0
    for p in walk(root):
        if os.path.basename(p) != "AndroidManifest.xml":
            continue
        seen += 1
        try:
            tree = ET.parse(os.path.join(root, *p.split("/")))
        except (ET.ParseError, OSError) as e:
            problems.append(f"{p}: cannot parse the manifest ({e})")
            continue
        if any(local(c.tag) == "application" for c in tree.getroot()):
            found[p] = tree.getroot()
    return found, problems, seen


def application_manifests(root):
    return sorted(load_manifests(root)[0])


def xml_resource(root, module, value):
    """None when `value` is `@xml/<name>` and <module>/src/*/res/xml*/<name>.xml exists, else the reason it is not."""
    m = re.fullmatch(r"@xml/([A-Za-z0-9_]+)", value or "")
    if not m:
        return f'"{value}" is not an @xml/<name> resource'
    base = os.path.join(root, *module.split("/")) if module else root
    src = os.path.join(base, "src")
    if os.path.isdir(src):
        for variant in sorted(os.listdir(src)):
            res = os.path.join(src, variant, "res")
            if os.path.isdir(res) and any(
                os.path.isfile(os.path.join(res, d, m.group(1) + ".xml")) for d in os.listdir(res) if d.startswith("xml")
            ):
                return None
    return f"{value} is missing: no res/xml*/{m.group(1)}.xml in module {module or '.'}"


def manifest_problems(root):
    apps, problems, seen = load_manifests(root)
    for p, top in sorted(apps.items()):
        app = next(c for c in top if local(c.tag) == "application")
        a = attrs(app)
        for element in () if is_android_test(p) else top.iter():
            v = attrs(element).get("usesCleartextTraffic")
            if v is not None and v.lower() != "false":
                problems.append(f'{p}: android:usesCleartextTraffic="{v}"; cleartext traffic must stay off')
        backup = a.get("allowBackup")
        if backup is None and is_overlay(p):
            continue  # inherits the value of the main manifest, which is checked itself
        if backup is not None and backup.lower() == "false":
            continue
        rules = {k: a.get(k) for k in ("dataExtractionRules", "fullBackupContent")}
        if is_overlay(p):  # a rule attribute the overlay lacks comes from the main manifest of the module
            mod = module_of(p)
            main = apps.get((mod + "/" if mod else "") + "src/main/AndroidManifest.xml")
            if main is not None:
                ma = attrs(next(c for c in main if local(c.tag) == "application"))
                rules = {k: v if v is not None else ma.get(k) for k, v in rules.items()}
        state = "missing, which means true" if backup is None else f'"{backup}"'
        absent = [f"android:{k}" for k, v in rules.items() if v is None]
        if absent:
            problems.append(f"{p}: android:allowBackup is {state} without {' and '.join(absent)}; turn backup off or add both rule files")
            continue
        for k, v in rules.items():
            why = xml_resource(root, module_of(p), v)
            if why:
                problems.append(f"{p}: android:{k} {why}")
    for p in walk(root):
        if not xml_resource_dirs(p):
            continue
        if is_android_test(p):
            continue  # a network security config of the test APK may allow the emulators' plain HTTP
        try:
            top = ET.parse(os.path.join(root, *p.split("/"))).getroot()
        except (ET.ParseError, OSError) as e:
            problems.append(f"{p}: cannot parse the XML resource ({e})")
            continue
        if local(top.tag) != "network-security-config":
            continue
        for element in top.iter():
            v = attrs(element).get("cleartextTrafficPermitted")
            if v is not None and v.lower() != "false":
                problems.append(f'{p}: cleartextTrafficPermitted="{v}" on <{local(element.tag)}>; cleartext traffic must stay off')
    if not apps and not any("cannot parse" in x for x in problems):
        problems.append("no manifest with an <application> element found (the manifest check would pass vacuously)")
    return problems


def main(argv):
    root = os.path.abspath(argv[1]) if len(argv) > 1 else os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
    problems = target_sdk_problems(root) + manifest_problems(root)
    if problems:
        for p in problems:
            print(f"build-guards: {p}")
        return 1
    sdk = min(v for _p, _l, v in target_sdk_values(root))
    manifests = len(application_manifests(root))
    print(f"build-guards: ok (targetSdk {sdk}, floor {TARGET_SDK_FLOOR}, {manifests} manifest)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
