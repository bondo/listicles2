package dk.bjarkebjarke.tally.domain

import io.kotest.core.spec.style.FunSpec
import io.kotest.matchers.shouldBe
import io.kotest.property.Arb
import io.kotest.property.arbitrary.Codepoint
import io.kotest.property.arbitrary.element
import io.kotest.property.arbitrary.filter
import io.kotest.property.arbitrary.int
import io.kotest.property.arbitrary.map
import io.kotest.property.arbitrary.string
import io.kotest.property.checkAll

private const val ASTRAL_END = 0x1F64F
private const val NON_BMP_NAME_LENGTH = 50

// Mixes BMP and non-BMP code points; never surrogates on their own.
private val anyCodePoints =
    Arb.int(0x20..ASTRAL_END).filter { it !in 0xD800..0xDFFF }.map { Codepoint(it) }

// Every char Kotlin's trim() and the spec count as whitespace: controls, Unicode spaces, line and paragraph separators.
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

private val visibleCores = Arb.string(1..50, anyCodePoints).filter { it.isNotBlank() && it == it.trim() }

private fun codePoints(s: String) = s.codePointCount(0, s.length)

private fun astral(n: Int) = "😀".repeat(n) // U+1F600, 2 UTF-16 chars each

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

        test("name: 1 to 50 code points after trimming passes") {
            checkAll(Arb.string(1..50, anyCodePoints).filter { it.isNotBlank() && it == it.trim() }) { n ->
                Validation.name(n) shouldBe null
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

        test("name: whitespace-only of any Unicode kind fails") {
            checkAll(whitespaceRuns) { n -> Validation.name(n) shouldBe NameError.Empty }
        }

        test("name: whitespace padding around 1 to 50 code points passes, 51 or more fails") {
            checkAll(whitespaceRuns, visibleCores, whitespaceRuns) { l, core, r ->
                Validation.name(l + core + r) shouldBe null
                Validation.name(l + core + astral(51 - codePoints(core)) + r) shouldBe NameError.TooLong
            }
        }

        test("name: the normalized value is exactly what was validated") {
            Validation.normalizedName("  \u3000Åse\t ") shouldBe "Åse"
            checkAll(whitespaceRuns, visibleCores, whitespaceRuns) { l, core, r ->
                val raw = l + core + r
                Validation.name(raw) shouldBe null
                Validation.normalizedName(raw) shouldBe core
            }
            checkAll(Arb.string(0..80, anyCodePoints)) { raw ->
                if (Validation.name(raw) == null) {
                    (codePoints(Validation.normalizedName(raw)) in 1..Validation.MAX_NAME_CODE_POINTS) shouldBe true
                }
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
