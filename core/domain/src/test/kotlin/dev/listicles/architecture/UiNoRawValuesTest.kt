package dev.listicles.architecture

import io.kotest.matchers.collections.shouldBeEmpty
import io.kotest.matchers.collections.shouldNotBeEmpty
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.io.TempDir
import java.io.File

class UiNoRawValuesTest {
    @TempDir
    lateinit var dir: File

    private fun violationsOf(
        code: String,
        path: String = "ui/Screen.kt",
    ): List<String> {
        val file = File(dir, path)
        file.parentFile.mkdirs()
        file.writeText("package sample\n\n$code\n")
        return ArchitectureRules.rawUiValueViolations(dir)
    }

    @Test
    fun realUiSourcesHaveNoRawValues() {
        ArchitectureRules.rawUiValueViolations(File("../../app/src/main")).shouldBeEmpty()
    }

    @Test
    fun scansTheRealUiSources() {
        check(ArchitectureRules.scannedFileCount(File("../../app/src/main")) > 0) { "scanned nothing" }
    }

    @Test
    fun tokenUsageIsAccepted() {
        violationsOf("val c = MaterialTheme.colorScheme.primary\nval p = Spacing.medium").shouldBeEmpty()
    }

    @Test
    fun rejectsRawHexColor() {
        violationsOf("val c = Color(0xFF112233)").shouldNotBeEmpty()
    }

    @Test
    fun rejectsRawDpLiteral() {
        violationsOf("val p = 16.dp").shouldNotBeEmpty()
    }

    @Test
    fun rejectsRawSpLiteral() {
        violationsOf("val s = 14.sp").shouldNotBeEmpty()
    }

    @Test
    fun rejectsFractionalDpLiteral() {
        violationsOf("val p = 0.5.dp").shouldNotBeEmpty()
    }

    @Test
    fun allowsRawValuesInThemePackage() {
        violationsOf("val c = Color(0xFF112233)\nval p = 16.dp", "theme/Tokens.kt").shouldBeEmpty()
    }

    @Test
    fun allowsRawValuesInThemeFile() {
        violationsOf("val p = 16.dp", "Theme.kt").shouldBeEmpty()
    }

    @Test
    fun dpInCommentsIsAccepted() {
        violationsOf("// 16.dp is wrong\nval a = 1").shouldBeEmpty()
    }
}
