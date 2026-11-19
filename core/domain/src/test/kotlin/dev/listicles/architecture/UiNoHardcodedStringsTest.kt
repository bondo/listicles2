package dev.listicles.architecture

import io.kotest.matchers.collections.shouldBeEmpty
import io.kotest.matchers.collections.shouldNotBeEmpty
import io.kotest.matchers.string.shouldContain
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.io.TempDir
import java.io.File

class UiNoHardcodedStringsTest {
    @TempDir
    lateinit var dir: File

    private fun violationsOf(
        code: String,
        path: String = "ui/Screen.kt",
    ): List<String> {
        val file = File(dir, path)
        file.parentFile.mkdirs()
        file.writeText("package sample\n\n$code\n")
        return UiHardcodedStringRules.violations(dir)
    }

    @Test
    fun realUiSourcesHaveNoHardcodedStrings() {
        UiHardcodedStringRules.violations(File("../../app/src/main")).shouldBeEmpty()
    }

    @Test
    fun scansTheRealUiSources() {
        check(ArchitectureRules.scannedFileCount(File("../../app/src/main")) > 0) { "scanned nothing" }
    }

    @Test
    fun acceptsStringResources() {
        violationsOf("Text(stringResource(R.string.welcome))").shouldBeEmpty()
        violationsOf("Text(text = stringResource(R.string.welcome))").shouldBeEmpty()
        violationsOf("Icon(contentDescription = stringResource(R.string.add))").shouldBeEmpty()
    }

    @Test
    fun rejectsPositionalTextLiteral() {
        violationsOf("Text(\"Welcome\")").shouldNotBeEmpty()
    }

    @Test
    fun rejectsPositionalTextLiteralOnTheNextLine() {
        violationsOf("Text(\n    \"Welcome\",\n)").single().shouldContain(":3:")
    }

    @Test
    fun rejectsNamedTextLiteral() {
        violationsOf("Text(text = \"Welcome\", style = s)").shouldNotBeEmpty()
    }

    @Test
    fun rejectsNamedArgumentsOnTheNextLine() {
        violationsOf("Icon(\n    contentDescription =\n        \"Add\",\n)").shouldNotBeEmpty()
    }

    @Test
    fun rejectsEachUserVisibleNamedArgument() {
        listOf("text", "contentDescription", "label", "placeholder", "title", "message", "supportingText")
            .forEach { name -> violationsOf("Field($name = \"Hello there\")").shouldNotBeEmpty() }
    }

    @Test
    fun rejectsLiteralInsideALabelLambda() {
        violationsOf("OutlinedTextField(label = { Text(\"Name\") })").shouldNotBeEmpty()
    }

    @Test
    fun rejectsTemplateWithWords() {
        violationsOf("Text(\"Hello \$name\")").shouldNotBeEmpty()
    }

    @Test
    fun rejectsRawStringLiteral() {
        violationsOf("Text(\"\"\"Hello\"\"\")").shouldNotBeEmpty()
    }

    @Test
    fun rejectsSnackbarMessageLiteral() {
        violationsOf("snackbarHostState.showSnackbar(message = \"Saved\")").shouldNotBeEmpty()
    }

    @Test
    fun reportsTheOffendingLine() {
        violationsOf("val a = 1\nText(\"Hi\")").single().shouldContain("ui/Screen.kt:4:")
    }

    @Test
    fun acceptsTestTagsAndOtherNonVisibleLiterals() {
        violationsOf("Modifier.testTag(\"add_button\")").shouldBeEmpty()
        violationsOf("Log.d(\"Tag\", \"opened\")").shouldBeEmpty()
        violationsOf("val route = \"home/list\"").shouldBeEmpty()
        violationsOf("val title = \"Not a call argument\"").shouldBeEmpty()
        violationsOf("fun f(title: String = \"Default\") = Unit").shouldBeEmpty()
    }

    @Test
    fun acceptsEmptyAndSymbolOnlyLiterals() {
        violationsOf("Text(\"\")\nText(\"•\")\nText(text = \"-\")").shouldBeEmpty()
    }

    @Test
    fun acceptsNamesThatOnlyEndInText() {
        violationsOf("BasicText(\"x\")\nMyText(\"x\")\nsubtext(\"x\")\nfoo(subtitleText = \"x\")").shouldBeEmpty()
    }

    @Test
    fun acceptsLiteralsInCommentsAndStrings() {
        violationsOf("// Text(\"Welcome\")\n/* Text(\"Welcome\") */\nval s = \"Text(\\\"Welcome\\\")\"").shouldBeEmpty()
    }

    @Test
    fun rejectsLiteralInsideAStringTemplate() {
        violationsOf("val s = \"\${Text(\"Welcome\")}\"").shouldNotBeEmpty()
    }

    @Test
    fun acceptsLiteralsInPreviewFunctions() {
        violationsOf("@Preview\n@Composable\nprivate fun P() {\n    Text(\"Sample\")\n    Box { Text(\"Nested\") }\n}")
            .shouldBeEmpty()
    }

    @Test
    fun previewExemptionEndsWithThePreviewFunction() {
        violationsOf(
            "@Preview\n@Composable\nfun P() {\n    Text(\"Sample\")\n}\n\n" +
                "@Composable\nfun Q() {\n    Text(\"Real\")\n}",
        ).single()
            .shouldContain(":9:")
    }

    @Test
    fun allowsALiteralWithAJustification() {
        violationsOf("Text(\"WWW\") // justified: brand name is never translated").shouldBeEmpty()
    }

    @Test
    fun rejectsAShortOrMissingJustification() {
        violationsOf("Text(\"WWW\") // justified: brand").shouldNotBeEmpty()
        violationsOf("Text(\"WWW\") // justified:").shouldNotBeEmpty()
        violationsOf("Text(\"WWW\") // ok whatever").shouldNotBeEmpty()
        violationsOf("Text(\"WWW\") // justified: 1 2 3").shouldNotBeEmpty()
    }

    @Test
    fun aJustificationOnAnotherLineDoesNotAllowTheLiteral() {
        violationsOf("// justified: brand name is never translated\nText(\"WWW\")").shouldNotBeEmpty()
    }

    @Test
    fun scansEveryKotlinFileUnderTheDirectory() {
        File(dir, "a/b").mkdirs()
        File(dir, "a/b/Deep.kt").writeText("package sample\n\nval x = Text(\"Deep\")\n")
        UiHardcodedStringRules.violations(dir).single().shouldContain("a/b/Deep.kt:3:")
    }
}
