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

    @Test
    fun rejectsDpConstructor() {
        violationsOf("val p = Dp(16f)").shouldNotBeEmpty()
    }

    @Test
    fun rejectsTextUnitConstructor() {
        violationsOf("val s = TextUnit(14f, TextUnitType.Sp)").shouldNotBeEmpty()
    }

    @Test
    fun rejectsNamedArgumentColor() {
        violationsOf("val c = Color(red = 1f, green = 0f, blue = 0f)").shouldNotBeEmpty()
    }

    @Test
    fun rejectsDecimalLongColor() {
        violationsOf("val c = Color(4278190080)").shouldNotBeEmpty()
    }

    @Test
    fun rejectsDpFromIntVariable() {
        violationsOf("val n = 3\nval p = n.dp").shouldNotBeEmpty()
    }

    @Test
    fun rejectsSpFromIntVariable() {
        violationsOf("val n = 3\nval p = n.sp").shouldNotBeEmpty()
    }

    @Test
    fun rejectsRawValueInsideStringTemplate() {
        violationsOf("val t = \"\${16.dp}\"").shouldNotBeEmpty()
    }

    @Test
    fun acceptsDpAndSpImports() {
        violationsOf("import androidx.compose.ui.unit.dp\nimport androidx.compose.ui.unit.sp").shouldBeEmpty()
    }

    @Test
    fun acceptsColorFromTokensAndPlainDp() {
        violationsOf("val c = Color.Unspecified\nval d = Dp.Unspecified\nval v = dp").shouldBeEmpty()
    }

    @Test
    fun allowsDpFromVariableInTheme() {
        violationsOf("val p = n.dp\nval t = Dp(4f)", "theme/Tokens.kt").shouldBeEmpty()
    }

    @Test
    fun aCheckoutUnderAThemeDirectoryDoesNotExemptTheUi() {
        val nested = File(dir, "theme/project").also { it.mkdirs() }
        File(nested, "ui").mkdirs()
        File(nested, "ui/Screen.kt").writeText("package sample\n\nval p = 16.dp\n")
        ArchitectureRules.rawUiValueViolations(nested).shouldNotBeEmpty()
    }

    @Test
    fun themeDirectoryInsideTheScannedRootStillExempts() {
        val nested = File(dir, "theme/project").also { it.mkdirs() }
        File(nested, "theme").mkdirs()
        File(nested, "theme/Tokens.kt").writeText("package sample\n\nval p = 16.dp\n")
        ArchitectureRules.rawUiValueViolations(nested).shouldBeEmpty()
    }
}
