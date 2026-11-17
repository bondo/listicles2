"""Tests for scripts/wireframes_safety.py (no URL- or error-derived text in innerHTML on the wireframes page).

Run: python3 -I scripts/test_wireframes_safety.py
"""

import html
import json
import re
import subprocess
import sys
import tempfile
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


class SanitizerMustWrapTheWholeValue(unittest.TestCase):
    """R2-02: a lookup or literal ternary somewhere in the expression must not clear the whole value."""

    def test_includes_in_the_condition_does_not_clean_the_value(self):
        t = js("const one = params.get('s');\nconst v = one.includes('a') ? one : '';\napp.innerHTML = `<p>${v}</p>`;")
        self.assertEqual(lines(t), [6])

    def test_literal_ternary_with_a_tainted_branch(self):
        t = js("const one = params.get('s');\nconst v = one === 'x' ? 'ok' : one;\napp.innerHTML = `<p>${v}</p>`;")
        self.assertEqual(lines(t), [6])

    def test_find_on_a_tainted_list(self):
        t = js("const list = params.get('s');\nconst v = list.find(x => x);\napp.innerHTML = `<p>${v}</p>`;")
        self.assertEqual(lines(t), [6])

    def test_a_name_that_is_not_a_whitelisted_sanitizer(self):
        t = js("const one = params.get('s');\napp.innerHTML = `<p>${sanitize(one)}</p>`;")
        self.assertEqual(lines(t), [5])

    def test_a_sanitizer_around_only_part_of_the_value(self):
        t = js("const one = params.get('s');\napp.innerHTML = `<p>${esc(one) + one}</p>`;")
        self.assertEqual(lines(t), [5])

    def test_whitelisted_sanitizers_around_the_whole_value_pass(self):
        t = js("const one = params.get('s');\napp.innerHTML = `<p>${esc(one)}</p>`;\napp.innerHTML = '<p>' + esc(location.hash) + '</p>';")
        self.assertEqual(ws.check(t), [])

    def test_whole_value_forms_that_pass(self):
        t = js(
            "const one = params.get('s');\nconst a = one === 'x' ? 'yes' : 'no';\nconst b = one.includes('x');\nconst c = LIST.find(x => x.id === one);\n"
            "app.innerHTML = `<p class=\"${a}\">${b}${c.name}</p>`;"
        )
        self.assertEqual(ws.check(t), [])


class Reassignment(unittest.TestCase):
    """R3-01: an existing name that is assigned from a source taints it, wherever the assignment sits."""

    SINK = "app.innerHTML = `<p>${a}</p>`;"

    def flagged(self, body: str, line: int):
        self.assertEqual(lines(js(body)), [line], body)

    def test_assignment_in_an_if_without_braces(self):
        self.flagged("let a = 'x';\nif (params.has('s')) a = params.get('s');\n" + self.SINK, 6)

    def test_assignment_on_the_same_line_after_a_semicolon(self):
        self.flagged("let a = 'x'; a = params.get('s');\n" + self.SINK, 5)

    def test_compound_assignments(self):
        for op in ("+=", "||=", "??=", "&&="):
            self.flagged(f"let a = 'x';\na {op} params.get('s');\n" + self.SINK, 6)

    def test_assignment_in_an_arrow_body(self):
        self.flagged("let a = 'x';\nbtn.onclick = () => a = location.hash;\n" + self.SINK, 6)

    def test_assignment_after_an_opening_brace(self):
        self.flagged("let a = 'x';\nif (c) { a = location.hash; }\n" + self.SINK, 6)

    def test_assignment_inside_a_block_but_use_after_it(self):
        self.flagged("let a = 'x';\nif (c) {\n  a = params.get('s');\n}\n" + self.SINK, 8)

    def test_assignment_to_a_parameter(self):
        self.flagged("function f(a) {\n  a = params.get('s');\n  app.innerHTML = `<p>${a}</p>`;\n}", 6)

    def test_else_branch_assignment(self):
        self.flagged("let a = 'x';\nif (c) { go(); } else a = location.hash;\n" + self.SINK, 6)

    def test_chained_comma_for_ternary_and_logical_assignments(self):
        self.flagged("let x, y;\nx = y = params.get('s');\napp.innerHTML = `<p>${y}</p>`;", 6)
        self.flagged("let a, b;\na = 1, b = params.get('s');\napp.innerHTML = `<p>${b}</p>`;", 6)
        self.flagged("let a;\nfor (a = params.get('s'); ; ) { break; }\napp.innerHTML = `<p>${a}</p>`;", 6)
        self.flagged("let a = 'x';\nc ? a = location.hash : 0;\napp.innerHTML = `<p>${a}</p>`;", 6)
        self.flagged("let a = 'x';\nc && (a = location.hash);\napp.innerHTML = `<p>${a}</p>`;", 6)
        self.flagged("let y;\nconst x = y = params.get('s');\napp.innerHTML = `<p>${y}</p>`;", 6)

    def test_assignment_text_inside_strings_and_templates_is_not_code(self):
        t = js("let a = 'x';\nconst h = `<i title=\"a = location.hash; a = params.get('s')\">${a}</i>`;\nlog('a = ' + location.hash);\n" + self.SINK)
        self.assertEqual(ws.check(t), [])

    def test_html_outside_script_tags_is_not_analysed(self):
        page = "<style>p { content: \"don't\"; }</style>\n<p>don't</p>\n" + js("const one = params.get('s');\napp.innerHTML = `<p>${one}</p>`;")
        self.assertEqual(lines(page), [7])

    def test_script_end_tags_with_attributes_or_whitespace_close_the_script(self):
        for end in ("</script>", "</script >", "</SCRIPT>", "</script foo>", "</script\t\n bar>"):
            page = "<p>before</p><script>a=1;" + end + "\n<p>after</p>"
            got = ws._script_only(page)
            self.assertIn("a=1;", got, end)
            self.assertNotIn("<p>after</p>", got, end)
            self.assertNotIn("<p>before</p>", got, end)
            self.assertEqual(got.count("\n"), page.count("\n"), end)

    def test_assignments_that_do_not_taint(self):
        for body in (
            "let a = 'x'; a = 'y';\n" + self.SINK,
            "let a = 'x';\nif (params.has('s')) a = 'y';\n" + self.SINK,
            "let a = 'x';\nconst t = params.get('s');\n" + self.SINK,
            "let a = 'x';\nif (a === params.get('s')) { go(); }\n" + self.SINK,
            "let a = 'x'; o.a = params.get('s');\n" + self.SINK,
            "let a = 'x'; a = esc(params.get('s'));\n" + self.SINK,
        ):
            self.assertEqual(ws.check(js(body)), [], body)

    def test_the_docstring_names_the_assignment_forms(self):
        self.assertIn("compound", ws.__doc__ or "")


class MoreSources(unittest.TestCase):
    def test_document_url_referrer_and_window_name(self):
        for src in ("document.URL", "document.documentURI", "document.referrer", "window.name", "location.href"):
            self.assertEqual(lines(js(f"app.innerHTML = `<p>${{{src}}}</p>`;")), [4], src)

    def test_fetched_data_in_a_then_callback(self):
        t = js("fetch(U).then(r => r.json()).then(d => { app.innerHTML = `<b>${d.name}</b>`; });")
        self.assertEqual(lines(t), [4])

    def test_fetched_data_passed_by_function_name(self):
        t = js("function render(T) { app.innerHTML = `<b>${T.name}</b>`; }\nfetch(U).then(r => r.json()).then(render);")
        self.assertEqual(lines(t), [4])

    def test_fetched_data_through_an_awaited_declaration(self):
        t = js("async function go() { const d = await (await fetch(U)).json(); app.innerHTML = `<b>${d.x}</b>`; }")
        self.assertEqual(lines(t), [4])

    def test_fetched_data_cleaned_at_the_source_passes(self):
        t = js("function render(T) { app.innerHTML = `<b>${T.name}</b>`; }\nfetch(U).then(r => r.json()).then(d => render(escDeep(d)));")
        self.assertEqual(ws.check(t), [])

    def test_function_parameter_that_receives_a_url_value(self):
        t = js("function show(m) { app.innerHTML = `<p>${m}</p>`; }\nshow(params.get('a'));")
        self.assertEqual(lines(t), [4])

    def test_function_parameter_that_only_gets_clean_values(self):
        t = js("function show(m) { app.innerHTML = `<p>${m}</p>`; }\nshow('fixed');")
        self.assertEqual(ws.check(t), [])

    def test_callback_parameters_of_a_tainted_receiver(self):
        t = js("const d = params.get('s');\nconst rows = Object.entries(d).map(([k, v]) => `<tr><td>${k}</td><td>${v}</td></tr>`).join('');")
        self.assertEqual(lines(t), [5])

    def test_markup_template_that_is_returned_not_assigned(self):
        t = js("const sheet = (d) => `<section>${d.title}</section>`;\nfetch(U).then(r => r.json()).then(d => { keep = sheet(d); });")
        self.assertEqual(lines(t), [4])

    def test_markup_template_and_the_sink_that_receives_it(self):
        t = js("const sheet = (d) => `<section>${d.title}</section>`;\nfetch(U).then(r => r.json()).then(d => { app.innerHTML = sheet(d); });")
        self.assertEqual(lines(t), [4, 5])

    def test_a_plain_text_template_is_not_markup(self):
        t = js("const one = params.get('s');\nshowText(`No screen ${one}`);")
        self.assertEqual(ws.check(t), [])

    def test_the_docstring_states_the_limits(self):
        doc = ws.__doc__ or ""
        self.assertIn("Limits", doc)
        for word in ("DOM", "aliasing", "same name"):
            self.assertIn(word, doc)


class PageHelpers(unittest.TestCase):
    """R2-01: the tokens URL must be same-origin and token values must be escaped; the helpers run under node."""

    BASE = "http://localhost:8000/docs/product/wireframes/wireframes.html"
    DEFAULT = "../../../design/tokens.json"

    @classmethod
    def helpers(cls) -> str:
        text = PAGE.read_text(encoding="utf-8")
        m = re.search(r"/\* safe-helpers:begin.*?\*/(.*?)/\* safe-helpers:end \*/", text, re.S)
        if not m:
            raise AssertionError("wireframes.html needs a /* safe-helpers:begin ... */ ... /* safe-helpers:end */ block (esc, escDeep, sameOriginUrl)")
        return m.group(1)

    def run_js(self, expr: str):
        prog = self.helpers() + "\nprocess.stdout.write(JSON.stringify(" + expr + "));"
        out = subprocess.run(["node", "-e", prog], capture_output=True, text=True, timeout=30)
        self.assertEqual(out.returncode, 0, out.stderr)
        return json.loads(out.stdout)

    def same_origin(self, value: str):
        return self.run_js(f"sameOriginUrl({json.dumps(value)}, {json.dumps(self.BASE)}, {json.dumps(self.DEFAULT)})")

    def test_other_origin_urls_are_replaced_by_the_default(self):
        for bad in ("https://evil.example/t.json", "http://localhost:9999/t.json", "//evil.example/t.json", "http://localhost.evil.example/t.json",
                    "javascript:alert(1)", "data:application/json,{}", "file:///etc/passwd", "http://user@evil.example/t.json"):
            self.assertEqual(self.same_origin(bad), self.DEFAULT, bad)

    def test_same_origin_urls_are_kept(self):
        self.assertEqual(self.same_origin("/design/tokens.json"), "http://localhost:8000/design/tokens.json")
        self.assertEqual(self.same_origin("../../../design/tokens.json"), "http://localhost:8000/design/tokens.json")
        self.assertEqual(self.same_origin("http://localhost:8000/copy.json"), "http://localhost:8000/copy.json")

    def test_markup_in_a_token_value_or_key_is_escaped(self):
        got = self.run_js("escDeep({meta: {font: '<img src=x onerror=alert(1)>', 'k\"<b>': 'a&b'}, list: ['<i>', 3, true, null]})")
        self.assertEqual(got["meta"]["font"], "&lt;img src=x onerror=alert(1)&gt;")
        self.assertEqual(got["meta"]["k&quot;&lt;b&gt;"], "a&amp;b")
        self.assertEqual(got["list"], ["&lt;i&gt;", 3, True, None])

    def test_esc_escapes_all_five_characters(self):
        self.assertEqual(self.run_js("esc(`&<>\"'`)"), "&amp;&lt;&gt;&quot;&#39;")

    def test_the_real_tokens_are_unchanged_by_escaping_apart_from_entities(self):
        real = json.loads((ROOT / "design" / "tokens.json").read_text(encoding="utf-8"))
        got = self.run_js("escDeep(" + json.dumps(real) + ")")

        def same(a, b):
            if isinstance(a, dict):
                return isinstance(b, dict) and {html.unescape(k) for k in a} == set(b) and all(same(a[k], b[html.unescape(k)]) for k in a)
            if isinstance(a, list):
                return isinstance(b, list) and len(a) == len(b) and all(same(x, y) for x, y in zip(a, b, strict=True))
            return html.unescape(a) == b if isinstance(a, str) else a == b

        self.assertTrue(same(got, real))

    def test_stored_theme_is_whitelisted(self):
        cases = (("light", "light"), ("dark", "dark"), ("tokens", "tokens"), ("sepia", "light"), ("", "light"), ("__proto__", "light"), ("DARK", "light"))
        for stored, want in cases:
            self.assertEqual(self.run_js(f"storedTheme({json.dumps(stored)})"), want, stored)
        self.assertEqual(self.run_js("storedTheme(null)"), "light")
        self.assertEqual(self.run_js("storedTheme(undefined)"), "light")

    def test_the_page_reads_the_stored_theme_through_the_whitelist(self):
        text = PAGE.read_text(encoding="utf-8")
        self.assertRegex(text, r"theme = storedTheme\(localStorage\.getItem\(")
        self.assertNotRegex(text, r"theme = localStorage\.getItem")

    def test_the_page_uses_the_helpers_for_the_tokens_url_and_the_fetched_data(self):
        text = PAGE.read_text(encoding="utf-8")
        self.assertRegex(text, r"TOKENS_URL = sameOriginUrl\(")
        self.assertRegex(text, r"render\(escDeep\(")


class TheRealPage(unittest.TestCase):
    def test_the_wireframes_page_has_no_url_or_error_text_in_innerhtml(self):
        self.assertEqual(ws.check(PAGE.read_text(encoding="utf-8")), [])

    def test_the_cli_exits_non_zero_on_a_bad_file_and_zero_on_the_page(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "bad.html"
            bad.write_text(js("app.innerHTML = location.hash;"), encoding="utf-8")
            self.assertEqual(ws.main([str(bad)]), 1)
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
