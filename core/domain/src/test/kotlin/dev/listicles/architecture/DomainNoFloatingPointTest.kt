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

    @Test
    fun rejectsNullSafeConversionToFloatingPoint() {
        violationsOf("val x = \"1.5\".toDoubleOrNull()").shouldNotBeEmpty()
        violationsOf("val y = s.toFloatOrNull() ?: 0").shouldNotBeEmpty()
    }

    @Test
    fun rejectsBigDecimalInAnyForm() {
        violationsOf("val x = \"1\".toBigDecimal()").shouldNotBeEmpty()
        violationsOf("val x = s.toBigDecimalOrNull()").shouldNotBeEmpty()
        violationsOf("val x = BigDecimal(\"1.5\")").shouldNotBeEmpty()
        violationsOf("val x: BigDecimal? = null").shouldNotBeEmpty()
        violationsOf("import java.math.BigDecimal").shouldNotBeEmpty()
        violationsOf("val x = java.math.BigDecimal.ONE").shouldNotBeEmpty()
    }

    @Test
    fun acceptsBigIntegerBecauseItIsWholeNumber() {
        violationsOf("import java.math.BigInteger\nval x = BigInteger.ONE + \"2\".toBigInteger()").shouldBeEmpty()
    }

    @Test
    fun acceptsIdentifiersThatMerelyContainTheForbiddenWords() {
        violationsOf(
            "val bigDecimalCount = 1\nfun toBigDecimalish() = 1\nclass MyBigDecimal\n" +
                "val toDoubleOrNullable = 2\nfun a(s: String) = s.toDoubleOrNullish()\n" +
                "val doubleOrNull = 3\nfun toFloatOrNullCount() = 4",
        ).shouldBeEmpty()
    }

    @Test
    fun wholeNumberParsingIsAccepted() {
        violationsOf("val x = \"12\".toLongOrNull() ?: \"3\".toIntOrNull() ?: 0").shouldBeEmpty()
    }

    @Test
    fun rejectsFloatingConversionsWithoutALeadingDot() {
        violationsOf("val x = listOf(\"1\").mapNotNull(String::toDoubleOrNull)").shouldNotBeEmpty()
        violationsOf("val x = listOf(\"1\").mapNotNull(String::toFloatOrNull)").shouldNotBeEmpty()
        violationsOf("val x = listOf(1).map(Int::toDouble)").shouldNotBeEmpty()
        violationsOf("val x = listOf(1).map(Int::toFloat)").shouldNotBeEmpty()
        violationsOf("val x = with(\"1\") { toDoubleOrNull() }").shouldNotBeEmpty()
    }

    @Test
    fun rejectsFloatingArraysStreamsAndRandomHelpers() {
        violationsOf("val x = DoubleArray(3)").shouldNotBeEmpty()
        violationsOf("val x = FloatArray(3)").shouldNotBeEmpty()
        violationsOf("val x = doubleArrayOf(1)").shouldNotBeEmpty()
        violationsOf("val x = floatArrayOf(1)").shouldNotBeEmpty()
        violationsOf("val x = listOf(1).toDoubleArray()").shouldNotBeEmpty()
        violationsOf("val x = listOf(1).stream().mapToDouble { it * 1 }.sum()").shouldNotBeEmpty()
        violationsOf("val x = s.asDoubleStream()").shouldNotBeEmpty()
        violationsOf("val x: DoubleStream? = null").shouldNotBeEmpty()
        violationsOf("val x = java.util.Random().nextGaussian()").shouldNotBeEmpty()
        violationsOf("val x: OptionalDouble? = null").shouldNotBeEmpty()
    }

    @Test
    fun acceptsWholeNumberArraysStreamsAndLookAlikes() {
        violationsOf(
            "val a = IntArray(3)\nval b = LongArray(3)\nval c = intArrayOf(1)\nval d = s.mapToInt { it }\n" +
                "val e = s.mapToLong { it }\nval doubleArrayCount = 1\nclass MyDoubleArray\n" +
                "fun mapToDoubleish() = 1\n" +
                "fun nextGaussianish() = 1",
        ).shouldBeEmpty()
    }

    @Test
    fun rejectsLessCommonDoubleReturningNames() {
        violationsOf("val x = s.flatMapToDouble(f)").shouldNotBeEmpty()
        violationsOf("val x = items.sumByDouble(Item::weight)").shouldNotBeEmpty()
        violationsOf("val x: DoubleSummaryStatistics? = null").shouldNotBeEmpty()
        violationsOf("val x = DoubleAdder()").shouldNotBeEmpty()
        violationsOf("val x = DoubleAccumulator(f, 0)").shouldNotBeEmpty()
    }

    @Test
    fun acceptsLookAlikesOfLessCommonDoubleNames() {
        violationsOf(
            "fun sumByDoubleish() = 1\nclass MyDoubleAdder\nval flatMapToDoubles = 2\n" +
                "val averageCount = 3\nval x = s.summaryStatistics().max",
        ).shouldBeEmpty()
    }
}
