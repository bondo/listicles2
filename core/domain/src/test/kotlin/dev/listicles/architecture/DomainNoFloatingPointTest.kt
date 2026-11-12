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
}
