"""Validate GitHub issue forms in .github/ISSUE_TEMPLATE. Run: python3 -I scripts/issue_forms.py"""

import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("PyYAML required: apt install python3-yaml or pip install pyyaml")

# The only labels forms may apply: the five the owner created (collaborator-workflow report, D4).
ALLOWED_LABELS = {"feedback", "idea", "decision", "needs-collaborator", "needs-owner"}
INPUT_TYPES = {"textarea", "input", "dropdown", "checkboxes"}
BODY_TYPES = INPUT_TYPES | {"markdown"}
ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")
# Keys GitHub's issue-form schema accepts at the top level.
# Keys GitHub accepts on a body item.
ITEM_KEYS = {"type", "id", "attributes", "validations"}
TOP_LEVEL_KEYS = {"name", "description", "title", "labels", "assignees", "projects", "type", "body"}


def _is_text(v):
    return isinstance(v, str) and bool(v.strip())


def _check_attrs(where, item, attrs):
    """Errors for the attributes of one non-markdown field (label, value, options)."""
    errs = []
    if not isinstance(attrs, dict):
        return [f"{where} ({item['type']}) needs attributes.label"]
    if "label" not in attrs:
        errs.append(f"{where} ({item['type']}) needs attributes.label")
    elif not isinstance(attrs["label"], str):
        errs.append(f"{where} attributes.label must be a string")
    elif not attrs["label"].strip():
        errs.append(f"{where} ({item['type']}) needs attributes.label")
    if "value" in attrs and not isinstance(attrs["value"], str):
        errs.append(f"{where} attributes.value must be a string")
    if item["type"] == "dropdown":
        errs += _check_dropdown(where, attrs.get("options"))
    elif item["type"] == "checkboxes":
        errs += _check_checkboxes(where, attrs.get("options"))
    return errs


def _check_dropdown(where, options):
    if not isinstance(options, list) or not options:
        return [f"{where} (dropdown) needs a non-empty attributes.options list"]
    errs = [f"{where} dropdown option {o!r} must be a non-empty string" for o in options if not _is_text(o)]
    texts = [o.strip() for o in options if _is_text(o)]
    errs += [f"{where} duplicate option {o!r}" for o in sorted({t for t in texts if texts.count(t) > 1})]
    return errs


def _check_checkboxes(where, options):
    if not isinstance(options, list) or not options:
        return [f"{where} (checkboxes) needs a non-empty attributes.options list"]
    errs = []
    for j, o in enumerate(options):
        if not isinstance(o, dict) or not _is_text(o.get("label")):
            errs.append(f"{where} checkboxes option {j} needs a label string")
        elif "required" in o and not isinstance(o["required"], bool):
            errs.append(f"{where} checkboxes option {j} required must be a boolean")
    return errs


def _check_body(name, body):
    if not isinstance(body, list) or not body:
        return [f"{name}: body must be a non-empty list"]
    errs, required, seen, labels = [], False, set(), set()
    for i, item in enumerate(body):
        where = f"{name}: body[{i}]"
        if not isinstance(item, dict) or not isinstance(item.get("type"), str):
            errs.append(f"{where} needs a type")
            continue
        if item["type"] not in BODY_TYPES:
            errs.append(f"{where} has unknown type {item['type']!r}")
            continue
        errs += [f"{where} unknown key {k!r}" for k in item if k not in ITEM_KEYS]
        attrs = item.get("attributes")
        if "id" in item:
            bid = item["id"]
            if not isinstance(bid, str) or not ID_RE.match(bid):
                errs.append(f"{where} id must match [A-Za-z0-9_-]+")
            elif bid in seen:
                errs.append(f"{where} duplicate id {bid!r}")
            else:
                seen.add(bid)
        if item["type"] == "markdown":
            if not isinstance(attrs, dict) or not str(attrs.get("value", "")).strip():
                errs.append(f"{where} (markdown) needs attributes.value")
            elif not isinstance(attrs["value"], str):
                errs.append(f"{where} attributes.value must be a string")
            if "id" in item:
                errs.append(f"{where} (markdown) cannot have an id")
            if "validations" in item:
                errs.append(f"{where} (markdown) cannot have validations")
            continue
        errs += _check_attrs(where, item, attrs)
        label = attrs.get("label") if isinstance(attrs, dict) else None
        if _is_text(label):
            if label.strip() in labels:
                errs.append(f"{where} duplicate label {label.strip()!r}")
            labels.add(label.strip())
        vals = item.get("validations")
        if vals is not None and not isinstance(vals, dict):
            errs.append(f"{where} validations must be a mapping")
        elif isinstance(vals, dict) and "required" in vals:
            if not isinstance(vals["required"], bool):
                errs.append(f"{where} validations.required must be a boolean")
            elif vals["required"]:
                required = True
        if item["type"] == "checkboxes" and isinstance(attrs, dict) and isinstance(attrs.get("options"), list):
            required = required or any(isinstance(o, dict) and o.get("required") is True for o in attrs["options"])
    if not required:
        errs.append(f"{name}: at least one body field must be required (validations.required: true or a required checkbox option)")
    return errs


def validate_form(name, text, allowed):
    try:
        doc = yaml.safe_load(text)
    except yaml.YAMLError as e:
        return [f"{name}: invalid YAML: {str(e).splitlines()[0]}"]
    if not isinstance(doc, dict):
        return [f"{name}: top level must be a mapping"]
    errs = [f"{name}: unknown top-level key {k!r}" for k in doc if k not in TOP_LEVEL_KEYS]
    for key in ("name", "description"):
        if not isinstance(doc.get(key), str) or not doc[key].strip():
            errs.append(f"{name}: missing {key}")
    if "title" in doc and not isinstance(doc["title"], str):
        errs.append(f"{name}: title must be a string")
    labels = doc.get("labels")
    if not isinstance(labels, list) or not labels:
        errs.append(f"{name}: missing labels")
    else:
        errs += [f"{name}: unknown label {lb!r}" for lb in labels if lb not in allowed]
    return errs + _check_body(name, doc.get("body"))


def validate_dir(d, allowed=ALLOWED_LABELS):
    d = Path(d)
    errs = []
    forms = sorted(p for p in d.glob("*.yml") if p.name != "config.yml")
    if not forms:
        errs.append(f"{d}: no issue forms found")
    for p in forms:
        errs += validate_form(p.name, p.read_text(encoding="utf-8"), allowed)
    cfg = d / "config.yml"
    if cfg.exists():
        try:
            c = yaml.safe_load(cfg.read_text(encoding="utf-8"))
        except yaml.YAMLError as e:
            return errs + [f"config.yml: invalid YAML: {str(e).splitlines()[0]}"]
        if isinstance(c, dict) and c.get("blank_issues_enabled") is False:
            errs.append("config.yml: blank_issues_enabled must stay true (D3)")
    return errs


if __name__ == "__main__":
    root = Path(__file__).resolve().parent.parent / ".github" / "ISSUE_TEMPLATE"
    problems = validate_dir(root)
    print("\n".join(problems) if problems else f"issue forms ok ({root})")
    sys.exit(1 if problems else 0)
