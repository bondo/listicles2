package dk.bjarkebjarke.tally.domain

import io.kotest.core.spec.style.FunSpec
import io.kotest.matchers.shouldBe
import io.kotest.property.Arb
import io.kotest.property.arbitrary.Codepoint
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
            Validation.email(" \t\n ") shouldBe EmailError.Empty
        }

        test("email: whitespace-only strings always fail") {
            checkAll(Arb.string(0..20, Arb.int(0..0).map { Codepoint(0x20) })) { e ->
                Validation.email(e) shouldBe EmailError.Empty
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
            Validation.name("     ") shouldBe NameError.Empty
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
