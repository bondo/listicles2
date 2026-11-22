#!/usr/bin/env python3
"""Checks JVM-module class files against the Android SDK's api-versions.xml for minSdk (M1-37, issue 228).

Usage: python3 -I scripts/check_java_api_level.py --api-versions FILE --min-sdk N PATH...   (PATH: a class directory or a .class file)

Android lint's NewApi skips pure JVM modules such as :core:domain, and no core library desugaring is configured, so a Java 9 to 17
member that is newer than minSdk (Stream.toList is API 34, Objects.requireNonNullElse is API 30) compiles and then crashes on old devices.
This reads every field and method reference in the class files and looks it up in api-versions.xml, following the superclass and interface
chain (also through the scanned project classes). A reference to a java/ or android/ class or member that the file does not list, lists with
a `since` above minSdk, or lists with `removed` (a later Android dropped it: Thread.suspend, removed in API 36) is a violation.
invokedynamic bootstrap methods (lambdas, string concatenation) are desugared by D8 and not checked.
It also walks the bytecode and looks up every class that is only named, with no member reference (M1-56): a class literal (`X.class`,
an ldc), a new, anewarray, multianewarray, checkcast or instanceof operand (an array type counts as its element type), a catch type, and
an annotation type, an enum type, a class value or a nested annotation in the (class, field, method, parameter) annotations and the
annotation defaults. The constant pool Class entries that only the InnerClasses attribute or a bootstrap method owner name are not used
by the code and are not looked up.
Known gaps: a type that is only named in a field or method descriptor, a Signature, a throws clause, a stack map frame or a type annotation
is not looked up; a project class whose parent is a third-party class that is not scanned is not resolved further.

Exit: 0 clean, 1 violations, 2 the check could not run (missing, empty or unreadable api file, no class files, a corrupt class file, bad usage).
Whole-number arithmetic only: a level is the tuple (major, minor) of integers, so `37.0` and `26.1` are above 26.
"""

import argparse
import os
import re
import struct
import sys
import xml.etree.ElementTree as ET

CHECKED_PREFIXES = ("java/", "android/")
ANCHOR_CLASSES = ("java/lang/Object", "java/util/List")  # a file without these is not a platform api-versions.xml
LEVEL = re.compile(r"(\d+)(?:\.(\d+))?")
ONE = (1, 0)
NEVER = (10**9, 0)  # the `removed` level of an entry that Android never removed
MEMBER_ERROR, CLASS_ERROR = "NoSuchMethodError or NoSuchFieldError", "NoClassDefFoundError"
ANNOTATION_ATTRS = ("RuntimeVisibleAnnotations", "RuntimeInvisibleAnnotations")
PARAMETER_ANNOTATION_ATTRS = ("RuntimeVisibleParameterAnnotations", "RuntimeInvisibleParameterAnnotations")
# Operand bytes after each JVM opcode that has any; tableswitch, lookupswitch and wide are handled in walk_code.
OPERANDS = {0x10: 1, 0x11: 2, 0x12: 1, 0x13: 2, 0x14: 2, 0x84: 2, 0xA9: 1, 0xB9: 4, 0xBA: 4, 0xBC: 1, 0xC5: 3, 0xC8: 4, 0xC9: 4}
OPERANDS.update({op: 1 for op in (*range(0x15, 0x1A), *range(0x36, 0x3B))})  # loads and stores with an index
OPERANDS.update({op: 2 for op in (*range(0x99, 0xA9), *range(0xB2, 0xB9), 0xBB, 0xBD, 0xC0, 0xC1, 0xC6, 0xC7)})  # branches, fields, invokes, new...
NO_OPERANDS = {*range(0x00, 0x10), *range(0x1A, 0x36), *range(0x3B, 0x84), *range(0x85, 0x99), *range(0xAC, 0xB2), 0xBE, 0xBF, 0xC2, 0xC3}
CLASS_OPCODES = {0xBB, 0xBD, 0xC0, 0xC1, 0xC5}  # new, anewarray, checkcast, instanceof, multianewarray: a 2-byte Class index
LDC_OPCODES = {0x12: ">B", 0x13: ">H"}  # ldc, ldc_w: the entry is a class literal when it is a Class entry


class CheckError(Exception):
    """The check cannot give an answer: the caller must fail, not pass."""


def level(text, where):
    m = LEVEL.fullmatch(text.strip()) if text else None
    if not m:
        raise CheckError(f"{where}: unreadable since=\"{text}\"")
    return (int(m.group(1)), int(m.group(2) or 0))


class Api:
    """classes[name] = (since, removed, {member key: (since, removed)}, [(parent, since, removed)]); a member key is "M:name(desc)ret" or "F:name"."""

    def __init__(self, path):
        self.classes = {}
        try:
            with open(path, "rb") as f:
                for _, el in ET.iterparse(f):
                    if el.tag == "class":
                        self.add(el)
                        el.clear()
        except OSError as e:
            raise CheckError(f"cannot read api-versions.xml {path}: {e.strerror}") from e
        except ET.ParseError as e:
            raise CheckError(f"{path} is not well-formed XML (truncated?): {e}") from e
        missing = [c for c in ANCHOR_CLASSES if c not in self.classes]
        if missing:
            raise CheckError(f"{path} is not a platform api-versions.xml: it lists no {', '.join(missing)}")

    @staticmethod
    def span(el, where):
        """(since, removed) of an entry; `removed` is the first API level that no longer has it."""
        removed = level(el.get("removed"), where + " removed") if el.get("removed") is not None else NEVER
        return level(el.get("since", "1"), where), removed

    def add(self, el):
        name = el.get("name", "")
        since, removed = self.span(el, name)
        members, parents = {}, []
        for child in el:
            span = self.span(child, f"{name} {child.get('name')}")
            if child.tag == "method":
                members["M:" + child.get("name", "")] = span
            elif child.tag == "field":
                members["F:" + child.get("name", "")] = span
            elif child.tag in ("extends", "implements"):
                parents.append((child.get("name", ""), *span))
        self.classes[name] = (since, removed, members, parents)


class Reader:
    def __init__(self, data):
        self.data, self.pos = data, 0

    def take(self, fmt):
        size = struct.calcsize(fmt)
        if self.pos + size > len(self.data):
            raise CheckError("class file is truncated")
        (v,) = struct.unpack_from(fmt, self.data, self.pos)
        self.pos += size
        return v

    def advance(self, n):
        if self.pos + n > len(self.data):
            raise CheckError("class file is truncated")
        self.pos += n

    def raw(self, n):
        self.advance(n)
        return self.data[self.pos - n : self.pos]


def descriptor_class(desc):
    """The class a field descriptor names, looking through array types; None for a primitive."""
    desc = desc.lstrip("[")
    return desc[1:-1] if desc.startswith("L") and desc.endswith(";") else None


def entry_class(name):
    """The class a constant pool Class entry names: an array type counts as its element type."""
    return descriptor_class(name) if name.startswith("[") else name


def walk_code(code):
    """Yield (opcode, constant pool index) for each instruction that names a class or loads a constant; fail on an unreadable instruction."""
    r = Reader(code)
    while r.pos < len(code):
        op = r.take(">B")
        if op in CLASS_OPCODES:
            yield op, r.take(">H")
            r.advance(OPERANDS[op] - 2)  # multianewarray: the dimensions
        elif op in LDC_OPCODES:
            yield op, r.take(LDC_OPCODES[op])
        elif op in (0xAA, 0xAB):  # tableswitch, lookupswitch: padded to a multiple of 4 from the start of the code
            r.advance(-r.pos % 4)
            r.advance(4)  # default
            if op == 0xAA:
                low, high = r.take(">i"), r.take(">i")
                size = 4 * (high - low + 1)
            else:
                size = 8 * r.take(">i")
            if size < 0:
                raise CheckError("class file has a switch with a negative size")
            r.advance(size)
        elif op == 0xC4:  # wide: iinc takes two 2-byte operands, the loads, stores and ret one
            op2 = r.take(">B")
            if op2 in (0x84, *range(0x15, 0x1A), *range(0x36, 0x3B), 0xA9):
                r.advance(4 if op2 == 0x84 else 2)
            else:
                raise CheckError(f"class file has an unreadable wide instruction (opcode {op2:#x})")
        elif op in OPERANDS or op in NO_OPERANDS:
            r.advance(OPERANDS.get(op, 0))
        else:
            raise CheckError(f"class file has an unknown opcode {op:#x}")


def read_annotation(r, utf8, found):
    found.add(descriptor_class(utf8(r.take(">H"))))
    for _ in range(r.take(">H")):
        r.advance(2)  # element name
        read_element_value(r, utf8, found)


def read_element_value(r, utf8, found):
    tag = chr(r.take(">B"))
    if tag in "BCDFIJSZs":
        r.advance(2)
    elif tag == "e":  # enum constant: the type is a descriptor
        found.add(descriptor_class(utf8(r.take(">H"))))
        r.advance(2)
    elif tag == "c":  # class value: a return descriptor
        found.add(descriptor_class(utf8(r.take(">H"))))
    elif tag == "@":
        read_annotation(r, utf8, found)
    elif tag == "[":
        for _ in range(r.take(">H")):
            read_element_value(r, utf8, found)
    else:
        raise CheckError(f"class file has an unknown annotation value tag {tag!r}")


def scan_attributes(r, pool, found, excluded):
    """Read an attribute table. Adds the classes that code and annotations name to `found` and the bootstrap Methodref indexes to `excluded`."""

    def utf8(idx):
        return pool[idx][1]

    def class_entry(idx):
        if pool[idx][0] != 7:
            raise CheckError("class file is corrupt (an instruction names a constant that is not a class)")
        return entry_class(utf8(pool[idx][1]))

    for _ in range(r.take(">H")):
        attr = utf8(r.take(">H"))
        body = Reader(r.raw(r.take(">I")))
        if attr == "BootstrapMethods":
            for _ in range(body.take(">H")):
                excluded.add(pool[body.take(">H")][2])
                body.advance(2 * body.take(">H"))
        elif attr in ANNOTATION_ATTRS:
            for _ in range(body.take(">H")):
                read_annotation(body, utf8, found)
        elif attr in PARAMETER_ANNOTATION_ATTRS:
            for _ in range(body.take(">B")):
                for _ in range(body.take(">H")):
                    read_annotation(body, utf8, found)
        elif attr == "AnnotationDefault":
            read_element_value(body, utf8, found)
        elif attr == "Code":
            body.advance(4)  # max_stack, max_locals
            for op, idx in walk_code(body.raw(body.take(">I"))):
                if op in CLASS_OPCODES or pool[idx][0] == 7:  # an ldc names a class literal when its entry is a Class entry
                    found.add(class_entry(idx))
            for _ in range(body.take(">H")):  # exception table: a catch type of 0 is a finally
                body.advance(6)
                catch_type = body.take(">H")
                if catch_type:
                    found.add(class_entry(catch_type))


def parse_class(data):
    """(name, super, interfaces, declared member keys, refs, named classes); a ref is (owner, member key, display)."""
    r = Reader(data)
    if r.take(">I") != 0xCAFEBABE:
        raise CheckError("not a class file (bad magic)")
    r.advance(4)  # minor, major
    count = r.take(">H")
    pool, i = {}, 1
    while i < count:
        tag = r.take(">B")
        if tag == 1:
            pool[i] = (1, r.raw(r.take(">H")).decode("utf-8", errors="replace"))
        elif tag in (3, 4):
            r.advance(4)
            pool[i] = (tag,)
        elif tag in (5, 6):
            r.advance(8)
            pool[i] = (tag,)
            i += 1  # long and double take two slots
        elif tag in (7, 8, 16, 19, 20):
            pool[i] = (tag, r.take(">H"))
        elif tag in (9, 10, 11, 12, 17, 18):
            pool[i] = (tag, r.take(">H"), r.take(">H"))
        elif tag == 15:
            pool[i] = (15, r.take(">B"), r.take(">H"))
        else:
            raise CheckError(f"class file has an unknown constant pool tag {tag}")
        i += 1

    def utf8(idx):
        return pool[idx][1]

    def class_name(idx):
        return utf8(pool[idx][1]) if idx else None

    try:
        r.advance(2)  # access flags
        name = class_name(r.take(">H"))
        sup = class_name(r.take(">H"))
        interfaces = [class_name(r.take(">H")) for _ in range(r.take(">H"))]
        declared = set()
        named = set()  # classes that code (class literals, casts, catch types...) and annotations name
        excluded = set()  # Methodref entries that only name a bootstrap method of an invokedynamic
        for kind in ("F", "M"):
            for _ in range(r.take(">H")):
                r.advance(2)
                n, d = utf8(r.take(">H")), utf8(r.take(">H"))
                declared.add(f"F:{n}" if kind == "F" else f"M:{n}{d}")
                scan_attributes(r, pool, named, excluded)
        scan_attributes(r, pool, named, excluded)
        named.discard(None)
        refs = []
        for idx, e in pool.items():
            if e[0] in (9, 10, 11) and idx not in excluded:
                owner, nat = class_name(e[1]), pool[e[2]]
                n, d = utf8(nat[1]), utf8(nat[2])
                refs.append((owner, f"F:{n}" if e[0] == 9 else f"M:{n}{d}", f"{owner}.{n}" if e[0] == 9 else f"{owner}.{n}{d}"))
    except (KeyError, IndexError, TypeError, RecursionError) as e:
        raise CheckError(f"class file is corrupt ({type(e).__name__})") from e
    return name, sup, interfaces, declared, refs, named


class Checker:
    def __init__(self, api, min_sdk):
        self.api, self.limit = api, (min_sdk, 0)
        self.project = {}  # scanned class name -> (super, interfaces, declared member keys)

    def lookup(self, owner, key):
        """((lowest level at which `owner` has the member, level that removed it or NEVER), whether a parent was unknown).

        The first element is None when the member is on no path; a path on which nothing was removed wins over one that was."""
        found, opaque, seen = [], False, set()
        queue = [(owner, ONE, NEVER)]
        while queue:
            state = queue.pop()
            if state in seen:
                continue
            seen.add(state)
            cls, lvl, gone = state
            if cls in self.api.classes:
                since, removed, members, parents = self.api.classes[cls]
                lvl, gone = max(lvl, since), min(gone, removed)
                if key in members:
                    found.append((max(lvl, members[key][0]), min(gone, members[key][1])))
            elif cls in self.project:
                sup, interfaces, declared = self.project[cls]
                if key in declared:
                    found.append((lvl, gone))
                parents = [(p, ONE, NEVER) for p in [sup, *interfaces] if p]
            else:
                opaque = opaque or not cls.startswith(CHECKED_PREFIXES)
                continue
            queue += [(p, max(lvl, since), min(gone, removed)) for p, since, removed in parents]
        if not found and "java/lang/Object" in self.api.classes and key in self.api.classes["java/lang/Object"][2]:
            found.append(self.api.classes["java/lang/Object"][2][key])
        alive = [f for f in found if f[1] == NEVER]
        if alive:
            return min(alive), opaque
        return (min(f[0] for f in found), max(f[1] for f in found)) if found else None, opaque

    def unknown(self, cls):
        return cls.startswith(CHECKED_PREFIXES) and cls not in self.api.classes

    def problem(self, shown, lvl, gone, error=MEMBER_ERROR):
        if gone != NEVER:
            return f"{shown} was removed in API {fmt(gone)} ({error} on newer Android)"
        return f"{shown} requires API {fmt(lvl)} (minSdk {self.limit[0]})" if lvl > self.limit else None

    def check_ref(self, owner, key, shown):
        if owner.startswith("["):
            return None
        if owner in self.project or owner in self.api.classes:
            found, opaque = self.lookup(owner, key)
            if found is None:
                return None if opaque else f"{shown} is not in the Android API (api-versions.xml lists no such member)"
            return self.problem(shown, *found)
        return f"{shown} is not in the Android API (api-versions.xml lists no class {owner})" if self.unknown(owner) else None

    def check_class(self, cls):
        if cls in self.api.classes:
            return self.problem(f"class {cls}", *self.api.classes[cls][:2], error=CLASS_ERROR)
        return f"class {cls} is not in the Android API (api-versions.xml lists no such class)" if self.unknown(cls) else None

    def check_header(self, name, sup, interfaces):
        for parent in [sup, *interfaces]:
            if parent and self.unknown(parent):
                yield f"{name} extends or implements {parent}, which is not in the Android API (api-versions.xml lists no such class)"
            elif parent in self.api.classes:
                msg = self.problem(f"{name} extends or implements {parent}, which", *self.api.classes[parent][:2])
                if msg:
                    yield msg


def fmt(lvl):
    return str(lvl[0]) if lvl[1] == 0 else f"{lvl[0]}.{lvl[1]}"


def class_files(paths):
    found = []
    for p in paths:
        if os.path.isfile(p):
            found.append(p)
        elif os.path.isdir(p):
            found += [os.path.join(d, f) for d, _, fs in os.walk(p) for f in fs if f.endswith(".class")]
        else:
            raise CheckError(f"{p} does not exist")
    if not found:
        raise CheckError("no class files found under " + " ".join(paths))
    return sorted(found)


def run(api_path, min_sdk, paths):
    checker = Checker(Api(api_path), min_sdk)
    parsed = []
    for path in class_files(paths):
        try:
            with open(path, "rb") as f:
                parsed.append(parse_class(f.read()))
        except CheckError as e:
            raise CheckError(f"{path}: {e}") from e
    for name, sup, interfaces, declared, _, _ in parsed:
        checker.project[name] = (sup, interfaces, declared)
    problems = set()
    for name, sup, interfaces, _, refs, named in parsed:
        problems.update(f"{name}: {p}" for p in checker.check_header(name, sup, interfaces))
        problems.update(f"{name}: {m}" for m in map(checker.check_class, sorted(named)) if m)
        for owner, key, shown in refs:
            msg = checker.check_ref(owner, key, shown)
            if msg:
                problems.add(f"{name}: {msg}")
    return len(parsed), sorted(problems)


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--api-versions", required=True)
    ap.add_argument("--min-sdk", required=True)
    ap.add_argument("paths", nargs="+")
    try:
        args = ap.parse_args(argv)
    except SystemExit:
        return 2
    try:
        if not args.min_sdk.isdigit():
            raise CheckError(f"--min-sdk must be a whole number, not {args.min_sdk!r}")
        scanned, problems = run(args.api_versions, int(args.min_sdk), args.paths)
    except CheckError as e:
        print(f"java-api-level: cannot check: {e}")
        return 2
    for p in problems:
        print(f"java-api-level: {p}")
    if problems:
        print(f"java-api-level: {len(problems)} reference(s) above minSdk {args.min_sdk} in {scanned} class file(s)")
        return 1
    print(f"java-api-level: {scanned} class file(s) use only API {args.min_sdk} or older")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
