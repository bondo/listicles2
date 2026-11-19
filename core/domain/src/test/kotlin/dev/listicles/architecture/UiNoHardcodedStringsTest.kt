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
            .shouldContain(":11:")
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

    private val realText = "    Text(\"Real text\")"

    private fun realFunction() = "\n\n@Composable\nfun Real() {\n$realText\n}"

    @Test
    fun previewWithAPreviewParameterDoesNotExemptTheNextFunction() {
        violationsOf(
            "@Preview\n@Composable\nfun P(@PreviewParameter(Prov::class) s: String) {\n    Text(\"Sample\")\n}" +
                realFunction(),
        ).single().shouldContain("Real text")
    }

    @Test
    fun previewParameterAloneIsNotAPreviewExemption() {
        violationsOf("@Composable\nfun P(@PreviewParameter(Prov::class) s: String) {\n    Text(\"Sample\")\n}")
            .shouldNotBeEmpty()
    }

    @Test
    fun expressionBodyPreviewDoesNotExemptTheNextFunction() {
        violationsOf("@Preview\n@Composable\nfun P() = Sample()" + realFunction())
            .single()
            .shouldContain("Real text")
    }

    @Test
    fun multiPreviewAnnotationClassDoesNotExemptTheNextFunction() {
        violationsOf(
            "@Preview(name = \"Light\")\n@Preview(name = \"Dark\")\nannotation class ThemePreviews" + realFunction(),
        ).single().shouldContain("Real text")
    }

    @Test
    fun previewWithArgumentsAndAReturnTypeBodyIsStillExempt() {
        violationsOf(
            "@Preview(name = \"Dark\", showBackground = true)\n@Composable\nfun P(): Unit {\n    Text(\"Sample\")\n}",
        ).shouldBeEmpty()
    }

    @Test
    fun rejectsPositionalSnackbarMessage() {
        violationsOf("suspend fun f() {\n    host.showSnackbar(\"Item deleted\")\n}").shouldNotBeEmpty()
        violationsOf("suspend fun f() {\n    host.showSnackbar(stringResource(R.string.deleted))\n}").shouldBeEmpty()
    }

    @Test
    fun rejectsActionLabelOnClickLabelAndStateDescription() {
        violationsOf("host.showSnackbar(m, actionLabel = \"Undo\")").shouldNotBeEmpty()
        violationsOf("Modifier.clickable(onClickLabel = \"Open list\") {}").shouldNotBeEmpty()
        violationsOf("Modifier.toggleable(stateDescription = \"Selected item\")").shouldNotBeEmpty()
    }

    @Test
    fun rejectsPositionalContentDescriptionOfIconAndImage() {
        violationsOf("Icon(Icons.Filled.Add, \"Add item\")").shouldNotBeEmpty()
        violationsOf("Image(painter, \"Logo\")").shouldNotBeEmpty()
        violationsOf("Icon(Icons.Filled.Add, null)\nImage(painter, null)").shouldBeEmpty()
        violationsOf("Icon(Icons.Filled.Add, stringResource(R.string.add))").shouldBeEmpty()
        violationsOf("Icon(vector(\"a, b\", 1), null)").shouldBeEmpty()
    }

    @Test
    fun rejectsContentDescriptionAssignedInASemanticsBlock() {
        violationsOf("Box(Modifier.semantics { contentDescription = \"Add item\" })").shouldNotBeEmpty()
        violationsOf("Box(Modifier.semantics {\n    contentDescription = \"Add item\"\n})").shouldNotBeEmpty()
        violationsOf("Box(Modifier.semantics { stateDescription = \"Selected item\"; role = r })").shouldNotBeEmpty()
        violationsOf("Box(Modifier.semantics { contentDescription = stringResource(R.string.add) })").shouldBeEmpty()
    }

    @Test
    fun acceptsEscapeOnlyLiterals() {
        violationsOf("Text(\"\\u2022\")\nText(\"\\n\")\nText(\"\\t-\\\\\")").shouldBeEmpty()
        violationsOf("Text(\"\\nHello\")").shouldNotBeEmpty()
    }

    @Test
    fun acceptsLabelsOfAnimationApis() {
        listOf(
            """val a = animateFloatAsState(target, label = "alpha")""",
            """val a = animateColorAsState(c, animationSpec = spec, label = "color")""",
            """val t = updateTransition(state, label = "card")""",
            """val t = rememberInfiniteTransition(label = "pulse")""",
            """val v = animateValueAsState<Float>(x, converter, label = "value")""",
            """val f = transition.animateFloat(label = "fade") { 1 }""",
            "val a = animateDpAsState(\n    targetValue = d,\n    label = \"padding\",\n)",
            """AnimatedContent(state, label = "swap") { Text(stringResource(R.string.a)) }""",
            """AnimatedVisibility(visible, label = "show") {}""",
            """Crossfade(state, label = "fade") {}""",
        ).forEach { code -> violationsOf(code).shouldBeEmpty() }
    }

    @Test
    fun otherLabelsNearAnimationCallsAreStillRejected() {
        violationsOf("""OutlinedTextField(label = "Name")""").shouldNotBeEmpty()
        violationsOf("""Chip(onClick = animateIt(1), label = "Hello there")""").shouldNotBeEmpty()
        violationsOf("""Chip(modifier = Modifier.animate(label = "x"), label = "Hello there")""").shouldNotBeEmpty()
        violationsOf("""animateFloatAsState(target, contentDescription = "Add item")""").shouldNotBeEmpty()
        violationsOf("""val a = animated(label = "Hello there")""").shouldNotBeEmpty()
    }

    @Test
    fun builtInMultiPreviewsAreExempt() {
        listOf("PreviewLightDark", "PreviewScreenSizes", "PreviewFontScale", "PreviewDynamicColors").forEach { name ->
            violationsOf("@$name\n@Composable\nfun P() {\n    Text(\"Sample\")\n}").shouldBeEmpty()
        }
        violationsOf("@PreviewLightDarkX\n@Composable\nfun P() {\n    Text(\"Sample\")\n}").shouldNotBeEmpty()
    }

    @Test
    fun aBodylessPreviewDeclarationDoesNotExemptTheNextDeclaration() {
        violationsOf("@Preview\n@Composable\nfun P()" + realFunction()).single().shouldContain("Real text")
        violationsOf("@Preview\nfun P()\n\nclass K {\n    fun f() {\n$realText\n    }\n}")
            .single()
            .shouldContain("Real text")
    }
}
