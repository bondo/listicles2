"""Tests for scripts/issue_forms.py. Run: python3 -I scripts/test_issue_forms.py"""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import issue_forms  # noqa: E402  # justified: must follow the sys.path insert above

# Fixture list: exactly the five labels the owner created (collaborator-workflow report, D4).
LABELS = {"feedback", "idea", "decision", "needs-collaborator", "needs-owner"}
ROOT = Path(__file__).resolve().parent.parent

GOOD = """\
name: Feedback
description: Tell us what you think
labels: [feedback]
body:
  - type: textarea
    id: what
    attributes:
      label: What do you think?
    validations:
      required: true
"""


def check(text, name="form.yml"):
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / name).write_text(text)
        return issue_forms.validate_dir(Path(d), LABELS)


class IssueFormTests(unittest.TestCase):
    def test_good_form_has_no_errors(self):
        self.assertEqual(check(GOOD), [])

    def test_unknown_label_rejected(self):
        errs = check(GOOD.replace("[feedback]", "[feedback, golden-update]"))
        self.assertTrue(any("golden-update" in e for e in errs), errs)

    def test_missing_name_rejected(self):
        errs = check(GOOD.replace("name: Feedback\n", ""))
        self.assertTrue(any("name" in e for e in errs), errs)

    def test_missing_description_rejected(self):
        errs = check(GOOD.replace("description: Tell us what you think\n", ""))
        self.assertTrue(any("description" in e for e in errs), errs)

    def test_missing_labels_rejected(self):
        errs = check(GOOD.replace("labels: [feedback]\n", ""))
        self.assertTrue(any("labels" in e for e in errs), errs)

    def test_no_required_field_rejected(self):
        errs = check(GOOD.replace("required: true", "required: false"))
        self.assertTrue(any("required" in e for e in errs), errs)

    def test_missing_body_rejected(self):
        errs = check("name: X\ndescription: Y\nlabels: [idea]\n")
        self.assertTrue(any("body" in e for e in errs), errs)

    def test_body_item_without_type_rejected(self):
        errs = check(GOOD.replace("type: textarea", "kind: textarea"))
        self.assertTrue(any("type" in e for e in errs), errs)

    def test_input_without_label_rejected(self):
        errs = check(GOOD.replace("      label: What do you think?\n", "      placeholder: x\n"))
        self.assertTrue(any("label" in e for e in errs), errs)

    def test_malformed_yaml_rejected(self):
        errs = check("name: [unclosed\nbody: {")
        self.assertTrue(errs and any("YAML" in e for e in errs), errs)

    def test_non_mapping_rejected(self):
        self.assertTrue(check("- just\n- a list\n"))

    def test_no_forms_is_an_error(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertTrue(issue_forms.validate_dir(Path(d), LABELS))

    def test_config_must_allow_blank_issues(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "a.yml").write_text(GOOD)
            (Path(d) / "config.yml").write_text("blank_issues_enabled: false\n")
            errs = issue_forms.validate_dir(Path(d), LABELS)
            self.assertTrue(any("blank_issues_enabled" in e for e in errs), errs)
            (Path(d) / "config.yml").write_text("blank_issues_enabled: true\n")
            self.assertEqual(issue_forms.validate_dir(Path(d), LABELS), [])


class RealFormsTests(unittest.TestCase):
    def test_repo_forms_valid(self):
        d = ROOT / ".github" / "ISSUE_TEMPLATE"
        self.assertEqual(issue_forms.validate_dir(d, LABELS), [])

    def test_repo_has_three_forms_and_config(self):
        d = ROOT / ".github" / "ISSUE_TEMPLATE"
        forms = sorted(p.name for p in d.glob("*.yml") if p.name != "config.yml")
        self.assertEqual(len(forms), 3, forms)
        self.assertTrue((d / "config.yml").exists())


if __name__ == "__main__":
    unittest.main()
