package dk.bjarkebjarke.tally.architecture

import io.kotest.matchers.collections.shouldBeEmpty
import io.kotest.matchers.collections.shouldNotBeEmpty
import io.kotest.matchers.string.shouldContain
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
    fun rejectsEmLiteral() {
        violationsOf("val s = 1.em").shouldNotBeEmpty()
    }

    @Test
    fun rejectsFractionalEmLiteral() {
        violationsOf("val s = 0.5.em").shouldNotBeEmpty()
    }

    @Test
    fun rejectsEmFromIntVariable() {
        violationsOf("val n = 3\nval s = n.em").shouldNotBeEmpty()
    }

    @Test
    fun acceptsIdentifiersThatOnlyStartWithEm() {
        violationsOf("val a = item.emit()\nval b = list.empty\nval c = text.emoji\nval d = em").shouldBeEmpty()
    }

    @Test
    fun acceptsEmImportAndComment() {
        violationsOf("import androidx.compose.ui.unit.em\n// 2.em is wrong\nval a = 1").shouldBeEmpty()
    }

    @Test
    fun allowsEmInTheThemePackage() {
        violationsOf("val s = 2.em", "theme/Type.kt").shouldBeEmpty()
    }

    @Test
    fun rejectsColorWithNamedColorArgument() {
        violationsOf("val c = Color(color = 0xFF112233)").shouldNotBeEmpty()
    }

    @Test
    fun rejectsColorWithNamedValueArgument() {
        violationsOf("val c = Color(value = 0xFF112233uL)").shouldNotBeEmpty()
    }

    @Test
    fun rejectsColorWithNamedArgumentFromAVariable() {
        violationsOf("val n = 1\nval c = Color(color = n)").shouldNotBeEmpty()
    }

    @Test
    fun rejectsColorWhoseFirstNamedArgumentIsNotRed() {
        violationsOf("val c = Color(blue = 1f, red = 0f, green = 0f)").shouldNotBeEmpty()
        violationsOf("val c = Color(alpha = 1f, red = 0f, green = 0f, blue = 0f)").shouldNotBeEmpty()
    }

    @Test
    fun rejectsColorWhoseArgumentsStartOnTheNextLine() {
        violationsOf("val a = Color(\n    0xFF112233,\n)").shouldNotBeEmpty()
        violationsOf("val b = Color(\n    color = 0xFF112233,\n)").shouldNotBeEmpty()
        violationsOf("val c = Color(\n    red = 1f,\n    green = 0f,\n    blue = 0f,\n)").shouldNotBeEmpty()
    }

    @Test
    fun reportsTheLineWhereAMultiLineColorCallStarts() {
        violationsOf("val a = 1\nval c = Color(\n    0xFF112233,\n)").single().shouldContain(":4:")
    }

    @Test
    fun rejectsNamedColorConstants() {
        listOf("Red", "Green", "Blue", "Yellow", "Cyan", "Magenta", "Black", "White", "Gray", "LightGray", "DarkGray")
            .forEach { name -> violationsOf("val c = Color.$name").shouldNotBeEmpty() }
    }

    @Test
    fun rejectsNamedColorConstantWithItsPackage() {
        violationsOf("val c = androidx.compose.ui.graphics.Color.Red").shouldNotBeEmpty()
    }

    @Test
    fun acceptsTransparentAndUnspecifiedColorConstants() {
        violationsOf("val a = Color.Transparent\nval b = Color.Unspecified").shouldBeEmpty()
    }

    @Test
    fun acceptsNamesThatOnlyLookLikeColorCalls() {
        violationsOf(
            "val a = Color.Redwood\nval b = MyColor.Red\nval c = BrandColor(color = 1)\nval d = Color.Red2",
        ).shouldBeEmpty()
    }

    @Test
    fun allowsColorConstantsAndColorCallsInTheThemePackage() {
        violationsOf(
            "val a = Color.Red\nval b = Color(color = 1)\nval c = Color(\n    0xFF112233,\n)",
            "theme/Tokens.kt",
        ).shouldBeEmpty()
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
