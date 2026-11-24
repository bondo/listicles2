"""Build guards (M1-51, M1-58 and M1-59, issue 257, checklist follow-ups 3, 4 and 5 in docs/ANDROID-BEST-PRACTICES.md): the targetSdk
floor, the manifest cleartext and backup rules, and catalog-only coordinates.

1. targetSdk floor. Every `targetSdk` in a Gradle build file (`*.gradle.kts`, `*.gradle`) is a literal at or above TARGET_SDK_FLOOR, the Play minimum for new
apps and updates (36 since 2026-08-31). A value this script cannot read (an expression, a variable, a preview) fails too, and so does any
other way of setting it (a qualifier or call chain it does not know), and so does a tree with no targetSdk at all, so a moved or renamed
build file cannot make the check pass vacuously. Comments and strings are ignored.

2. Manifest. No `android:usesCleartextTraffic` or `cleartextTrafficPermitted` other than "false" (every manifest and every network security
   config under `res/xml*`), and an `<application>` whose `allowBackup` is not "false" (a missing one counts as true in the main manifest;
   an overlay manifest inherits it) must have both `android:dataExtractionRules` and `android:fullBackupContent`, each `@xml/<name>` with
   that file present. A value that is not a literal, an unreadable file, and a tree with no manifest that has an `<application>` fail too.
   Attributes are read by namespace (`android:` in a manifest, none in a network security config), so a `tools:` attribute cannot hide one.
   An overlay manifest (`src/<set>/`) without `allowBackup` is skipped only when its module has a main manifest with an `<application>`.
   The one scope exception: files of a `src/androidTest/` source set are not checked for cleartext (the test APK talks plain HTTP to the
   Auth emulator on 10.0.2.2 and is never shipped), and such a manifest without `allowBackup` needs no main manifest; every other source
   set is checked.

3. Catalog-only coordinates (M1-59, follow-up 3). Libraries and plugins come from gradle/libs.versions.toml as `libs.<name>`. A Gradle file
   fails on: a string literal that starts with a literal `group:artifact` anywhere inside a `dependencies { }` block (so any
   configuration, Kotlin or Groovy, wrapped in `platform(...)` or not, in `constraints` too; also `dependencies.apply { }`, `run`,
   `also`, `with` and `with(dependencies) { }`); group notation with a literal group (named arguments, a Groovy map, `mapOf`) and
   the positional `(group, name, ...)` form there (`exclude` is not a declaration); outside such a block `add(<conf>, "g:a...")`,
   `dependencies.<conf>("g:a...")`, `force`, `useModule`, `useTarget` (also in group notation), `platform`, `enforcedPlatform`,
   `module` and `create` with a literal coordinate, and one in a `forcedModules` assignment; a literal version
   (`id(...) version "1"`, `.version("1")`, `useVersion("1")`, and `version = "1"` or `strictly("1")` in a dependencies block); and
   a version catalog declared in Gradle code (`versionCatalogs`).
   A literal that has to stay says why in a comment on its line: `// justified: <at least 3 words>` (the rule of scripts/guards.sh).
   No Gradle file, or no dependency declaration in any `dependencies { }` block, fails too. Known gaps (it reads text, not the build):
   a coordinate held in a variable or with an interpolated group (`"$g:a:1"`), and a declaration made through a helper function.

4. Convention plugins (M1-46, issue 217). No Gradle file or build-logic/ Kotlin source reaches other projects: any use of `allprojects`,
   `subprojects` or `childProjects` (also `getAllprojects()` and the like, so a read such as `allprojects.flatMap { ... }` too; M1-68 part B3,
   issue 48), member access on (also after `?` or `!!`) or a configure block for `project(...)`/`findProject(...)`, a `project(path, ...)`
   call with an Action or lambda argument, `evaluationDependsOn`, and
   `gradle.allprojects`/`beforeProject`/`afterProject`/`projectsLoaded`/`projectsEvaluated`. M1-84 (isolated projects): any `rootProject`
   (also `getRootProject()`, passed, held in a variable or in string template code, `gradle.rootProject { }`) other than
   `isolated.rootProject`, which reads the root's directory; in a settings file `rootProject` is the project descriptor, so there only
   `rootProject.name`, `.buildFileName` and `.projectDir` pass. `parent` (also `getParent()`) with the implicit receiver or on `project`,
   `target`, `this` or `getProject()` (also backticked, in parentheses, after `!!` or a cast). A `project(...)`/`findProject(...)`
   that is not a direct argument of a dependency declaration (an allowlist: a call that is a whole statement in a `dependencies { }` block, `"conf"(...)`, Groovy
   `conf project(...)`, or `dependencies.<conf>(...)`, with only `testFixtures`/`platform`/`enforcedPlatform` in between), so one held
   in a variable or in `configure(listOf(project(...))) { }` fails; so do a callable reference (`::project`, Groovy `.&project`), a
   Groovy method name in any string (`'project'(...)`, triple-quoted, slashy, `.&"project"`) or built by a GString (`owner."${n}"`),
   Groovy command syntax (`project ':app', { }`) and `invokeMethod`; a backticked name counts as the plain one (PR 384 R1, R2).
   A project dependency
   (`implementation(project(":x"))`, `dependencies.project(mapOf(...))`) is fine. One finding per line. Known gaps: `.parent` on
   another receiver (File.parent has the same name), and a Project reached through a helper function. Fails closed on: a Kotlin
   parameter, named argument or Groovy map key called `parent`, a settings plugin in build-logic/ Kotlin that reads
   `settings.rootProject`, and a Groovy `conf project(':a'), project(':b')` list.
   Every module in settings.gradle.kts
   `include(...)` applies exactly one module convention plugin (MODULE_CONVENTION) and does not set again what they own (see OWNED). build-logic/ sets no
   targetSdk (check 1 reads Gradle files only). No settings.gradle.kts: the module part is skipped (the real-repository test reads four).
   The root build's `val listiclesModules = listOf(...)` names exactly the settings modules, and detekt depends on each one's
   `listiclesChecks` by task path (aggregation_problems; M1-68 part B2: each module runs its own checks, the root reads none).

Run: python3 -I scripts/check_build_guards.py [repo root]   (exit 1 and one `build-guards: ...` line per problem; one line when fine)
"""

import os
import re
import sys
import xml.etree.ElementTree as ET
from functools import partial

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

TEMPLATE_NAME = re.compile(r"\$[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*")  # `$name`, Groovy `$a.b.c`


def strip(text, blank_strings=False, strings=None, templates=False):
    """The text with every comment replaced by spaces (newlines kept, so offsets and lines stay); with blank_strings also the
    contents of string literals. Reads Kotlin (`"..."` with `${...}`, `\"\"\"...\"\"\"`) and Groovy (`'...'`) strings. A list passed
    as strings receives the offset where the contents of each string literal start. With templates, blank_strings keeps the code of
    `${...}` and `$name` templates (`$a.b.c` for Groovy), so check 4 reads `"${rootProject.projectDir}"`."""
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
        keep = []  # template code spans kept with templates
        triple = text.startswith(q * 3, i)
        i += 3 if triple else 1
        if strings is not None:
            strings.append(i)
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
                j = code(i + 2, True)
                keep.append((i, j))
                i = j
                continue
            m = TEMPLATE_NAME.match(text, i) if q == '"' else None
            if m:
                keep.append((i + 1, m.end()))  # without the `$`, so the name reads as code
                i = m.end()
                continue
            i += 1
        if blank_strings:
            a = start + 1
            for k0, k1 in (keep if templates else []):
                blank(a, k0)
                a = k1
            blank(a, max(a, i - 1))
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


ANDROID_NS = "{http://schemas.android.com/apk/res/android}"


def android_attrs(element):
    """The `android:` attributes of a manifest element by local name; `tools:` and other namespaces with the same local name are not read."""
    return {k[len(ANDROID_NS):]: v for k, v in element.attrib.items() if k.startswith(ANDROID_NS)}


def plain_attrs(element):
    """The attributes without a namespace (those of a network security config) by name."""
    return {k: v for k, v in element.attrib.items() if not k.startswith("{")}


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
        a = android_attrs(app)
        for element in () if is_android_test(p) else top.iter():
            v = android_attrs(element).get("usesCleartextTraffic")
            if v is not None and v.lower() != "false":
                problems.append(f'{p}: android:usesCleartextTraffic="{v}"; cleartext traffic must stay off')
        backup = a.get("allowBackup")
        mod = module_of(p)
        main = apps.get((mod + "/" if mod else "") + "src/main/AndroidManifest.xml")
        if backup is None and is_overlay(p) and (main is not None or is_android_test(p)):
            continue  # inherits the value of the module's main manifest, which has an <application> and is checked itself; a test APK is not shipped
        if backup is not None and backup.lower() == "false":
            continue
        rules = {k: a.get(k) for k in ("dataExtractionRules", "fullBackupContent")}
        if is_overlay(p) and main is not None:  # a rule attribute the overlay lacks comes from the main manifest of the module
            ma = android_attrs(next(c for c in main if local(c.tag) == "application"))
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
            v = plain_attrs(element).get("cleartextTrafficPermitted")
            if v is not None and v.lower() != "false":
                problems.append(f'{p}: cleartextTrafficPermitted="{v}" on <{local(element.tag)}>; cleartext traffic must stay off')
    if not apps and not any("cannot parse" in x for x in problems):
        problems.append("no manifest with an <application> element found (the manifest check would pass vacuously)")
    return problems

# -- 3. catalog-only coordinates -----------------------------------------------------------------------------------------------------

def justified(line):
    """True when the line has `justified:` followed by a reason of at least 3 words (runs of 2 or more ASCII letters): just() of
    scripts/guards.sh. The reason ends at `*/`, `-->` and a following comment opener."""
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


COORD = re.compile(r"[A-Za-z0-9_.-]+:[A-Za-z0-9_.-]+(?=[:@\"']|$)", re.M)  # a literal group:artifact; the version may be anything
WS = r"[ \t\r\n]*"
# `dependencies { }`, `dependencies.constraints { }` and the scope functions `dependencies.apply { }` (run, also, with), `with(dependencies) { }`.
DEPS_BLOCK = re.compile(
    rf"(?<![\w$])(?:with[ \t]*\({WS}dependencies{WS}\)|dependencies(?:{WS}\.{WS}constraints)?(?:{WS}\.{WS}(?:apply|run|also|with))?){WS}\{{"
)
# A configuration called on the handler outside a block: `dependencies.implementation(x)`, Groovy `dependencies.implementation x`.
DEPS_CALL = re.compile(
    rf"""(?<![\w$])dependencies{WS}\.{WS}(?:constraints{WS}\.{WS})?(?!(?:apply|run|also|with)\b)[A-Za-z_]\w*(?=[ \t]*\(|[ \t]+[\w"'\[])"""
)
# A statement in a dependencies block that is a call: `implementation(x)`, `"implementation"(x)`, Groovy `implementation x`.
STATEMENT = re.compile(r"""(?:^|[{;])[ \t]*("[ \t]*"|'[ \t]*'|[A-Za-z_]\w*)(?=[ \t]*\(|[ \t]+[\w"'\[])""", re.M)
KEYWORDS = {"if", "else", "for", "while", "when", "return", "val", "var", "def", "try", "catch", "throw", "fun", "import", "in", "is", "as"}
# Group notation with a literal group, or a literal version, as a named argument, a Groovy map entry or a Kotlin `mapOf` entry.
NAMED = re.compile(
    rf"""(?<![\w$])(?:group[ \t]*[:=]{WS}["'](?=[A-Za-z0-9_.-])|(version)[ \t]*[:=]{WS}["'])"""
    rf"""|(["'])(?:group\2{WS}to{WS}["'](?=[A-Za-z0-9_.-])|(version)\2{WS}to{WS}["'])"""
)
MAPS = {"mapOf", "mutableMapOf", "hashMapOf", "linkedMapOf"}
FORCED = re.compile(r"(?<![\w$])(?:forcedModules[ \t]*=[ \t]*|setForcedModules[ \t]*)")  # resolutionStrategy.forcedModules = setOf("g:a:1")
RICH = re.compile(r"(?<![\w$])(?:strictly|require|prefer)(?:[ \t]*\([ \t\r\n]*|[ \t]+)[\"']")  # `version { strictly("1.0") }`
POSITIONAL = re.compile(r"""(?<![\w$])([A-Za-z_]\w*)[ \t]*\([ \t\r\n]*(["'])(?=[A-Za-z0-9_.-]+\2[ \t\r\n]*,[ \t\r\n]*["'])""")
NOT_DECLARATIONS = {"exclude", "add", "because", "listOf", "setOf", "arrayOf"}
OPEN = r"(?:[ \t]*\([ \t\r\n]*|[ \t]+)"
ADD = re.compile(r"(?<![\w$])add" + OPEN + r"""(["'])[^"'\n]*\1[ \t\r\n]*,[ \t\r\n]*["'](?=""" + COORD.pattern + ")")
ANYWHERE = re.compile(r"(?<![\w$])(?:force|useModule|useTarget|platform|enforcedPlatform|module|create)" + OPEN + r"""["'](?=""" + COORD.pattern + ")")
PLUGIN_VERSION = re.compile(r"""[)"'`](?:[ \t]+version[ \t]*\(?|[ \t\r\n]*\.[ \t\r\n]*version[ \t]*\()[ \t]*["']""")
USE_VERSION = re.compile(r"(?<![\w$])useVersion" + OPEN + r"""["']""")
CATALOG_IN_CODE = re.compile(r"(?<![\w$])versionCatalogs\b")


def blocks(blank):
    """The (start, end) offsets of every `dependencies { }` block body in text with comments and string contents blanked."""
    found = []
    for m in DEPS_BLOCK.finditer(blank):
        depth, i = 1, m.end()
        while i < len(blank) and depth:
            depth += {"{": 1, "}": -1}.get(blank[i], 0)
            i += 1
        found.append((m.end(), i))
    return found


def within(spans, i):
    return any(a <= i < b for a, b in spans)


def enclosing_call(blank, pos):
    """(name, offset) of the call whose argument list holds pos: the identifier before the first unmatched `(`, or for a Groovy call
    without parentheses the first identifier of its statement (after the line start, `{` or `;`)."""
    depth, i, stop = 0, pos, 0
    while i > 0:
        i -= 1
        c = blank[i]
        if c in ")]":
            depth += 1
        elif c in "([":
            if depth:
                depth -= 1
            elif c == "(":
                m = re.search(r"([A-Za-z_]\w*)[ \t]*$", blank[:i])
                return (m.group(1), m.start(1)) if m else ("", i)
        elif c in "{;" and not depth:
            stop = i + 1
            break
    start = max(stop, blank.rfind("\n", 0, pos) + 1)
    # `details.useTarget group: ...`, also after a closure parameter list on the same line (`{ details -> ...`)
    m = re.compile(r"[ \t]*(?:[\w \t,]*->)?[ \t]*(?:[A-Za-z_]\w*[ \t]*\.[ \t]*)*([A-Za-z_]\w*)").match(blank, start)
    return (m.group(1), m.start(1)) if m else ("", pos)


def statement_end(blank, i):
    """The offset where the expression starting at i ends: a line end or `;` outside brackets, or a closing bracket it did not open."""
    depth = 0
    while i < len(blank):
        c = blank[i]
        if c in "([{":
            depth += 1
        elif c in ")]}":
            if not depth:
                return i
            depth -= 1
        elif c in "\n;" and not depth:
            return i
        i += 1
    return i


def scan_catalog(root):
    """(problems, number of Gradle files, number of dependency declarations in dependencies blocks)."""
    files = gradle_files(root)
    problems, declarations = [], 0
    for p in files:
        raw, starts = read(root, p), []
        code = strip(raw, strings=starts)
        blank = strip(raw, blank_strings=True)
        comments = "".join(" " if r == c and r != "\n" else r for r, c in zip(raw, code, strict=True)).split("\n")
        spans = blocks(blank) + [(m.end(), statement_end(blank, m.end())) for m in DEPS_CALL.finditer(blank)]  # R2-01: its arguments too
        inside = partial(within, spans)
        hits = {}  # offset -> what was found, so one literal found by two patterns is reported once
        for s in starts:
            m = COORD.match(code, s)
            if m and inside(s):
                hits.setdefault(s, f'dependency "{m.group()}"')
        for m in STATEMENT.finditer(blank):
            if inside(m.start(1)) and m.group(1) not in KEYWORDS:
                declarations += 1
        for m in DEPS_CALL.finditer(blank):
            declarations += 1
            lit = re.compile(OPEN + r"""["'](?=""" + COORD.pattern + ")").match(code, m.end())
            if lit:
                hits.setdefault(lit.end(), f'dependency "{COORD.match(code, lit.end()).group()}"')
        for m in FORCED.finditer(blank):
            for s in starts:
                if m.end() <= s < statement_end(blank, m.end()) and COORD.match(code, s):
                    hits.setdefault(s, f'forced module "{COORD.match(code, s).group()}"')
        for m in NAMED.finditer(code):  # reported once per call, at its name; a map is read as the argument of the call around it
            name, at = enclosing_call(blank, m.start())
            while name in MAPS:
                name, at = enclosing_call(blank, at)
            if (inside(m.start()) and name not in NOT_DECLARATIONS) or name == "useTarget":
                what = "literal version (plugin or catalog entry)" if m.group(1) or m.group(3) else "dependency in group notation"
                hits.setdefault(at, what)
        for m in RICH.finditer(blank):
            if inside(m.start()):
                hits.setdefault(m.end(), "literal version (plugin or catalog entry)")
        for m in POSITIONAL.finditer(code):
            if inside(m.end()) and m.group(1) not in NOT_DECLARATIONS:  # the end: a DEPS_CALL span starts after the name
                hits.setdefault(m.end(), "dependency given as separate group, name and version literals")
        for rx in (ADD, ANYWHERE):
            for m in rx.finditer(code):
                hits.setdefault(m.end(), f'dependency "{COORD.match(code, m.end()).group()}"')
        for rx in (PLUGIN_VERSION, USE_VERSION):
            for m in rx.finditer(blank):
                hits.setdefault(m.end(), "literal version (plugin or catalog entry)")
        for m in CATALOG_IN_CODE.finditer(blank):
            hits.setdefault(m.start(), "version catalog declared in Gradle code (versionCatalogs)")
        for offset, what in sorted(hits.items()):
            line = line_of(raw, offset)
            if not justified(comments[line - 1]):
                problems.append(
                    f"{p}:{line}: {what} bypasses the version catalog; declare it in gradle/libs.versions.toml and use libs.<name>, "
                    "or say why in `// justified: <reason>` on this line"
                )
    return problems, len(files), declarations


def catalog_stats(root):
    _problems, files, declarations = scan_catalog(root)
    return files, declarations


def catalog_problems(root):
    problems, files, declarations = scan_catalog(root)
    if not files:
        problems.append("no Gradle build files found (the catalog check would pass vacuously)")
    elif not declarations and not problems:
        problems.append("no dependency declaration found in a dependencies block of any Gradle file (the catalog check would pass vacuously)")
    return problems


# -- 4. convention plugins (M1-46) -------------------------------------------------------------------------------------------------------

# Reaching other projects (M1-68 part B3): any use of the project sets (Kotlin property or Groovy getter), member access on (also after
# `?` or `!!`) or a configure block or Action/lambda argument for another project, evaluationDependsOn, and the Gradle-level hooks.
# String contents are blanked, so `project("...")` is matched with its parentheses (one level of nesting, as in `project(mapOf(...))`).
CROSS_PROJECT = re.compile(
    r"(?<![\w$])(?:get)?(?:[aA]llprojects|[sS]ubprojects|[cC]hildProjects)(?![\w$])"
    r"|(?<![\w$])`?(?:project|findProject)`?\s*\((?:[^()]|\([^()]*\))*\)\s*(?:\?|!!)?\s*[.{]"
    # PR 359 R1-01: project(path, Action { }) and project(path, { }).
    r"|(?<![\w$])`?project`?\s*\([^(){}]*,\s*(?:Action\b|\{)"
    # PR 384 R1-01: a callable reference (Kotlin `::project`, Groovy `.&project`).
    r"|(?:::|\.\s*&)\s*`?(?:project|findProject)`?(?![\w$])"
    # PR 384 R2-02: a Groovy slashy method name (`owner./project/(...)`, `$/project/$`) and a dynamic call by name.
    r"|\.\s*&?\s*\$?/(?:project|findProject)/"
    r"|(?<![\w$])invokeMethod\b"
    r"|(?<![\w$])evaluationDependsOn(?:Children)?\b"
    r"|(?<![\w$])gradle\s*\.\s*(?:lifecycle\s*\.\s*)?(?:allprojects|beforeProject|afterProject|projectsLoaded|projectsEvaluated)\b"
)
# What the convention plugins own; a module build file that sets one again makes a second copy that can drift. Since M1-68 part B
# that includes the JUnit Platform, failOnNoDiscoveredTests (checkTestSettings checks the result per module) and :core:testing.
OWNED = re.compile(
    r"(?<![\w$])(allWarningsAsErrors|jvmTarget|sourceCompatibility|targetCompatibility|jvmToolchain|compileSdk|minSdk"
    r"|useJUnitPlatform|failOnNoDiscoveredTests)\b|(-Xjdk-release)"
    r"|(?<![\w$])testImplementation\s*\(\s*project\s*\(\s*(?:path\s*=\s*)?\":core:testing\""
)
# The four module conventions; listicles.dependency.floors is not one (it carries none of the module settings; R1-03).
MODULE_CONVENTION = r"listicles\.(?:jvm\.(?:library|testsupport)|android\.(?:library|application))"
CONVENTION = re.compile(rf"\balias\s*\(\s*libs\.plugins\.{MODULE_CONVENTION}\s*\)|\bid\s*\(\s*\"{MODULE_CONVENTION}\"\s*\)")
INCLUDE_CALL = re.compile(r"\binclude\s*\(([^)]*)\)")


def module_paths(root):
    """The project paths in settings.gradle.kts `include(...)` calls, or None when there is no settings file."""
    if not os.path.isfile(os.path.join(root, "settings.gradle.kts")):
        return None
    text = strip(read(root, "settings.gradle.kts"))
    return [p for m in INCLUDE_CALL.finditer(text) for p in re.findall(r"\"(:[^\"]+)\"", m.group(1))]


# M1-84, isolated projects: the root project is read only through `isolated.rootProject` (an IsolatedProject: its directory, name and
# path). In a settings file `rootProject` is the ProjectDescriptor: there only `rootProject.name`, `.buildFileName` and `.projectDir`
# (also on `settings.`) pass.
ROOT_PROJECT = re.compile(r"(?<![\w$])(?:rootProject|getRootProject\s*\(\s*\))(?![\w$])")
ISOLATED_BEFORE = re.compile(r"(?<![\w$])(?:isolated|getIsolated\s*\(\s*\))\s*(?:\?|!!)?\s*\.\s*$")
DESCRIPTOR = re.compile(r"\s*\.\s*(?:name|buildFileName|projectDir)(?![\w$])")
SETTINGS_RECEIVER = re.compile(r"(?:^|[^\w$.\s])\s*(?:settings\s*\.\s*)?$")
# The parent project: with the implicit receiver (`parent`, `getParent()`) or on `project`, `target`, `this` or `getProject()`. A
# `.parent` on any other receiver is not read: File.parent and Path.parent have the same name (a known gap).
PARENT = re.compile(
    r"(?<![\w$.])(?:parent|getParent\s*\(\s*\))(?![\w$])"
    # PR 384 R1-02: also with the receiver in parentheses, `(project).parent`.
    # PR 384 R2-03: backticked, in any parentheses, after `!!` or a cast: `((project)).parent`, `(project as Project).parent`.
    r"|(?<![\w$])(?:\(\s*)*(?:`?(?:project|target|this)`?|`?getProject`?\s*\(\s*\))(?:\s*!!|\s+as\??\s+[\w.]+\??)*(?:\s*\))*"
    r"\s*(?:\?|!!)?\s*\.\s*(?:parent|getParent\s*\(\s*\))(?![\w$])"
)
# project(...)/findProject(...) on any receiver but `dependencies.` (DependencyHandler.project, a dependency). It passes only as a direct
# argument of a dependency declaration (an allowlist): a call that is a whole statement in a `dependencies { }` block (`conf(...)`,
# `"conf"(...)`, `add("conf", ...)`, Groovy `conf project(...)`, optionally with a configuration block) or `dependencies.<conf>(...)`,
# with only testFixtures, platform or enforcedPlatform between it and project(...).
PROJECT_CALL = re.compile(r"(?<![\w$])`?(?:project|findProject)`?\s*\(")  # also backticked (PR 384 R1-01)
# A Groovy method name in a string, `owner.'project'(':x')`, `owner."""project"""(...)`, `.&'project'`, or one built by a GString
# (`owner."${n}"(...)`): the name is a string, so it is read from the raw text (PR 384 R1-01, R2-02).
PROJECT_NAMES = {"project", "findProject"}
MEMBER_BEFORE = re.compile(r"\.\s*&?\s*$")
# A call after the name: `(` or, in Groovy command syntax, an argument (not `in`, `instanceof` or `as`; PR 384 R2-01).
CALL_AFTER = re.compile(r"""\s*\(|[ \t]+(?!(?:in|instanceof|as)\b)['"\w$/\[]""")
GROOVY_COMMAND = re.compile(r"""(?<![\w$])`?(?:project|findProject)`?[ \t]+(?!(?:in|instanceof|as)\b)(?=['"\w$/\[])""")


def literals(raw, starts):
    """(quote offset, end offset, contents) of each string literal whose contents start at an offset in starts (see strip)."""
    for s in starts:
        delim = raw[s - 3 : s] if raw[s - 3 : s] in ('"""', "'''") else raw[s - 1 : s]
        i, depth = s, 0
        while i < len(raw) and not (depth == 0 and raw.startswith(delim, i)):
            if len(delim) == 1 and raw[i] == "\\":
                i += 1
            elif delim[0] == '"' and raw.startswith("${", i):
                depth += 1
                i += 1
            elif depth and raw[i] == "}":
                depth -= 1
            elif len(delim) == 1 and raw[i] == "\n":
                break
            i += 1
        yield s - len(delim), min(len(raw), i + len(delim)), raw[s:i]


def string_names(raw, text, starts):
    """Offsets of string literals used as a project/findProject method name, or as a GString method name. raw gives the contents,
    text (comments and string contents blanked, same offsets) what is around them."""
    found = []
    for q, e, contents in literals(raw, starts):
        member = MEMBER_BEFORE.search(text[max(0, q - WINDOW) : q])
        if (member and "$" in contents) or (contents in PROJECT_NAMES and (member or CALL_AFTER.match(text, e))):
            found.append(q)
    return found
DEPENDENCIES_BEFORE = re.compile(r"(?<![\w$])dependencies\s*\.\s*(?:constraints\s*\.\s*)?$")
WRAPPERS = {"testFixtures", "platform", "enforcedPlatform"}
NOT_DEPENDENCY_CALLS = KEYWORDS | {"with", "run", "apply", "also", "let", "configure", "project", "findProject"}
STATEMENT_START = re.compile(r"(?:^|[\n;{])[ \t]*$")
STATEMENT_END = re.compile(r"[ \t]*(?:$|[\n;}]|\{)")
WINDOW = 400  # how far back a receiver is looked for


def is_settings(p):
    name = p.rsplit("/", 1)[-1]
    return name in ("settings.gradle.kts", "settings.gradle") or name.endswith((".settings.gradle.kts", ".settings.gradle"))


def opener(blank, pos):
    """The offset of the innermost bracket that is open at pos, or -1."""
    depth = 0
    for i in range(pos - 1, -1, -1):
        c = blank[i]
        if c in ")]}":
            depth += 1
        elif c in "([{":
            if not depth:
                return i
            depth -= 1
    return -1


def closer(blank, i):
    """The offset just after the bracket that closes the one at i."""
    depth = 0
    for j in range(i, len(blank)):
        depth += {"(": 1, "[": 1, "{": 1, ")": -1, "]": -1, "}": -1}.get(blank[j], 0)
        if not depth:
            return j + 1
    return len(blank)


def declaration(blank, start, end, deps, name):
    """True when the call from start to end is a whole dependency declaration statement (see PROJECT_CALL)."""
    if name in NOT_DEPENDENCY_CALLS or not STATEMENT_END.match(blank, end):
        return False
    head = blank[max(0, start - WINDOW) : start]
    return bool(DEPENDENCIES_BEFORE.search(head) or (within(deps, start) and STATEMENT_START.search(head)))


def dependency_argument(blank, pos, deps, wrapped=0):
    """True when the project(...) call at pos is a direct argument of a dependency declaration (see PROJECT_CALL)."""
    o = opener(blank, pos)
    before = blank[max(0, pos - WINDOW) : pos]
    if o >= 0 and blank[o] == "(":
        if not re.search(r"[(,]\s*$|[(,]\s*[A-Za-z_]\w*\s*=\s*$", before):
            return False
        m = re.search(r"(?:([A-Za-z_]\w*)|\"[ \t]*\")[ \t]*$", blank[max(0, o - WINDOW) : o])
        if not m:
            return False
        name, start = m.group(1) or "", o - (len(blank[max(0, o - WINDOW) : o]) - m.start())
        if name in WRAPPERS:
            return wrapped < 2 and dependency_argument(blank, start, deps, wrapped + 1)
        return declaration(blank, start, closer(blank, o), deps, name)
    # Groovy without parentheses: `conf project(':x')` at the start of a statement.
    m = re.search(r"(?:^|(?<=[\n;{]))[ \t]*([A-Za-z_]\w*)[ \t]+$", before)
    if not m or wrapped:
        return False
    start = pos - (len(before) - m.start(1))
    return declaration(blank, start, closer(blank, blank.index("(", pos)), deps, m.group(1))


def cross_project(text, settings, quoted=(), groovy=False):
    """(line, what, hint) for each line of text (comments and string contents blanked) that reaches other projects, first finding only."""
    found = []
    for m in CROSS_PROJECT.finditer(text):
        found.append((m.start(), m.group().strip(), "move it into a convention plugin in build-logic/"))
    for m in ROOT_PROJECT.finditer(text):
        before = text[max(0, m.start() - WINDOW) : m.start()]
        if (not (DESCRIPTOR.match(text, m.end()) and SETTINGS_RECEIVER.search(before)) if settings else not ISOLATED_BEFORE.search(before)):
            found.append((m.start(), "rootProject", "read root files through isolated.rootProject.projectDirectory"))
    for m in PARENT.finditer(text):
        found.append((m.start(), "parent", "a project reads only its own and isolated.rootProject's state"))
    deps = blocks(text)
    for m in PROJECT_CALL.finditer(text):
        if not DEPENDENCIES_BEFORE.search(text[max(0, m.start() - WINDOW) : m.start()]) and not dependency_argument(text, m.start(), deps):
            call = "findProject" if "findProject" in m.group() else "project"
            found.append((m.start(), f"{call}(...)", "use project(...) only as a dependency, e.g. implementation(project(...))"))
    found += [(q, "project(...)", "call project(...) by its name, only as a dependency") for q in quoted]
    if groovy:
        found += [(m.start(), "project(...)", "call project(...) with parentheses, only as a dependency") for m in GROOVY_COMMAND.finditer(text)]
    lines = {}
    for start, what, hint in sorted(found):
        lines.setdefault(line_of(text, start), (what, hint))
    return [(line, what, hint) for line, (what, hint) in sorted(lines.items())]


def convention_problems(root):
    problems = []
    for p in gradle_files(root) + [p for p in walk(root) if p.startswith("build-logic/") and p.endswith(".kt")]:
        raw, starts = read(root, p), []
        text = strip(raw, blank_strings=True, templates=True, strings=starts)
        found = cross_project(text, is_settings(p), string_names(raw, text, starts), p.endswith(".gradle"))
        problems += [f"{p}:{line}: reaches other projects ({what}); {hint}" for line, what, hint in found]
        if p.endswith(".kt"):
            for m in TARGET_TOKEN.finditer(text):
                problems.append(f"{p}:{line_of(text, m.start())}: {m.group()} in build-logic; set it in the module build file, where the floor guard reads it")
    modules = module_paths(root)
    if modules is None:
        return problems
    if not modules:
        problems.append("settings.gradle.kts includes no module (the convention plugin check would pass vacuously)")
    for module in modules:
        base = module.strip(":").replace(":", "/")
        build = next((f"{base}/build.gradle{ext}" for ext in (".kts", "") if os.path.isfile(os.path.join(root, *base.split("/"), "build.gradle" + ext))), None)
        if build is None:
            problems.append(f"{module}: no build file at {base}/build.gradle.kts")
            continue
        text = strip(read(root, build))
        applied = CONVENTION.findall(text)
        if len(applied) != 1:
            problems.append(f"{build}: applies {len(applied)} listicles convention plugins; apply exactly one (build-logic/)")
        for m in OWNED.finditer(text):
            problems.append(f"{build}:{line_of(text, m.start())}: {m.group()} is set by the convention plugins in build-logic/; do not set it again here")
    return problems


ROOT_MODULES = re.compile(r"(?m)^val listiclesModules = listOf\(([^)]*)\)")
ROOT_WIRING = re.compile(r'(?m)^tasks\.named\("detekt"\)\s*\{\s*dependsOn\(listiclesModules\.map\s*\{\s*"\$it:listiclesChecks"\s*\}\)\s*\}')


def aggregation_problems(root):
    modules = module_paths(root)
    if modules is None:
        return []
    text = strip(read(root, "build.gradle.kts")) if os.path.isfile(os.path.join(root, "build.gradle.kts")) else ""
    lists = ROOT_MODULES.findall(text)
    if len(lists) != 1:
        return ["build.gradle.kts: no `val listiclesModules = listOf(...)` (the root runs every module's listiclesChecks by task path)"]
    listed = re.findall(r"\"(:[^\"]+)\"", lists[0])
    problems = [f"build.gradle.kts: listiclesModules misses {m} (settings.gradle.kts includes it)" for m in modules if m not in listed]
    problems += [f"build.gradle.kts: listiclesModules lists {m}, which settings.gradle.kts does not include" for m in dict.fromkeys(listed) if m not in modules]
    problems += [f"build.gradle.kts: listiclesModules lists {m} twice" for m in dict.fromkeys(listed) if listed.count(m) > 1]
    if not ROOT_WIRING.search(text):
        problems.append('build.gradle.kts: detekt does not depend on dependsOn(listiclesModules.map { "$it:listiclesChecks" })')
    return problems


def main(argv):
    root = os.path.abspath(argv[1]) if len(argv) > 1 else os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
    problems = catalog_problems(root) + target_sdk_problems(root) + manifest_problems(root) + convention_problems(root) + aggregation_problems(root)
    if problems:
        for p in problems:
            print(f"build-guards: {p}")
        return 1
    sdk = min(v for _p, _l, v in target_sdk_values(root))
    manifests = len(application_manifests(root))
    files, declarations = catalog_stats(root)
    modules = len(module_paths(root) or [])
    print(
        f"build-guards: ok ({files} Gradle file{'s' * (files != 1)}, {declarations} dependency declarations, targetSdk {sdk}, "
        f"floor {TARGET_SDK_FLOOR}, {manifests} manifest, {modules} modules on convention plugins)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
