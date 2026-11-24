package dk.bjarkebjarke.tally.domain

import io.kotest.core.spec.style.FunSpec
import io.kotest.matchers.collections.shouldBeEmpty
import io.kotest.matchers.shouldBe
import io.kotest.property.Arb
import io.kotest.property.arbitrary.Codepoint
import io.kotest.property.arbitrary.bind
import io.kotest.property.arbitrary.choice
import io.kotest.property.arbitrary.element
import io.kotest.property.arbitrary.filter
import io.kotest.property.arbitrary.int
import io.kotest.property.arbitrary.list
import io.kotest.property.arbitrary.map
import io.kotest.property.arbitrary.string
import io.kotest.property.checkAll

private const val ASTRAL_END = 0x1F64F
private const val NON_BMP_NAME_LENGTH = 50

// Mixes BMP and non-BMP code points; never surrogates on their own.
private val anyCodePoints =
    Arb.int(0x20..ASTRAL_END).filter { it !in 0xD800..0xDFFF }.map { Codepoint(it) }

// Every char Kotlin's trim() counts as whitespace, which the email is trimmed of: controls, Unicode spaces, line and
// paragraph separators.
private val whitespaceChars =
    listOf(
        '\t',
        '\n',
        '\u000B',
        '\u000C',
        '\r',
        '\u001C',
        '\u001D',
        '\u001E',
        '\u001F',
        ' ',
        '\u00A0',
        '\u1680',
        '\u2000',
        '\u2001',
        '\u2002',
        '\u2003',
        '\u2004',
        '\u2005',
        '\u2006',
        '\u2007',
        '\u2008',
        '\u2009',
        '\u200A',
        '\u2028',
        '\u2029',
        '\u202F',
        '\u205F',
        '\u3000',
    )

private val whitespaceRuns = Arb.string(0..20, Arb.element(whitespaceChars).map { Codepoint(it.code) })

// The blank code points of a name (PLAN 3.1 P4, M1-90): U+0000 to U+0020, which the rules' trim() strips, and
// Unicode White_Space. The rules' validName lists the same ones (firebase/test/names.test.ts checks them there).
private val blankCodePoints =
    (0x0..0x20) + listOf(0x85, 0xA0, 0x1680) + (0x2000..0x200A) + listOf(0x2028, 0x2029, 0x202F, 0x205F, 0x3000)
private val blank = blankCodePoints.toSet()

// Java's regex knows the Unicode White_Space property, so it checks the list above independently.
private val unicodeWhiteSpace = Regex("\\p{IsWhite_Space}")

private val blankRuns = Arb.string(0..20, Arb.element(blankCodePoints).map { Codepoint(it) })

// Any code point that is not blank and not a lone surrogate: BMP and non-BMP, other controls included.
private val visibleCodePoints =
    Arb.int(0x0..ASTRAL_END).filter { it !in 0xD800..0xDFFF && it !in blank }.map { Codepoint(it) }

// What a user may type: blank and visible code points, half and half.
private val typedCodePoints = Arb.choice(Arb.element(blankCodePoints).map { Codepoint(it) }, visibleCodePoints)

// 1 to 50 code points with a visible one at each end and anything between.
private val visibleCores =
    Arb.choice(
        visibleCodePoints.map { text(it.value) },
        Arb.bind(visibleCodePoints, Arb.list(typedCodePoints, 0..48), visibleCodePoints) { first, between, last ->
            (listOf(first) + between + last).joinToString("") { text(it.value) }
        },
    )

private fun text(codePoint: Int) = String(Character.toChars(codePoint))

private fun codePoints(s: String) = s.codePointCount(0, s.length)

private fun astral(n: Int) = "😀".repeat(n) // U+1F600, 2 UTF-16 chars each

// The rules' validName (PLAN 3.1 P4) on the saved value: 1 to 50 code points, not all of them blank.
private fun rulesAccept(saved: String) =
    codePoints(saved) in 1..Validation.MAX_NAME_CODE_POINTS && saved.codePoints().anyMatch { it !in blank }

// The code points of all of Unicode for which `wrong` holds; any is a failure.
private fun everyCodePointWhere(wrong: (Int) -> Boolean): List<String> =
    (0..Character.MAX_CODE_POINT).filter(wrong).map { "U+%04X".format(it) }

class ValidationTest :
    FunSpec({
        test("password: any string of 12 or more code points passes") {
            checkAll(Arb.string(12..60, anyCodePoints)) { p ->
                Validation.password(p) shouldBe null
            }
        }

        test("password: any string shorter than 12 code points fails") {
            checkAll(Arb.string(0..11, anyCodePoints)) { p ->
                Validation.password(p) shouldBe PasswordError.TooShort
            }
        }

        test("password: counts code points, not UTF-16 chars") {
            Validation.password(astral(6)) shouldBe PasswordError.TooShort // 12 chars, 6 code points
            Validation.password(astral(11)) shouldBe PasswordError.TooShort
            Validation.password(astral(12)) shouldBe null
            Validation.password("a".repeat(11)) shouldBe PasswordError.TooShort
            Validation.password("a".repeat(12)) shouldBe null
        }

        test("password: spaces count and nothing else is required") {
            Validation.password(" ".repeat(12)) shouldBe null
            Validation.password("aaaaaaaaaaaa") shouldBe null
        }

        test("email: blank or empty fails") {
            Validation.email("") shouldBe EmailError.Empty
            Validation.email(" \t\n\u00A0") shouldBe EmailError.Empty
        }

        test("email: whitespace-only strings of any Unicode kind always fail") {
            checkAll(whitespaceRuns) { e ->
                Validation.email(e) shouldBe EmailError.Empty
            }
        }

        test("email: whitespace around a visible address is trimmed away") {
            checkAll(whitespaceRuns, whitespaceRuns) { l, r ->
                Validation.email("${l}me@example.com$r") shouldBe null
                Validation.normalizedEmail("${l}me@example.com$r") shouldBe "me@example.com"
            }
        }

        test("email: anything with a visible character passes, Firebase decides validity") {
            Validation.email("a") shouldBe null
            Validation.email("  me@example.com ") shouldBe null
            Validation.email("not-an-email") shouldBe null
        }

        test("email: trimmed form is what is submitted") {
            Validation.normalizedEmail("  me@example.com\n") shouldBe "me@example.com"
        }

        test("name: the blank code points are U+0000 to U+0020 and Unicode White_Space, no others") {
            blank.size shouldBe 52
            everyCodePointWhere { (it <= 0x20 || unicodeWhiteSpace.matches(text(it))) != (it in blank) }.shouldBeEmpty()
        }

        test("name: a name of one code point is empty exactly when that code point is blank, in all of Unicode") {
            everyCodePointWhere { (Validation.name(text(it)) == NameError.Empty) != (it in blank) }.shouldBeEmpty()
        }

        test("name: exactly the blank code points are trimmed from either end, in all of Unicode") {
            everyCodePointWhere { (Validation.normalizedName(text(it) + "a" + text(it)) == "a") != (it in blank) }
                .shouldBeEmpty()
        }

        test("name: 1 to 50 code points with a visible one at each end pass") {
            checkAll(visibleCores) { n ->
                Validation.name(n) shouldBe null
                Validation.normalizedName(n) shouldBe n
            }
        }

        test("name: a 50-code-point name with non-BMP characters passes") {
            val n = astral(NON_BMP_NAME_LENGTH)
            codePoints(n) shouldBe NON_BMP_NAME_LENGTH
            n.length shouldBe NON_BMP_NAME_LENGTH * 2
            Validation.name(n) shouldBe null
        }

        test("name: 51 code points fails") {
            Validation.name(astral(51)) shouldBe NameError.TooLong
            Validation.name("a".repeat(51)) shouldBe NameError.TooLong
            Validation.name("a".repeat(50)) shouldBe null
        }

        test("name: empty or spaces only fails") {
            Validation.name("") shouldBe NameError.Empty
            Validation.name("   \u00A0 ") shouldBe NameError.Empty
        }

        // M1-90: Kotlin's trim() kept U+0000 to U+0008, U+000E to U+001B and U+0085, which the rules count as blank.
        test("name: control characters and NEL count as blank, a zero-width space does not") {
            Validation.name("\u0001") shouldBe NameError.Empty
            Validation.name("\u0085") shouldBe NameError.Empty
            Validation.name("\u0001\u3000\u0008") shouldBe NameError.Empty
            Validation.normalizedName("\u0001\u3000Åse\u0085\u001B") shouldBe "Åse"
            Validation.normalizedName(" Ann\u0001Lee\u00A0") shouldBe "Ann\u0001Lee"
            Validation.name("\u200B") shouldBe null
        }

        test("name: blank code points only, of any kind, fail") {
            checkAll(blankRuns) { n -> Validation.name(n) shouldBe NameError.Empty }
        }

        test("name: blank padding around 1 to 50 code points passes and is trimmed away, 51 or more fails") {
            checkAll(blankRuns, visibleCores, blankRuns) { l, core, r ->
                Validation.name(l + core + r) shouldBe null
                Validation.normalizedName(l + core + r) shouldBe core
                Validation.name(l + core + astral(51 - codePoints(core)) + r) shouldBe NameError.TooLong
            }
        }

        test("name: the app accepts a name exactly when the rules accept the value it saves") {
            Validation.normalizedName("  \u3000Åse\t ") shouldBe "Åse"
            checkAll(Arb.string(0..80, typedCodePoints)) { raw ->
                val saved = Validation.normalizedName(raw)
                (Validation.name(raw) == null) shouldBe rulesAccept(saved)
                (Validation.name(raw) == NameError.Empty) shouldBe raw.codePoints().allMatch { it in blank }
                Validation.normalizedName(saved) shouldBe saved
            }
        }

        test("name: surrounding spaces are not counted") {
            Validation.name("  " + "a".repeat(50) + "  ") shouldBe null
            Validation.name("  " + "a".repeat(51) + "  ") shouldBe NameError.TooLong
        }

        test("limits are the documented numbers") {
            Validation.MIN_PASSWORD_CODE_POINTS shouldBe 12
            Validation.MAX_NAME_CODE_POINTS shouldBe 50
        }
    })
