"""Build guards (M1-51, issue 257, checklist follow-ups 3-5 in docs/ANDROID-BEST-PRACTICES.md). Three checks over the working tree:

  1. Catalog-only coordinates: a Gradle build file (`*.gradle.kts`, `*.gradle`) may not name a dependency or a plugin version as a
     literal. `implementation("g:a:1.0")`, `platform("g:a:1.0")`, `add("classpath", "g:a:1.0")`, `force("g:a:1.0")`, a `group = ...`
     map notation, `id("x") version "1.0"` and a version catalog declared in Gradle code (`versionCatalogs`) all fail; the library or
     plugin goes in gradle/libs.versions.toml and is used as `libs.<name>`. A literal that has to stay (a fixture project) says why on
     its own line: `// justified: <at least 3 words>` (the rule of scripts/guards.sh).
  2. targetSdk floor: every `targetSdk` in a build file is a literal at or above TARGET_SDK_FLOOR, the Play minimum for new apps and
     updates (36 since 2026-08-31). A value this script cannot read (an expression, a variable, a preview) fails too.
  3. Manifest: no `android:usesCleartextTraffic` or `cleartextTrafficPermitted` other than "false" (manifests and every network security
     config under res/xml*), and an `<application>` whose `allowBackup` is not "false" (or is missing, which means true) must have both
     `android:dataExtractionRules` and `android:fullBackupContent`, as `@xml/<name>` with that file present.

Every check also fails when it found nothing to look at (no build files or declarations, no targetSdk, no manifest with an
`<application>`), so a moved or renamed file cannot make it pass vacuously.

Known gaps (the guard reads text, not the build): a coordinate held in a variable (`val c = "g:a:1"; implementation(c)`), one whose
group is interpolated (`"${g}:a:1"`), a dependency declared through a Gradle configuration that is neither named like one
(`...Implementation`, `...Api`, `...CompileOnly`, ...) nor declared in a build file with `configurations.create(...)` or
`by configurations.creating`, and `tools:replace` or manifest placeholders that change a manifest value after merging.

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


# -- the justified: escape hatch (same rule as scripts/guards.sh) ---------------------------------------------------------------------

def justified(line):
    """True when the line has `justified:` followed by a reason of at least 3 words (runs of 2 or more ASCII letters)."""
    i = line.find("justified:")
    if i < 0:
        return False
    reason = line[i + 10 :]
    for end in ("*/", "-->"):
        j = reason.find(end)
        if j >= 0:
            reason = reason[:j]
    m = re.search(r"[ \t](#|//)[ \t]*[A-Za-z]", reason)
    if m:
        reason = reason[: m.start() + 1]
    return len(re.findall(r"[A-Za-z][A-Za-z]+", reason)) >= 3


# -- 1. catalog-only coordinates ------------------------------------------------------------------------------------------------

CONFIG_SUFFIXES = (
    "implementation", "api", "compileonly", "runtimeonly", "annotationprocessor", "kapt", "ksp", "classpath", "plugins",
    "lintchecks", "lintpublish", "corelibrarydesugaring", "ruleset",
)
DECLARED = [
    re.compile(r"\b(?:val|var)\s+(\w+)\s+by\s+configurations\s*\.\s*(?:creating|registering|dependencyScope|resolvable|consumable)\b"),
    re.compile(r"\bconfigurations\s*\.\s*(?:create|register|maybeCreate|dependencyScope|resolvable|consumable)\s*\(\s*[\"'](\w+)[\"']"),
]
WS = r"[ \t\r\n]*"
COORD = r"[A-Za-z0-9_.-]+:[A-Za-z0-9_.-]+(?=[:\"'])"  # group:artifact are literal; the version may be anything
CALL = re.compile(r"""(?<![\w.$])(["']?)([A-Za-z_]\w*)\1(?:[ \t]*\(|[ \t]+(?=[\w"']))""" + WS)
WRAP = re.compile(r"(?:platform|enforcedPlatform|module|create)" + WS + r"\(" + WS)
LITERAL = re.compile(r"""(["'])(""" + COORD + ")")
GROUP_NOTATION = re.compile(r"group" + WS + r"[:=]")
ADD = re.compile(r"""(?<![\w$])add""" + WS + r"""\(""" + WS + r"""["'][^"'\n]*["']""" + WS + "," + WS + r"""(["'])(""" + COORD + ")")
STANDALONE = re.compile(
    r"""(?<![\w$])(?:force|useModule|platform|enforcedPlatform|module|dependencies\s*\.\s*create)""" + WS + r"\(" + WS + r"""(["'])(""" + COORD + ")"
)
PLUGIN_VERSION = re.compile(r"""[)"']""" + WS + r"""version""" + WS + r"""\(?""" + WS + r"""["']""")
CATALOG_IN_CODE = re.compile(r"\bversionCatalogs\b")


def declared_configurations(sources):
    names = set()
    for code in sources:
        for rx in DECLARED:
            names.update(rx.findall(code))
    return names


def is_config(name, declared):
    return name in declared or name.lower().endswith(CONFIG_SUFFIXES)


def scan_catalog(root):
    """(problems, number of Gradle files, number of dependency declarations)."""
    files = gradle_files(root)
    raw = {p: read(root, p) for p in files}
    code = {p: strip(t) for p, t in raw.items()}
    declared = declared_configurations(code.values())
    problems = []
    declarations = 0
    for p in files:
        text, lines = code[p], raw[p].split("\n")
        hits = {}  # offset -> what was found, so one literal found by two patterns is reported once

        for m in CALL.finditer(text):
            if not is_config(m.group(2), declared):
                continue
            declarations += 1
            pos = m.end()
            while True:
                w = WRAP.match(text, pos)
                if not w:
                    break
                pos = w.end()
            lit = LITERAL.match(text, pos)
            if lit:
                hits.setdefault(lit.start(2), f'dependency "{lit.group(2)}..." in {m.group(2)}(...)')
            elif GROUP_NOTATION.match(text, pos):
                hits.setdefault(pos, f"dependency in group/name/version notation in {m.group(2)}(...)")
        for m in ADD.finditer(text):
            hits.setdefault(m.start(2), f'dependency "{m.group(2)}..." in add(...)')
        for m in STANDALONE.finditer(text):
            hits.setdefault(m.start(2), f'dependency "{m.group(2)}..."')
        for m in PLUGIN_VERSION.finditer(text):
            hits.setdefault(m.start(), "plugin version")
        for m in CATALOG_IN_CODE.finditer(text):
            hits.setdefault(m.start(), "a version catalog declared in Gradle code")
        for offset, what in sorted(hits.items()):
            line = line_of(text, offset)
            if justified(lines[line - 1]):
                continue
            problems.append(f"{p}:{line}: {what} must come from the version catalog gradle/libs.versions.toml (libs.<name>), or carry `// justified: <reason>`")
    return problems, len(files), declarations


def catalog_stats(root):
    _problems, files, declarations = scan_catalog(root)
    return files, declarations


def catalog_problems(root):
    problems, files, declarations = scan_catalog(root)
    if files == 0:
        problems.append("no Gradle build files found (the catalog check would pass vacuously)")
    elif declarations == 0:
        problems.append("no dependency declarations found in any Gradle build file (the catalog check would pass vacuously)")
    return problems


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
        for element in top.iter():
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
    problems = catalog_problems(root) + target_sdk_problems(root) + manifest_problems(root)
    if problems:
        for p in problems:
            print(f"build-guards: {p}")
        return 1
    files, declarations = catalog_stats(root)
    sdk = min(v for _p, _l, v in target_sdk_values(root))
    manifests = len(application_manifests(root))
    print(f"build-guards: ok ({files} Gradle files, {declarations} dependency declarations, targetSdk {sdk}, {manifests} manifest)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
