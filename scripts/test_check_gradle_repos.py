"""Tests for scripts/check_gradle_repos.py. Run: python3 -I scripts/test_check_gradle_repos.py"""

import random
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_gradle_repos as c  # noqa: E402  # justified: must follow the sys.path insert above

ROOT = Path(__file__).resolve().parent.parent
GOOD_REPOS = f"""
        google {{
            content {{ includeGroupAndSubgroups("androidx") }}
        }}
        maven("{c.MIRROR}")
        mavenCentral()
"""
CHECK_CMD = "python3 -I scripts/check_gradle_repos.py"
TEST_CMD = "python3 -I scripts/test_check_gradle_repos.py"
GOOD_PROPS = f"{c.TENTATIVES}=6\n{c.BACKOFF}=1000\n"


def settings(plugin_repos=GOOD_REPOS, dep_repos=GOOD_REPOS):
    return (
        f"pluginManagement {{\n    repositories {{{plugin_repos}    }}\n}}\n"
        f"dependencyResolutionManagement {{\n    repositories {{{dep_repos}    }}\n}}\n"
    )


class Settings(unittest.TestCase):
    def test_good_settings_pass(self):
        self.assertEqual(c.check_settings(settings()), [])

    def test_mirror_missing(self):
        bad = GOOD_REPOS.replace(f'maven("{c.MIRROR}")', "")
        self.assertIn("pluginManagement: Maven Central mirror", c.check_settings(settings(plugin_repos=bad))[0])

    def test_mirror_after_central(self):
        bad = 'google() { content { includeGroup("x") } }\nmavenCentral()\nmaven("' + c.MIRROR + '")\n'
        self.assertEqual(
            c.check_settings(settings(dep_repos=bad)),
            ["dependencyResolutionManagement: Maven Central mirror must come before mavenCentral()"],
        )

    def test_central_fallback_missing(self):
        bad = GOOD_REPOS.replace("mavenCentral()", "")
        self.assertIn("mavenCentral() fallback missing", c.check_settings(settings(dep_repos=bad))[0])

    def test_unfiltered_google(self):
        bad = f'google()\nmaven("{c.MIRROR}")\nmavenCentral()\n'
        self.assertEqual(c.check_settings(settings(plugin_repos=bad)), ["pluginManagement: google() needs a content filter"])

    def test_google_with_parentheses_and_filter_passes(self):
        ok = GOOD_REPOS.replace("google {", "google() {")
        self.assertEqual(c.check_settings(settings(plugin_repos=ok)), [])

    def test_line_commented_mirror_does_not_count(self):
        bad = 'google { content { includeGroup("androidx") } }\n// maven("' + c.MIRROR + '")\nmavenCentral()\n'
        self.assertIn("Maven Central mirror " + c.MIRROR + " missing", c.check_settings(settings(dep_repos=bad))[0])

    def test_block_commented_central_does_not_count(self):
        bad = 'google { content { includeGroup("androidx") } }\nmaven("' + c.MIRROR + '")\n/* mavenCentral() */\n'
        self.assertIn("mavenCentral() fallback missing", c.check_settings(settings(dep_repos=bad))[0])

    def test_commented_out_mirror_on_one_line(self):
        bad = 'google{content{includeGroup("androidx")}} // maven("' + c.MIRROR + '") mavenCentral()\n'
        self.assertNotEqual(c.check_settings(settings(dep_repos=bad)), [])

    def test_no_google_is_fine_despite_googleapis_url(self):
        ok = f'maven("{c.MIRROR}")\nmavenCentral()\n'
        self.assertEqual(c.check_settings(settings(plugin_repos=ok, dep_repos=ok)), [])

    def test_second_unfiltered_google(self):
        bad = GOOD_REPOS + "        google()\n"
        self.assertEqual(c.check_settings(settings(dep_repos=bad)), ["dependencyResolutionManagement: google() needs a content filter"])

    def test_empty_content_filter(self):
        bad = GOOD_REPOS.replace('includeGroupAndSubgroups("androidx")', "")
        self.assertEqual(c.check_settings(settings(plugin_repos=bad)), ["pluginManagement: google() needs a content filter"])

    def test_google_block_without_content(self):
        bad = f'google {{ }}\nmaven("{c.MIRROR}")\nmavenCentral()\n'
        self.assertEqual(c.check_settings(settings(plugin_repos=bad)), ["pluginManagement: google() needs a content filter"])

    def test_second_outer_block_with_unfiltered_google(self):
        bad = settings() + "dependencyResolutionManagement {\n    repositories {\n        google()\n    }\n}\n"
        self.assertEqual(c.check_settings(bad), ["dependencyResolutionManagement: google() needs a content filter"])

    def test_second_repositories_block_with_unfiltered_google(self):
        bad = settings(dep_repos=GOOD_REPOS + "    }\n    repositories {\n        google()\n")
        self.assertEqual(c.check_settings(bad), ["dependencyResolutionManagement: google() needs a content filter"])

    def test_qualified_unfiltered_google(self):
        bad = GOOD_REPOS + "        this.google()\n"
        self.assertEqual(c.check_settings(settings(plugin_repos=bad)), ["pluginManagement: google() needs a content filter"])

    def test_central_before_mirror_across_repositories_blocks(self):
        first = 'google { content { includeGroup("androidx") } }\nmavenCentral()\n'
        bad = settings(dep_repos=first + f'    }}\n    repositories {{\n        maven("{c.MIRROR}")\n')
        self.assertEqual(
            c.check_settings(bad),
            ["dependencyResolutionManagement: Maven Central mirror must come before mavenCentral()"],
        )

    def test_missing_block(self):
        self.assertIn("pluginManagement: no repositories block", c.check_settings("rootProject.name = \"x\"\n"))


GOOGLE = 'google { content { includeGroup("androidx") } }\n'
MIRROR_CALL = f'maven("{c.MIRROR}")\n'
MISSING = [f"dependencyResolutionManagement: Maven Central mirror {c.MIRROR} missing"]
BEFORE = ["dependencyResolutionManagement: Maven Central mirror must come before mavenCentral()"]
UNFILTERED = ["dependencyResolutionManagement: google() needs a content filter"]
NO_CENTRAL = ["dependencyResolutionManagement: mavenCentral() fallback missing"]


class Hardening(unittest.TestCase):
    """Follow-up for issue 54: nested comments and valid forms that were rejected; every bypass must stay an error."""

    def dep(self, repos):
        return c.check_settings(settings(dep_repos=repos))

    # Item 1: Kotlin block comments nest.
    def test_mirror_inside_nested_block_comment_does_not_count(self):
        self.assertEqual(self.dep(GOOGLE + f"/* a /* b */ {MIRROR_CALL} */\nmavenCentral()\n"), MISSING)

    def test_central_inside_nested_block_comment_does_not_count(self):
        self.assertEqual(self.dep(GOOGLE + MIRROR_CALL + "/* a /* b */ mavenCentral() */\n"), NO_CENTRAL)

    def test_nested_comment_then_real_code_passes(self):
        self.assertEqual(self.dep(GOOGLE + "/* a /* b */ c */\n" + MIRROR_CALL + "mavenCentral()\n"), [])

    def test_unterminated_nested_comment_hides_the_rest(self):
        # the swallowed closing braces leave no repositories block, which is an error as well
        got = self.dep(GOOGLE + f"/* a /* b */ {MIRROR_CALL}mavenCentral()\n")
        self.assertEqual(got, ["dependencyResolutionManagement: no repositories block"])

    def test_comment_markers_inside_strings_do_not_open_a_comment(self):
        self.assertEqual(self.dep(GOOGLE + 'val s = "/*"\n' + MIRROR_CALL + "mavenCentral()\n"), [])

    def test_block_comment_does_not_glue_tokens_into_a_call(self):
        self.assertEqual(self.dep(GOOGLE + MIRROR_CALL + "maven/**/Central()\n"), NO_CENTRAL)

    # Item 2a: exclusiveContent { forRepository { google() } filter { include...() } } is a valid filter.
    def exclusive(self, filter_body='includeGroupAndSubgroups("androidx")'):
        return f"exclusiveContent {{ forRepository {{ google() }} filter {{ {filter_body} }} }}\n" + MIRROR_CALL + "mavenCentral()\n"

    def test_exclusive_content_with_include_filter_passes(self):
        self.assertEqual(self.dep(self.exclusive()), [])
        self.assertEqual(self.dep(self.exclusive('includeGroup("androidx")')), [])

    def test_exclusive_content_without_filter_still_fails(self):
        bad = "exclusiveContent { forRepository { google() } }\n" + MIRROR_CALL + "mavenCentral()\n"
        self.assertEqual(self.dep(bad), UNFILTERED)

    def test_exclusive_content_with_empty_or_exclude_only_filter_still_fails(self):
        self.assertEqual(self.dep(self.exclusive("")), UNFILTERED)
        self.assertEqual(self.dep(self.exclusive('excludeGroup("androidx")')), UNFILTERED)

    def test_exclusive_content_filter_commented_out_still_fails(self):
        bad = 'exclusiveContent { forRepository { google() } filter { /* includeGroup("x") */ } }\n' + MIRROR_CALL + "mavenCentral()\n"
        self.assertEqual(self.dep(bad), UNFILTERED)

    def test_exclusive_content_filter_does_not_cover_google_outside_it(self):
        self.assertEqual(self.dep(self.exclusive() + "google()\n"), UNFILTERED)
        other = 'exclusiveContent { forRepository { maven("https://x.example") } filter { includeGroup("x") } }\ngoogle()\n'
        self.assertEqual(self.dep(other + MIRROR_CALL + "mavenCentral()\n"), UNFILTERED)

    def test_filter_of_one_exclusive_content_does_not_cover_a_second_one(self):
        self.assertEqual(self.dep(self.exclusive() + "exclusiveContent { forRepository { google() } }\n"), UNFILTERED)

    def test_filter_nested_inside_forrepository_does_not_count(self):
        bad = 'exclusiveContent { forRepository { google() ; filter { includeGroup("x") } } }\n' + MIRROR_CALL + "mavenCentral()\n"
        self.assertEqual(self.dep(bad), UNFILTERED)

    def test_forrepository_body_must_be_exactly_google(self):
        # Gradle applies the exclusive filter only to the repository the lambda returns, so any other repository
        # or statement in the body means a google() there may be asked first for every group.
        for body in ('google(); maven("https://x.example")', 'maven { url = uri("https://x.example"); google() }',
                     'maven("https://x.example"); google()', "google(); google()", "val g = google()", "this.google()", "google"):
            with self.subTest(body=body):
                bad = f'exclusiveContent {{ forRepository {{ {body} }} filter {{ includeGroup("x") }} }}\n'
                self.assertEqual(self.dep(bad + MIRROR_CALL + "mavenCentral()\n"), UNFILTERED)

    def test_forrepository_with_only_google_in_any_layout_passes(self):
        for body in ("google()", " google() ", "\n google()\n", "google();", "google ( )", "/* c */ google() /* c */"):
            with self.subTest(body=body):
                ok = f'exclusiveContent {{ forRepository {{ {body} }} filter {{ includeGroup("x") }} }}\n'
                self.assertEqual(self.dep(ok + MIRROR_CALL + "mavenCentral()\n"), [])

    def test_google_with_its_own_filter_inside_forrepository_passes(self):
        ok = "exclusiveContent { forRepository { " + GOOGLE + "} }\n" + MIRROR_CALL + "mavenCentral()\n"
        self.assertEqual(self.dep(ok), [])

    # Item 2b: mavenCentral { } is the same repository as mavenCentral().
    def test_central_with_empty_block_passes(self):
        for call in ("mavenCentral { }", "mavenCentral {}", "mavenCentral() { }", "mavenCentral()"):
            with self.subTest(call=call):
                self.assertEqual(self.dep(GOOGLE + MIRROR_CALL + call + "\n"), [])

    def test_central_with_block_still_must_come_after_the_mirror(self):
        self.assertEqual(self.dep(GOOGLE + "mavenCentral { }\n" + MIRROR_CALL), BEFORE)

    def test_central_mentioned_without_call_does_not_count(self):
        for text in ("val mavenCentral = 1", "mavenCentral", "mavenCentral.foo"):
            with self.subTest(text=text):
                self.assertEqual(self.dep(GOOGLE + MIRROR_CALL + text + "\n"), NO_CENTRAL)

    # Item 2c: braces inside strings must not move block bounds (already handled by taking bounds from the blanked text).
    def test_closing_brace_in_string_before_the_mirror_passes(self):
        for before in ('maven("a}b")\n', 'val s = "}"\n', 'val s = "\\"}"\n', 'val s = "{"\n'):
            with self.subTest(before=before):
                self.assertEqual(self.dep(GOOGLE + before + MIRROR_CALL + "mavenCentral()\n"), [])

    def test_brace_in_string_does_not_end_the_repositories_block(self):
        bad = settings(dep_repos=GOOGLE + 'val s = "}"\n' + MIRROR_CALL + "mavenCentral()\n    }\n    repositories {\n        google()\n")
        self.assertEqual(c.check_settings(bad), UNFILTERED)

    def test_brace_in_string_does_not_hide_an_unfiltered_google(self):
        self.assertEqual(self.dep(GOOGLE + 'val s = "{"\ngoogle()\n' + MIRROR_CALL + "mavenCentral()\n"), UNFILTERED)

    # Item 2d: a char literal of a double quote is not the start of a string.
    def test_double_quote_char_literal_passes(self):
        self.assertEqual(self.dep(GOOGLE + "val q = '\"'\n" + MIRROR_CALL + "mavenCentral()\n"), [])

    def test_escaped_char_literals_pass(self):
        ok = GOOGLE + "val a = '\\''\nval b = '\\u0022'\nval c = '\\\\'\n" + MIRROR_CALL + "mavenCentral()\n"
        self.assertEqual(self.dep(ok), [])

    def test_double_quote_char_literal_does_not_hide_a_commented_mirror(self):
        bad = GOOGLE + "val q = '\"'\n// " + MIRROR_CALL + "mavenCentral()\n"
        self.assertEqual(self.dep(bad), MISSING)

    def test_double_quote_char_literal_keeps_the_mirror_order_check(self):
        self.assertEqual(self.dep(GOOGLE + "val q = '\"'\nmavenCentral()\n" + MIRROR_CALL), BEFORE)

    def test_double_quote_char_literal_does_not_hide_an_unfiltered_google(self):
        self.assertEqual(self.dep("val q = '\"'\ngoogle()\n" + MIRROR_CALL + "mavenCentral()\n"), UNFILTERED)

    def test_apostrophe_in_comment_or_string_is_not_a_char_literal(self):
        ok = GOOGLE + "// it's\n/* don't */\nval s = \"it's\"\n" + MIRROR_CALL + "mavenCentral()\n"
        self.assertEqual(self.dep(ok), [])


PLUGIN_UNFILTERED = ["pluginManagement: google() needs a content filter"]
OUTSIDE = ["settings.gradle.kts: google() outside pluginManagement and dependencyResolutionManagement needs a content filter"]
TAIL = MIRROR_CALL + "mavenCentral()\n"


def with_extra(extra, plugin_extra=""):
    """Settings whose two good repositories blocks are followed by `extra` statements inside their outer blocks."""
    return (
        f"pluginManagement {{\n    repositories {{{GOOD_REPOS}    }}\n{plugin_extra}}}\n"
        f"dependencyResolutionManagement {{\n    repositories {{{GOOD_REPOS}    }}\n{extra}\n}}\n"
    )


class DottedGoogle(unittest.TestCase):
    """Issue 226: google() written as repositories.google() (or any form outside a braced repositories block) needs the same filter."""

    def test_unfiltered_dotted_forms_are_flagged(self):
        for extra in (
            "repositories.google()",
            "repositories.google",
            "this.repositories.google()",
            "repositories.google { }",
            "repositories.google() { }",
            "repositories.google { content { } }",
            'repositories.google { content { excludeGroup("x") } }',
            "repositories.apply { google() }",
            "with(repositories) { google() }",
            "val g = repositories::google",
            "repositories.exclusiveContent { forRepository { google() } }",
            "repositories.exclusiveContent { forRepository { google() } filter { } }",
        ):
            with self.subTest(extra=extra):
                self.assertEqual(c.check_settings(with_extra(extra)), UNFILTERED)

    def test_unfiltered_dotted_google_in_plugin_management_is_flagged(self):
        self.assertEqual(c.check_settings(with_extra("", plugin_extra="    repositories.google()\n")), PLUGIN_UNFILTERED)

    def test_dotted_google_outside_both_outer_blocks_is_flagged(self):
        for extra in (
            "pluginManagement.repositories.google()",
            "settings.dependencyResolutionManagement.repositories { google() }",
            "buildscript { repositories { google() } }",
            "gradle.settings.pluginManagement.repositories.google()",
        ):
            with self.subTest(extra=extra):
                self.assertEqual(c.check_settings(with_extra("") + extra + "\n"), OUTSIDE)

    def test_dotted_google_without_a_braced_repositories_block_reports_both(self):
        text = f"pluginManagement {{\n    repositories {{{GOOD_REPOS}    }}\n}}\ndependencyResolutionManagement {{ repositories.google() }}\n"
        self.assertEqual(c.check_settings(text), ["dependencyResolutionManagement: no repositories block"] + UNFILTERED)

    def test_every_unfiltered_place_is_reported_once_per_block(self):
        got = c.check_settings(with_extra("repositories.google()\nrepositories.google()", "    repositories.google()\n") + "repositories.google()\n")
        self.assertEqual(got, PLUGIN_UNFILTERED + UNFILTERED + OUTSIDE)

    def test_filtered_dotted_forms_pass(self):
        for extra in (
            'repositories.google { content { includeGroup("androidx") } }',
            'repositories.google() { content { includeGroupAndSubgroups("androidx") } }',
            'repositories.exclusiveContent { forRepository { google() } filter { includeGroup("x") } }',
            'with(repositories) { google { content { includeGroup("x") } } }',
        ):
            with self.subTest(extra=extra):
                self.assertEqual(c.check_settings(with_extra(extra)), [])

    def test_google_in_comments_and_strings_outside_the_block_is_not_a_call(self):
        extra = '// repositories.google()\n/* repositories.google() */\nval s = "repositories.google()"\nval r = """repositories.google()"""'
        self.assertEqual(c.check_settings(with_extra(extra) + "// google()\n"), [])


NESTED = 'val s = "${ if (c) "}" else "" }"\n'


class Strings(unittest.TestCase):
    """Issue 227: raw strings and string templates with nested strings, braces or code must not hide an unfiltered google()."""

    def dep(self, repos):
        return c.check_settings(settings(dep_repos=repos))

    def hidden(self, before):
        """`before` is a statement that must not swallow the unfiltered google() that follows it."""
        return self.dep(GOOGLE + TAIL + before + "google()\n")

    def test_nested_string_with_brace_in_a_template_does_not_hide_google(self):
        self.assertEqual(self.hidden(NESTED), UNFILTERED)

    def test_raw_string_with_an_odd_number_of_quotes_does_not_hide_google(self):
        for before in ('val s = """a"b"""\n', 'val s = """x""""\n', 'val s = """\\"""\n', 'val s = """"""\n', 'val s = """a""b"""\n'):
            with self.subTest(before=before):
                self.assertEqual(self.hidden(before), UNFILTERED)

    def test_templates_inside_raw_strings_and_nested_templates_do_not_hide_google(self):
        for before in (
            'val s = """${ "}" }"""\n',
            'val s = """${ "${ "}" }" }"""\n',
            'val s = "${ "${ "}" }" }"\n',
            "val s = \"${ '}' }\"\n",
            'val s = "${ /* } */ 1 }"\n',
            'val s = "${ 1 // }\n }"\n',
            'val s = "${ mapOf("a" to "}").size }"\n',
        ):
            with self.subTest(before=before):
                self.assertEqual(self.hidden(before), UNFILTERED)

    def test_google_called_inside_a_template_is_code(self):
        for before in ('val s = "${google()}"\n', 'val s = """${ google() }"""\n', 'val s = "${ "${ google() }" }"\n'):
            with self.subTest(before=before):
                self.assertEqual(self.dep(GOOGLE + TAIL + before), UNFILTERED)

    def test_filtered_google_inside_a_template_passes(self):
        ok = 'val s = "${ google { content { includeGroup("x") } } }"\n'
        self.assertEqual(self.dep(GOOGLE + TAIL + ok), [])

    def test_valid_strings_keep_the_check_green(self):
        for before in (
            NESTED,
            'val s = """a"b"""\n',
            'val s = """x""""\n',
            'val s = """\\"""\n',
            'val s = """a\n}\n"{"\n"""\n',
            'val s = """${ "}" }"""\n',
            'val s = "${ "${ "}" }" }"\n',
            'val s = "${ if (c) \'}\' else \'{\' }"\n',
            'val s = "$x and ${y} and \\$z and \\${w}"\n',
            'val s = """$ $x ${\'$\'}"""\n',
            'val s = "// /* \\" \'"\n',
            'val s = ""\nval t = ""\n',
            "val q = '\"'\nval s = \"it's\"\n",
        ):
            with self.subTest(before=before):
                self.assertEqual(self.dep(GOOGLE + TAIL + before), [])
                self.assertEqual(self.dep(GOOGLE + before + TAIL), [])

    def test_mirror_in_a_raw_string_call_counts(self):
        self.assertEqual(self.dep(GOOGLE + f'maven("""{c.MIRROR}""")\nmavenCentral()\n'), [])

    def test_mirror_order_and_missing_checks_survive_nested_templates(self):
        self.assertEqual(self.dep(GOOGLE + NESTED + "mavenCentral()\n" + MIRROR_CALL), BEFORE)
        self.assertEqual(self.dep(GOOGLE + NESTED + "mavenCentral()\n"), MISSING)

    def test_commented_mirror_after_nested_template_does_not_count(self):
        self.assertEqual(self.dep(GOOGLE + NESTED + "// " + MIRROR_CALL + "mavenCentral()\n"), MISSING)

    def test_unparsable_strings_fail_closed(self):
        for before in (
            'val s = "abc\n',
            'val s = "abc',
            'val s = """abc\n',
            'val s = "${ x\n',
            'val s = "${ "}" \n',
            'val s = """${ x """\n',
            'val s = "${ "abc }"\n',
            'val s = "\\',
        ):
            with self.subTest(before=before):
                got = self.dep(GOOGLE + TAIL + before)
                self.assertEqual(len(got), 1)
                self.assertTrue(got[0].startswith("settings.gradle.kts: cannot parse"), got)

    def test_strip_never_fails_open_on_random_input(self):
        rng = random.Random(227)
        alphabet = ['"', '"""', "$", "${", "{", "}", "'", "\\", "/", "*", "//", "/*", "*/", "\n", "a", " ", "google()"]
        for _ in range(3000):
            text = "".join(rng.choice(alphabet) for _ in range(rng.randint(1, 14)))
            try:
                blanked, kept = c._strip(text, blank_strings=True), c._strip(text)
            except c.Unparsable:
                continue
            self.assertEqual(len(blanked), len(kept), repr(text))
            self.assertTrue(all(b in (k, " ") for b, k in zip(blanked, kept, strict=True)), repr(text))  # blanking only ever writes spaces


class Properties(unittest.TestCase):
    def test_good_properties_pass(self):
        self.assertEqual(c.check_properties(GOOD_PROPS), [])

    def test_missing_properties(self):
        self.assertEqual(len(c.check_properties("org.gradle.parallel=true\n")), 2)

    def test_too_few_retries(self):
        self.assertEqual(
            c.check_properties(f"{c.TENTATIVES}=3\n{c.BACKOFF}=1000\n"),
            [f"gradle.properties: {c.TENTATIVES}=3 is below {c.MIN_TENTATIVES}"],
        )

    def test_commented_out_does_not_count(self):
        self.assertEqual(len(c.check_properties(f"# {c.TENTATIVES}=6\n{c.BACKOFF}=1000\n")), 1)

    def test_not_a_number(self):
        self.assertEqual(len(c.check_properties(f"{c.TENTATIVES}=lots\n{c.BACKOFF}=1000\n")), 1)


HASH = "a" * 64
GOOD_META = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<verification-metadata xmlns="https://schema.gradle.org/dependency-verification">\n'
    "   <configuration>\n      <verify-metadata>true</verify-metadata>\n      <verify-signatures>false</verify-signatures>\n"
    "   </configuration>\n   <components>\n"
    '      <component group="g" name="n" version="1">\n'
    f'         <artifact name="n-1.jar">\n            <sha256 value="{HASH}" origin="Generated by Gradle"/>\n         </artifact>\n'
    "      </component>\n   </components>\n</verification-metadata>\n"
)


class Verification(unittest.TestCase):
    def check(self, meta=GOOD_META, props=GOOD_PROPS):
        return c.check_verification(meta, props)

    def test_good_metadata_passes(self):
        self.assertEqual(self.check(), [])

    def test_missing_metadata_file(self):
        self.assertEqual(self.check(meta=None), ["verification-metadata.xml missing"])

    def test_not_xml(self):
        self.assertEqual(self.check(meta="<oops"), ["verification-metadata.xml is not well-formed XML"])

    def test_verification_switched_off_in_metadata(self):
        bad = GOOD_META.replace("<verify-metadata>true", "<verify-metadata>false")
        self.assertEqual(self.check(meta=bad), ["verification-metadata.xml: verify-metadata must be true"])

    def test_no_components(self):
        bad = GOOD_META[: GOOD_META.index("<components>")] + "<components/>\n</verification-metadata>\n"
        self.assertEqual(self.check(meta=bad), ["verification-metadata.xml: no components"])

    def test_artifact_without_sha256(self):
        bad = GOOD_META.replace(f'<sha256 value="{HASH}" origin="Generated by Gradle"/>', "")
        self.assertEqual(self.check(meta=bad), ["verification-metadata.xml: artifact n-1.jar of g:n:1 has no sha256"])

    def test_malformed_sha256_value(self):
        bad = GOOD_META.replace(HASH, "abc")
        self.assertEqual(self.check(meta=bad), ["verification-metadata.xml: artifact n-1.jar of g:n:1 has no sha256"])

    def aapt2(self, oses):
        arts = "".join(
            f'<artifact name="aapt2-9-{o}.jar"><sha256 value="{HASH}" origin="Generated by Gradle"/></artifact>' for o in oses
        )
        return GOOD_META.replace("</components>", f'<component group="com.android.tools.build" name="aapt2" version="9">{arts}</component></components>')

    def test_aapt2_for_all_three_operating_systems_passes(self):
        self.assertEqual(self.check(meta=self.aapt2(["linux", "osx", "windows"])), [])

    def test_aapt2_missing_an_operating_system(self):
        self.assertEqual(
            self.check(meta=self.aapt2(["linux"])),
            ["verification-metadata.xml: aapt2 9 lacks osx, windows jars (see docs/ANDROID-BEST-PRACTICES.md section 11)"],
        )
        self.assertEqual(
            self.check(meta=self.aapt2(["osx", "windows"])),
            ["verification-metadata.xml: aapt2 9 lacks linux jar (see docs/ANDROID-BEST-PRACTICES.md section 11)"],
        )

    def test_trusted_artifacts_bypass(self):
        bad = GOOD_META.replace("</configuration>", '<trusted-artifacts><trust group="g"/></trusted-artifacts></configuration>')
        self.assertEqual(self.check(meta=bad), ["verification-metadata.xml: trusted-artifacts bypass verification"])

    def test_gradle_properties_switch_off(self):
        for value in ("off", "lenient"):
            self.assertEqual(
                self.check(props=GOOD_PROPS + f"org.gradle.dependency.verification={value}\n"),
                [f"gradle.properties: org.gradle.dependency.verification={value} disables verification"],
            )

    def test_gradle_properties_equivalent_spellings(self):
        for line in (
            "org.gradle.dependency.verification=LENIENT",
            "org.gradle.dependency.verification:lenient",
            "org.gradle.dependency.verification lenient",
            "org.gradle.dependency.verification = Off",
            "  org.gradle.dependency.verification\t=\toff  ",
        ):
            with self.subTest(line=line):
                self.assertEqual(len(self.check(props=GOOD_PROPS + line + "\n")), 1)

    def test_cli_flags_in_verify_script(self):
        for text in ("./gradlew -F off build", "./gradlew -F=lenient build", "./gradlew --dependency-verification=lenient x",
                     "./gradlew --dependency-verification off x", "./gradlew -Dorg.gradle.dependency.verification=off x",
                     "./gradlew --DEPENDENCY-VERIFICATION=Off x"):
            with self.subTest(text=text):
                self.assertEqual(
                    c.check_verification(GOOD_META, GOOD_PROPS, text),
                    ["scripts/verify.sh: switches Gradle dependency verification off"],
                )

    def test_quoted_and_attached_flag_forms(self):
        for text in ('./gradlew -F "lenient" x', "./gradlew -F 'off' x", './gradlew --dependency-verification="lenient" x',
                     "./gradlew -Flenient x", "./gradlew -F=off x"):
            with self.subTest(text=text):
                self.assertEqual(
                    c.check_verification(GOOD_META, GOOD_PROPS, text),
                    ["scripts/verify.sh: switches Gradle dependency verification off"],
                )

    def test_strict_flag_forms_pass(self):
        for text in ("./gradlew -F strict x", "./gradlew -Fstrict x", './gradlew -F "strict" x'):
            with self.subTest(text=text):
                self.assertEqual(c.check_verification(GOOD_META, GOOD_PROPS, text), [])

    def test_properties_line_continuation(self):
        bad = GOOD_PROPS + "org.gradle.dependency.verification=\\\n    lenient\n"
        self.assertEqual(self.check(props=bad), ["gradle.properties: org.gradle.dependency.verification=lenient disables verification"])
        ok = GOOD_PROPS + "# note \\\norg.gradle.dependency.verification=strict\n"
        self.assertEqual(self.check(props=ok), [])

    def test_verify_script_without_flags_and_commented_flag_pass(self):
        ok = './gradlew -q --console=plain "$@"\n# ./gradlew -F off build\nstep x python3 -F foo\n'
        self.assertEqual(c.check_verification(GOOD_META, GOOD_PROPS, ok), [])

    def test_gradle_properties_strict_is_fine_and_commented_off_ignored(self):
        self.assertEqual(self.check(props=GOOD_PROPS + "org.gradle.dependency.verification=strict\n"), [])
        self.assertEqual(self.check(props=GOOD_PROPS + "# org.gradle.dependency.verification=off\n"), [])


class Repo(unittest.TestCase):
    def test_repo_config_passes(self):
        self.assertEqual(c.main(ROOT), 0)


def read(*parts):
    return ROOT.joinpath(*parts).read_text(encoding="utf-8")


def active_lines(text):
    return [ln.strip() for ln in text.splitlines() if ln.strip() and not ln.strip().startswith("#")]


def runs(text, command):
    """True if an active line is exactly the command as a verify.sh `step <name> <cmd>` or a workflow `run: <cmd>`."""
    pattern = re.compile(rf"^(?:step\s+[\w-]+\s+|(?:-\s+)?run:\s+){re.escape(command)}$")
    return any(pattern.match(ln) for ln in active_lines(text))


def job(text, name):
    m = re.search(rf"^  {re.escape(name)}:\n(.*?)(?=^  [A-Za-z][\w-]*:[ \t]*(?:#.*)?$|\Z)", text, re.S | re.M)
    return m.group(1) if m else None


def wiring_problems(verify, ci):
    """Problems with how verify.sh and ci.yml run the check and its tests (both must run in verify.sh even with --fast)."""
    problems = []
    top_level = "\n".join(ln for ln in verify.splitlines() if ln == ln.lstrip())
    for cmd in (CHECK_CMD, TEST_CMD):
        if not runs(top_level, cmd):
            problems.append(f"verify.sh does not run `{cmd}` as a top-level step")
    static = job(ci, "static")
    if static is None:
        return problems + ["ci.yml has no static job"]
    for cmd in (CHECK_CMD, TEST_CMD):
        if not runs(static, cmd):
            problems.append(f"ci.yml static job does not run `{cmd}`")
    if re.search(r"(?m)^\s*(?:-\s+)?if:", static) or "continue-on-error" in static:
        problems.append("ci.yml static job has if: or continue-on-error")
    if re.search(r"(?m)^    permissions:", static) or not re.search(r"(?m)^permissions:\n  contents: read\n(?!  )", ci):
        problems.append("ci.yml permissions must stay contents: read only, with no job-level override on static")
    return problems

GOOD_VERIFY = f"step gradle-repos {CHECK_CMD}\nstep gradle-repos-tests {TEST_CMD}\nif [ x ]; then\n  step unit-tests gradle test\nfi\n"
GOOD_CI = (
    "permissions:\n  contents: read\n\njobs:\n"
    "  static:\n    name: static\n    runs-on: ubuntu-latest\n    steps:\n"
    f"      - name: gradle repos tests\n        run: {TEST_CMD}\n"
    f"      - name: gradle repos\n        run: {CHECK_CMD}\n"
    "  python-lint:\n    name: python-lint\n    runs-on: ubuntu-latest\n    steps:\n      - run: echo hi\n"
)


class Wiring(unittest.TestCase):
    def test_real_wiring_is_complete(self):
        self.assertEqual(wiring_problems(read("scripts", "verify.sh"), read(".github", "workflows", "ci.yml")), [])

    def mutated(self, verify=(), ci=()):
        v, c = GOOD_VERIFY, GOOD_CI
        for old, new in verify:
            self.assertIn(old, v)
            v = v.replace(old, new)
        for old, new in ci:
            self.assertIn(old, c)
            c = c.replace(old, new)
        return wiring_problems(v, c)

    def test_good_synthetic_wiring_passes(self):
        self.assertEqual(wiring_problems(GOOD_VERIFY, GOOD_CI), [])

    def test_check_missing_from_ci(self):
        got = self.mutated(ci=[(f"        run: {CHECK_CMD}", "        run: echo skipped")])
        self.assertEqual(got, [f"ci.yml static job does not run `{CHECK_CMD}`"])

    def test_tests_missing_from_ci(self):
        got = self.mutated(ci=[(f"        run: {TEST_CMD}", "        run: echo skipped")])
        self.assertEqual(got, [f"ci.yml static job does not run `{TEST_CMD}`"])

    def test_check_in_the_wrong_ci_job_does_not_count(self):
        moved = [(f"        run: {CHECK_CMD}\n", ""), ("      - run: echo hi\n", f"      - run: {CHECK_CMD}\n")]
        got = self.mutated(ci=moved)
        self.assertIn(f"ci.yml static job does not run `{CHECK_CMD}`", got)

    def test_commented_out_step_in_ci_does_not_count(self):
        got = self.mutated(ci=[(f"        run: {CHECK_CMD}", f"        # run: {CHECK_CMD}")])
        self.assertIn(f"ci.yml static job does not run `{CHECK_CMD}`", got)

    def test_continue_on_error_is_flagged(self):
        got = self.mutated(ci=[("  static:\n    name: static\n", "  static:\n    name: static\n    continue-on-error: true\n")])
        self.assertIn("ci.yml static job has if: or continue-on-error", got)

    def test_or_true_after_the_check_does_not_count(self):
        got = self.mutated(ci=[(f"        run: {CHECK_CMD}", f"        run: {CHECK_CMD} || true")])
        self.assertEqual(got, [f"ci.yml static job does not run `{CHECK_CMD}`"])

    def test_step_level_if_is_flagged(self):
        got = self.mutated(ci=[(f"        run: {CHECK_CMD}", f"        if: false\n        run: {CHECK_CMD}")])
        self.assertEqual(got, ["ci.yml static job has if: or continue-on-error"])

    def test_step_starting_with_if_is_flagged(self):
        step = f"      - name: gradle repos\n        run: {CHECK_CMD}"
        got = self.mutated(ci=[(step, f"      - if: false\n        name: gradle repos\n        run: {CHECK_CMD}")])
        self.assertEqual(got, ["ci.yml static job has if: or continue-on-error"])

    def test_next_job_key_with_a_comment_still_ends_the_static_job(self):
        moved = [(f"      - name: gradle repos\n        run: {CHECK_CMD}\n", ""), ("  python-lint:\n", "  python-lint: # lint\n"),
                 ("      - run: echo hi\n", f"      - run: {CHECK_CMD}\n")]
        self.assertEqual(self.mutated(ci=moved), [f"ci.yml static job does not run `{CHECK_CMD}`"])

    def test_job_level_permissions_on_static_are_flagged(self):
        got = self.mutated(ci=[("  static:\n    name: static\n", "  static:\n    name: static\n    permissions:\n      contents: write\n")])
        self.assertTrue(any("permissions" in p for p in got), got)

    def test_wider_top_level_permissions_are_flagged(self):
        got = self.mutated(ci=[("permissions:\n  contents: read\n", "permissions:\n  contents: read\n  issues: write\n")])
        self.assertTrue(any("permissions" in p for p in got), got)

    def test_check_missing_from_verify(self):
        got = self.mutated(verify=[(f"step gradle-repos {CHECK_CMD}", "")])
        self.assertEqual(got, [f"verify.sh does not run `{CHECK_CMD}` as a top-level step"])

    def test_check_moved_into_the_fast_branch_is_flagged(self):
        got = self.mutated(verify=[(f"step gradle-repos {CHECK_CMD}", f"  step gradle-repos {CHECK_CMD}")])
        self.assertEqual(got, [f"verify.sh does not run `{CHECK_CMD}` as a top-level step"])

    def test_tests_missing_from_verify(self):
        got = self.mutated(verify=[(f"step gradle-repos-tests {TEST_CMD}", "")])
        self.assertEqual(got, [f"verify.sh does not run `{TEST_CMD}` as a top-level step"])


if __name__ == "__main__":
    unittest.main()
