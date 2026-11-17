"""Tests for scripts/wireframes_safety.py (no URL- or error-derived text in innerHTML on the wireframes page).

Run: python3 -I scripts/test_wireframes_safety.py
"""

import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import wireframes_safety as ws  # noqa: E402  # justified: must follow the sys.path insert above

ROOT = Path(__file__).resolve().parent.parent
PAGE = ROOT / "docs" / "product" / "wireframes" / "wireframes.html"
PREFIX = "const params = new URLSearchParams(location.search);\nconst app = document.getElementById('app');\n"


def js(body: str) -> str:
    return "<script>\n" + PREFIX + body + "\n</script>"


def lines(text: str) -> list[int]:
    return [n for n, _ in ws.check(text)]


class UnsafePatternsFail(unittest.TestCase):
    def test_screen_id_from_the_query_string_in_a_template(self):
        t = js("const one = params.get('screen');\napp.innerHTML = `<p>No screen ${one}</p>`;")
        self.assertEqual(lines(t), [5])

    def test_error_in_a_catch_callback(self):
        t = js("fetch(U).catch(e => { app.innerHTML = `<p>Could not read (${e})</p>`; });")
        self.assertEqual(lines(t), [4])

    def test_error_in_a_try_catch(self):
        t = js("try { go(); } catch (err) { app.innerHTML = '<p>' + err.message + '</p>'; }")
        self.assertEqual(lines(t), [4])

    def test_url_constant_derived_from_params(self):
        t = js("const U = params.get('tokens') || 'x.json';\napp.innerHTML = `<p>${U}</p>`;")
        self.assertEqual(lines(t), [5])

    def test_value_derived_through_a_chain(self):
        t = js("const a = params.get('screen');\nconst b = 'x' + a;\nconst c = `y${b}`;\napp.innerHTML = c;")
        self.assertEqual(lines(t), [7])

    def test_direct_location_and_params_get_in_the_expression(self):
        self.assertEqual(lines(js("app.innerHTML = location.hash;")), [4])
        self.assertEqual(lines(js("app.innerHTML = `<b>${params.get('q')}</b>`;")), [4])

    def test_other_name_for_the_params_object(self):
        t = "const q = new URLSearchParams(window.location.search);\nel.innerHTML = '<i>' + q.get('a') + '</i>';"
        self.assertEqual(lines(t), [2])

    def test_append_assignment_outerhtml_and_insert_adjacent(self):
        self.assertEqual(lines(js("app.innerHTML += location.search;")), [4])
        self.assertEqual(lines(js("app.outerHTML = location.search;")), [4])
        self.assertEqual(lines(js("app.insertAdjacentHTML('beforeend', location.search);")), [4])

    def test_template_nested_in_a_template(self):
        t = js("const one = params.get('s');\napp.innerHTML = `<ul>${[1].map(() => `<li>${one}</li>`).join('')}</ul>`;")
        self.assertEqual(lines(t), [5])

    def test_message_names_the_line_and_the_remedy(self):
        (line, msg), = ws.check(js("app.innerHTML = location.hash;"))
        self.assertEqual(line, 4)
        self.assertIn("textContent", msg)
        self.assertIn("location", msg)


class SafePatternsPass(unittest.TestCase):
    def test_text_content(self):
        t = js("const one = params.get('screen');\nconst p = document.createElement('p');\np.textContent = `No screen ${one}`;\napp.replaceChildren(p);")
        self.assertEqual(ws.check(t), [])

    def test_static_markup_and_unrelated_data(self):
        t = js("const T = {a: 1};\napp.innerHTML = `<p>One screen ${T.a} location params.get</p>`;")
        self.assertEqual(ws.check(t), [])

    def test_text_that_only_mentions_the_words(self):
        t = js("const one = 'fixed';\napp.innerHTML = `<p>one location URLSearchParams params.get(x)</p>${one}`;")
        self.assertEqual(ws.check(t), [])

    def test_value_reduced_to_literals(self):
        t = js("const theme = params.get('theme') === 'dark' ? 'dark' : 'light';\napp.innerHTML = `<b class=\"${theme}\"></b>`;")
        self.assertEqual(ws.check(t), [])

    def test_value_looked_up_in_a_trusted_list(self):
        t = js("const one = params.get('screen');\nconst sc = SCREENS.find(x => x.id === one);\napp.innerHTML = sc ? shot(sc) : '';")
        self.assertEqual(ws.check(t), [])

    def test_comments_are_ignored(self):
        t = js("/* app.innerHTML = location.hash; */\napp.textContent = location.hash;")
        self.assertEqual(ws.check(t), [])

    def test_catch_without_using_the_error(self):
        t = js("try { go(); } catch (e) { /* ignore */ }\napp.innerHTML = '<p>done</p>';")
        self.assertEqual(ws.check(t), [])


class TheRealPage(unittest.TestCase):
    def test_the_wireframes_page_has_no_url_or_error_text_in_innerhtml(self):
        self.assertEqual(ws.check(PAGE.read_text(encoding="utf-8")), [])

    def test_the_cli_exits_non_zero_on_a_bad_file_and_zero_on_the_page(self):
        bad = ROOT / ".wireframes-safety-fixture.tmp"
        try:
            bad.write_text(js("app.innerHTML = location.hash;"), encoding="utf-8")
            self.assertEqual(ws.main([str(bad)]), 1)
        finally:
            bad.unlink(missing_ok=True)
        self.assertEqual(ws.main([]), 0)


class Wiring(unittest.TestCase):
    CMD = "python3 -I scripts/test_wireframes_safety.py"
    CHECK = "python3 -I scripts/wireframes_safety.py"

    def runs(self, text: str, cmd: str) -> bool:
        return re.search(r"(?m)^\s*(?:step\s+\S+\s+|run:\s*)" + re.escape(cmd) + r"\s*$", text) is not None

    def test_verify_and_ci_run_the_tests_and_the_check(self):
        verify = (ROOT / "scripts" / "verify.sh").read_text(encoding="utf-8")
        ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        for cmd in (self.CMD, self.CHECK):
            self.assertTrue(self.runs(verify, cmd), f"verify.sh must run {cmd}")
            self.assertTrue(self.runs(ci, cmd), f"ci.yml must run {cmd}")

    def test_the_wiring_matcher_has_a_negative_case(self):
        self.assertFalse(self.runs("# python3 -I scripts/test_wireframes_safety.py", self.CMD))
        self.assertFalse(self.runs("step x python3 -I scripts/test_wireframes_safety.py --skip", self.CMD))


if __name__ == "__main__":
    unittest.main()
