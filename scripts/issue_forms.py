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


def _check_body(name, body):
    if not isinstance(body, list) or not body:
        return [f"{name}: body must be a non-empty list"]
    errs, required, seen = [], False, set()
    for i, item in enumerate(body):
        if not isinstance(item, dict) or not isinstance(item.get("type"), str):
            errs.append(f"{name}: body[{i}] needs a type")
            continue
        if item["type"] not in BODY_TYPES:
            errs.append(f"{name}: body[{i}] has unknown type {item['type']!r}")
            continue
        attrs = item.get("attributes")
        if "id" in item:
            bid = item["id"]
            if not isinstance(bid, str) or not ID_RE.match(bid):
                errs.append(f"{name}: body[{i}] id must match [A-Za-z0-9_-]+")
            elif bid in seen:
                errs.append(f"{name}: body[{i}] duplicate id {bid!r}")
            else:
                seen.add(bid)
        if item["type"] == "markdown":
            if not isinstance(attrs, dict) or not str(attrs.get("value", "")).strip():
                errs.append(f"{name}: body[{i}] (markdown) needs attributes.value")
            continue
        if item["type"] in INPUT_TYPES:
            if not isinstance(attrs, dict) or not attrs.get("label"):
                errs.append(f"{name}: body[{i}] ({item['type']}) needs attributes.label")
            if isinstance(item.get("validations"), dict) and item["validations"].get("required") is True:
                required = True
    if not required:
        errs.append(f"{name}: at least one body field must have validations.required: true")
    return errs


def validate_form(name, text, allowed):
    try:
        doc = yaml.safe_load(text)
    except yaml.YAMLError as e:
        return [f"{name}: invalid YAML: {str(e).splitlines()[0]}"]
    if not isinstance(doc, dict):
        return [f"{name}: top level must be a mapping"]
    errs = []
    for key in ("name", "description"):
        if not isinstance(doc.get(key), str) or not doc[key].strip():
            errs.append(f"{name}: missing {key}")
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
