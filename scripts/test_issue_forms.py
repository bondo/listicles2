"""Tests for scripts/issue_forms.py. Run: python3 -I scripts/test_issue_forms.py"""

import subprocess
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

    def test_duplicate_ids_rejected(self):
        extra = "  - type: input\n    id: what\n    attributes:\n      label: Again\n"
        errs = check(GOOD + extra)
        self.assertTrue(any("duplicate id" in e for e in errs), errs)

    def test_bad_id_characters_rejected(self):
        errs = check(GOOD.replace("id: what", "id: has space"))
        self.assertTrue(any("id" in e for e in errs), errs)

    def test_id_is_optional(self):
        self.assertEqual(check(GOOD.replace("    id: what\n", "")), [])

    def test_unknown_body_type_rejected(self):
        errs = check(GOOD.replace("type: textarea", "type: textare"))
        self.assertTrue(any("unknown type" in e for e in errs), errs)

    def test_markdown_without_value_rejected(self):
        extra = "  - type: markdown\n    attributes:\n      label: oops\n"
        errs = check(GOOD + extra)
        self.assertTrue(any("attributes.value" in e for e in errs), errs)

    def test_markdown_without_attributes_rejected(self):
        errs = check(GOOD + "  - type: markdown\n")
        self.assertTrue(any("attributes.value" in e for e in errs), errs)

    def test_missing_pyyaml_exits_1_with_hint(self):
        script = Path(__file__).resolve().parent / "issue_forms.py"
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "yaml.py").write_text("raise ImportError('no yaml')\n")
            r = subprocess.run(
                [sys.executable, "-S", str(script)], cwd=d, capture_output=True, text=True,
                env={"PYTHONPATH": d},
            )
        self.assertEqual(r.returncode, 1)
        self.assertIn("PyYAML required", r.stderr + r.stdout)
        self.assertNotIn("Traceback", r.stderr)


DROPDOWN = """\
  - type: dropdown
    id: area
    attributes:
      label: Area
      options:
        - One
        - Two
"""
CHECKBOXES = """\
  - type: checkboxes
    id: agree
    attributes:
      label: Agree
      options:
        - label: I agree
"""


class ShapeTests(unittest.TestCase):
    """Shapes GitHub's issue-form schema rejects (follow-up for issue 61, R2-01)."""

    def rejects(self, text, needle):
        errs = check(text)
        self.assertTrue(any(needle in e for e in errs), errs)

    def test_valid_dropdown_and_checkboxes_pass(self):
        self.assertEqual(check(GOOD + DROPDOWN + CHECKBOXES), [])

    def test_dropdown_without_options_rejected(self):
        self.rejects(GOOD + DROPDOWN.split("      options:")[0], "options")

    def test_dropdown_with_empty_options_rejected(self):
        self.rejects(GOOD + DROPDOWN.split("      options:")[0] + "      options: []\n", "options")

    def test_dropdown_duplicate_options_rejected(self):
        self.rejects(GOOD + DROPDOWN.replace("- Two", "- One"), "duplicate option")

    def test_dropdown_non_string_option_rejected(self):
        self.rejects(GOOD + DROPDOWN.replace("- Two", "- {a: b}"), "option")

    def test_checkboxes_without_options_rejected(self):
        self.rejects(GOOD + CHECKBOXES.split("      options:")[0], "options")

    def test_checkbox_option_without_label_rejected(self):
        self.rejects(GOOD + CHECKBOXES.replace("label: I agree", "required: true"), "option")

    def test_checkbox_option_required_must_be_boolean(self):
        bad = CHECKBOXES.replace("label: I agree", "label: I agree\n          required: yes please")
        self.rejects(GOOD + bad, "required")

    def test_required_checkbox_option_satisfies_required_rule(self):
        only = GOOD.split("  - type: textarea")[0] + CHECKBOXES.replace(
            "label: I agree", "label: I agree\n          required: true"
        )
        self.assertEqual(check(only), [])

    def test_duplicate_labels_across_fields_rejected(self):
        self.rejects(GOOD + DROPDOWN.replace("label: Area", "label: What do you think?"), "duplicate label")

    def test_distinct_labels_still_pass(self):
        self.assertEqual(check(GOOD + DROPDOWN.replace("label: Area", "label: Other")), [])

    def test_unknown_top_level_key_rejected(self):
        self.rejects(GOOD + "label: [feedback]\n", "unknown top-level key")

    def test_allowed_top_level_keys_pass(self):
        extra = "title: '[Feedback]: '\nassignees: [bondo]\nprojects: [bondo/1]\ntype: Bug\n"
        self.assertEqual(check(extra + GOOD), [])

    def test_validations_on_markdown_rejected(self):
        md = "  - type: markdown\n    attributes:\n      value: hi\n    validations:\n      required: true\n"
        self.rejects(GOOD + md, "validations")

    def test_required_must_be_boolean(self):
        self.rejects(GOOD.replace("required: true", 'required: "true"'), "must be a boolean")

    def test_validations_must_be_mapping(self):
        self.rejects(GOOD.replace("      required: true\n", "").replace("validations:", "validations: x"), "validations must be a mapping")

    def test_label_must_be_string(self):
        self.rejects(GOOD.replace("label: What do you think?", "label: 42"), "label must be a string")

    def test_label_must_not_be_blank(self):
        self.rejects(GOOD.replace("label: What do you think?", "label: ' '"), "label")

    def test_markdown_value_must_be_string(self):
        md = "  - type: markdown\n    attributes:\n      value: 123\n"
        self.rejects(GOOD + md, "value must be a string")

    def test_input_value_must_be_string(self):
        self.rejects(GOOD.replace("label: What do you think?", "label: L\n      value: 7"), "value must be a string")

    def test_title_must_be_string(self):
        self.rejects("title: [a]\n" + GOOD, "title")


class RealFormsTests(unittest.TestCase):
    def test_repo_forms_valid(self):
        d = ROOT / ".github" / "ISSUE_TEMPLATE"
        self.assertEqual(issue_forms.validate_dir(d, LABELS), [])

    def test_repo_forms_say_issues_are_public(self):
        d = ROOT / ".github" / "ISSUE_TEMPLATE"
        for p in d.glob("*.yml"):
            if p.name != "config.yml":
                self.assertIn("This is public", p.read_text(encoding="utf-8"), p.name)

    def test_repo_forms_have_danish_public_notice(self):
        d = ROOT / ".github" / "ISSUE_TEMPLATE"
        notice = "Dette er offentligt: udelad adresser, telefonnumre, rigtige navne og billeder af dit hjem."
        for p in d.glob("*.yml"):
            if p.name != "config.yml":
                self.assertIn(notice, p.read_text(encoding="utf-8"), p.name)

    def test_repo_has_three_forms_and_config(self):
        d = ROOT / ".github" / "ISSUE_TEMPLATE"
        forms = sorted(p.name for p in d.glob("*.yml") if p.name != "config.yml")
        self.assertEqual(len(forms), 3, forms)
        self.assertTrue((d / "config.yml").exists())


if __name__ == "__main__":
    unittest.main()
