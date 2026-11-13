package dev.listicles.architecture

import io.kotest.matchers.collections.shouldBeEmpty
import io.kotest.matchers.collections.shouldNotBeEmpty
import io.kotest.matchers.string.shouldContain
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.io.TempDir
import java.io.File

class DomainNoFloatingPointTest {
    @TempDir
    lateinit var dir: File

    private fun violationsOf(code: String): List<String> {
        File(dir, "Sample.kt").writeText("package sample\n\n$code\n")
        return ArchitectureRules.floatingPointViolations(dir)
    }

    @Test
    fun realDomainSourcesHaveNoFloatingPoint() {
        ArchitectureRules.floatingPointViolations(File("src/main")).shouldBeEmpty()
    }

    @Test
    fun scansTheRealDomainSources() {
        // Guards against the rule silently scanning nothing (wrong working directory).
        ArchitectureRules.scannedFileCount(File("src/main")).let { check(it > 0) { "scanned $it files" } }
    }

    @Test
    fun wholeNumberCodeIsAccepted() {
        violationsOf("fun f(a: Int, b: Long): Long = kotlin.math.abs(a) + b * 0x1f + 1_000L").shouldBeEmpty()
    }

    @Test
    fun floatAndDoubleInCommentsAndStringsAreAccepted() {
        violationsOf("// a Double here\n/* Float */\nval s = \"1.5 Double\"").shouldBeEmpty()
    }

    @Test
    fun rejectsDoubleType() {
        violationsOf("val x: Double = 0").shouldNotBeEmpty()
    }

    @Test
    fun rejectsFloatType() {
        violationsOf("fun f(x: Float) = x").shouldNotBeEmpty()
    }

    @Test
    fun rejectsNullableFloatingTypes() {
        violationsOf("val x: Double? = null").shouldNotBeEmpty()
    }

    @Test
    fun rejectsDecimalLiteral() {
        violationsOf("val x = 1.5").shouldNotBeEmpty()
    }

    @Test
    fun rejectsFloatSuffixLiteral() {
        violationsOf("val x = 2f").shouldNotBeEmpty()
    }

    @Test
    fun rejectsExponentLiteral() {
        violationsOf("val x = 1e3").shouldNotBeEmpty()
    }

    @Test
    fun rejectsConversionToFloatingPoint() {
        violationsOf("val x = 3.toDouble()").shouldNotBeEmpty()
    }

    @Test
    fun rejectsFloatingKotlinMathImport() {
        violationsOf("import kotlin.math.sqrt").shouldNotBeEmpty()
    }

    @Test
    fun rejectsKotlinMathWildcardImport() {
        violationsOf("import kotlin.math.*").shouldNotBeEmpty()
    }

    @Test
    fun rejectsFullyQualifiedKotlinMathCall() {
        violationsOf("val x = kotlin.math.floor(1)").shouldNotBeEmpty()
    }

    @Test
    fun reportsFileAndLine() {
        violationsOf("val ok = 1\nval x: Double = 0").single().let {
            it shouldContain "Sample.kt:4"
        }
    }

    @Test
    fun rejectsExponentWithFloatSuffix() {
        violationsOf("val x = 1e3f").shouldNotBeEmpty()
    }

    @Test
    fun rejectsDecimalExponentLiteral() {
        violationsOf("val x = 1.5e-3").shouldNotBeEmpty()
    }

    @Test
    fun rejectsLeadingDotLiteral() {
        violationsOf("val x = .5").shouldNotBeEmpty()
    }

    @Test
    fun rejectsUnderscoredFloatSuffixLiteral() {
        violationsOf("val x = 1_0f").shouldNotBeEmpty()
    }

    @Test
    fun rejectsLiteralInsideStringTemplate() {
        violationsOf("val s = \"value \${1.5}\"").shouldNotBeEmpty()
    }

    @Test
    fun rejectsTypeInsideStringTemplate() {
        violationsOf("val s = \"value \${3.toDouble()}\"").shouldNotBeEmpty()
    }

    @Test
    fun rejectsLiteralInsideTemplateInsideRawString() {
        violationsOf("val s = \"\"\"a \${2.5} b\"\"\"").shouldNotBeEmpty()
    }

    @Test
    fun rejectsLiteralAfterNestedStringInTemplate() {
        violationsOf("val s = \"a \${listOf(\"}\").size + 2.5} b\"").shouldNotBeEmpty()
    }

    @Test
    fun rejectsAverage() {
        violationsOf("val x = listOf(1, 2).average()").shouldNotBeEmpty()
    }

    @Test
    fun rejectsJavaLangMath() {
        violationsOf("val x = java.lang.Math.PI").shouldNotBeEmpty()
    }

    @Test
    fun rejectsStrictMathAndBareMath() {
        violationsOf("val x = StrictMath.sqrt(1)").shouldNotBeEmpty()
        violationsOf("val x = Math.abs(1)").shouldNotBeEmpty()
    }

    @Test
    fun rejectsRandomFloatingPointHelpers() {
        violationsOf("val x = kotlin.random.Random.nextDouble()").shouldNotBeEmpty()
    }

    @Test
    fun rejectsAliasedFloatingKotlinMathImport() {
        violationsOf("import kotlin.math.sqrt as root").shouldNotBeEmpty()
    }

    @Test
    fun acceptsHexLiteralsThatLookLikeExponents() {
        violationsOf("val x = 0x1e3 + 0xE3L + 0xFF").shouldBeEmpty()
    }

    @Test
    fun acceptsRangesAndMemberAccessThatLookLikeDecimals() {
        violationsOf("val r = 1..5\nval q = (0..9).map { it }\nval l = listOf(1, 2).first()").shouldBeEmpty()
    }

    @Test
    fun acceptsPlainStringTemplates() {
        violationsOf("val s = \"total \${1 + 2} and \$name\"").shouldBeEmpty()
    }

    @Test
    fun acceptsFloatInNestedBlockCommentsAndRawStrings() {
        violationsOf("/* a /* 1.5 */ still comment 2.5 */\nval s = \"\"\"1.5 Double\"\"\"").shouldBeEmpty()
    }

    @Test
    fun acceptsQuoteCharLiteral() {
        violationsOf("val q = '\"'\nval n = 1").shouldBeEmpty()
    }

    @Test
    fun keepsLineNumbersAcrossMultilineStringsAndComments() {
        violationsOf("val s = \"\"\"\nline\n\"\"\"\n/* \n */\nval x: Double = 0").single() shouldContain "Sample.kt:8"
    }

    @Test
    fun aCheckoutUnderAnyDirectoryNameStillScansEverything() {
        val nested = File(dir, "theme/project").also { it.mkdirs() }
        File(nested, "Sample.kt").writeText("package sample\n\nval x: Double = 0\n")
        ArchitectureRules.floatingPointViolations(nested).shouldNotBeEmpty()
    }
}
