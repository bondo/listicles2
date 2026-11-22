package dk.bjarkebjarke.tally

import androidx.compose.material3.ColorScheme
import androidx.compose.material3.Typography
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.text.TextStyle
import io.kotest.matchers.collections.shouldBeEmpty
import io.kotest.matchers.shouldBe
import org.junit.jupiter.api.Test
import java.io.File
import kotlin.math.pow

/** M1-04 (P22): Theme.kt matches design/tokens.json, and every contrastPairs entry keeps its WCAG minimum. */
class ThemeTokensTest {
    private val tokens = obj(Json(File(tokensPath()).readText()).value())

    private fun colors(theme: String): Map<String, String> =
        obj(obj(tokens.getValue("color")).getValue(theme)).mapValues { it.value as String }

    private fun obj(v: Any?): Map<String, Any> =
        (v as Map<*, *>).entries.associate { (k, x) -> k as String to x as Any }

    private fun pairList(): List<Map<String, Any>> = (tokens.getValue("contrastPairs") as List<*>).map { obj(it) }

    private fun rolesOf(s: ColorScheme): Map<String, Color> =
        mapOf(
            "primary" to s.primary,
            "onPrimary" to s.onPrimary,
            "primaryContainer" to s.primaryContainer,
            "onPrimaryContainer" to s.onPrimaryContainer,
            "secondary" to s.secondary,
            "onSecondary" to s.onSecondary,
            "secondaryContainer" to s.secondaryContainer,
            "onSecondaryContainer" to s.onSecondaryContainer,
            "tertiary" to s.tertiary,
            "onTertiary" to s.onTertiary,
            "tertiaryContainer" to s.tertiaryContainer,
            "onTertiaryContainer" to s.onTertiaryContainer,
            "error" to s.error,
            "onError" to s.onError,
            "errorContainer" to s.errorContainer,
            "onErrorContainer" to s.onErrorContainer,
            "surface" to s.surface,
            "onSurface" to s.onSurface,
            "onSurfaceVariant" to s.onSurfaceVariant,
            "surfaceContainerLowest" to s.surfaceContainerLowest,
            "surfaceContainerLow" to s.surfaceContainerLow,
            "surfaceContainer" to s.surfaceContainer,
            "surfaceContainerHigh" to s.surfaceContainerHigh,
            "surfaceContainerHighest" to s.surfaceContainerHighest,
            "outline" to s.outline,
            "outlineVariant" to s.outlineVariant,
            "inverseSurface" to s.inverseSurface,
            "inverseOnSurface" to s.inverseOnSurface,
            "inversePrimary" to s.inversePrimary,
            "scrim" to s.scrim,
            "background" to s.background,
            "onBackground" to s.onBackground,
            "surfaceVariant" to s.surfaceVariant,
            "surfaceTint" to s.surfaceTint,
            "surfaceBright" to s.surfaceBright,
            "surfaceDim" to s.surfaceDim,
            "primaryFixed" to s.primaryFixed,
            "primaryFixedDim" to s.primaryFixedDim,
            "onPrimaryFixed" to s.onPrimaryFixed,
            "onPrimaryFixedVariant" to s.onPrimaryFixedVariant,
            "secondaryFixed" to s.secondaryFixed,
            "secondaryFixedDim" to s.secondaryFixedDim,
            "onSecondaryFixed" to s.onSecondaryFixed,
            "onSecondaryFixedVariant" to s.onSecondaryFixedVariant,
            "tertiaryFixed" to s.tertiaryFixed,
            "tertiaryFixedDim" to s.tertiaryFixedDim,
            "onTertiaryFixed" to s.onTertiaryFixed,
            "onTertiaryFixedVariant" to s.onTertiaryFixedVariant,
        )

    private fun hex(c: Color) = "#%06X".format(c.toArgb() and 0xFFFFFF)

    @Test
    fun everyTokenRoleIsAColorSchemeRoleAndViceVersa() {
        for (dark in listOf(false, true)) {
            val theme = if (dark) "dark" else "light"
            rolesOf(colorSchemeFor(dark)).keys shouldBe colors(theme).keys
        }
    }

    @Test
    fun themeColorsEqualTokens() {
        for (dark in listOf(false, true)) {
            val theme = if (dark) "dark" else "light"
            val actual = rolesOf(colorSchemeFor(dark)).mapValues { hex(it.value) }
            val diff = colors(theme).filter { (role, value) -> actual[role] != value }.keys
            diff.toList().shouldBeEmpty()
        }
    }

    @Test
    fun everyContrastPairKeepsItsMinimumInBothThemes() {
        val pairs = pairList()
        (pairs.size >= 26) shouldBe true
        val failures = mutableListOf<String>()
        for (dark in listOf(false, true)) {
            val s = rolesOf(colorSchemeFor(dark))
            for (p in pairs) {
                val ratio = contrast(s.getValue(p["fg"] as String), s.getValue(p["bg"] as String))
                if (ratio < (p["min"] as Number).toDouble()) failures += "${p["fg"]} on ${p["bg"]} dark=$dark: $ratio"
            }
        }
        failures.shouldBeEmpty()
    }

    @Test
    fun outlineIsGatedOnTheLowAndHighSurfaceContainers() {
        val pairs = pairList().map { it["fg"] to it["bg"] }
        (("outline" to "surfaceContainerLow") in pairs) shouldBe true
        (("outline" to "surfaceContainerHigh") in pairs) shouldBe true
    }

    /** M1-60: the Spacing and Sizes objects hold exactly the spacing and size tokens, in dp. */
    @Test
    fun spacingAndSizesMatchTokens() {
        for ((group, holder) in listOf("spacing" to Spacing, "size" to Sizes)) {
            val dps = holder.javaClass.declaredFields.filter { it.type == java.lang.Float.TYPE }
            val actual =
                dps.associate { f ->
                    f.isAccessible = true
                    f.name to f.getFloat(null)
                }
            actual shouldBe obj(tokens.getValue(group)).mapValues { (it.value as Number).toFloat() }
        }
    }

    @Test
    fun contrastFunctionMatchesWcagReferenceValues() {
        contrast(Color.Black, Color.White) shouldBe 21.0
        contrast(Color.White, Color.White) shouldBe 1.0
        (contrast(Color(0xFF777777), Color.White) < 4.5) shouldBe true // #777 is the classic AA failure on white
        (contrast(Color(0xFF767676), Color.White) >= 4.5) shouldBe true
    }

    @Test
    fun typographyMatchesTokensAndOtherStylesAreMaterialDefaults() {
        val t = colorSchemeTypography()
        val styles: Map<String, TextStyle> =
            mapOf(
                "headlineSmall" to t.headlineSmall,
                "titleLarge" to t.titleLarge,
                "titleMedium" to t.titleMedium,
                "bodyLarge" to t.bodyLarge,
                "bodyMedium" to t.bodyMedium,
                "bodySmall" to t.bodySmall,
                "labelLarge" to t.labelLarge,
                "labelMedium" to t.labelMedium,
            )
        val spec = obj(tokens.getValue("type")).mapValues { e -> obj(e.value).mapValues { it.value as Number } }
        spec.keys shouldBe styles.keys
        for ((name, style) in styles) {
            style.fontSize.value shouldBe spec.getValue(name).getValue("size").toFloat()
            style.lineHeight.value shouldBe spec.getValue(name).getValue("lineHeight").toFloat()
            style.fontWeight?.weight shouldBe spec.getValue(name).getValue("weight").toInt()
        }
        // Every style not in tokens.json (T2: Material 3 type scale) is the Material 3 default, unchanged (all 7).
        val d = Typography()
        val unlisted =
            listOf(
                Triple("displayLarge", t.displayLarge, d.displayLarge),
                Triple("displayMedium", t.displayMedium, d.displayMedium),
                Triple("displaySmall", t.displaySmall, d.displaySmall),
                Triple("headlineLarge", t.headlineLarge, d.headlineLarge),
                Triple("headlineMedium", t.headlineMedium, d.headlineMedium),
                Triple("titleSmall", t.titleSmall, d.titleSmall),
                Triple("labelSmall", t.labelSmall, d.labelSmall),
            )
        unlisted.filter { (name, _, _) -> name in spec.keys }.shouldBeEmpty()
        unlisted.filter { (_, actual, default) -> actual != default }.map { it.first }.shouldBeEmpty()
    }

    private fun contrast(
        a: Color,
        b: Color,
    ): Double {
        val (hi, lo) = listOf(lum(a), lum(b)).sortedDescending()
        return (hi + 0.05) / (lo + 0.05)
    }

    private fun lum(c: Color): Double {
        fun ch(v: Float): Double =
            v.toDouble().let {
                if (it <=
                    0.03928
                ) {
                    it / 12.92
                } else {
                    ((it + 0.055) / 1.055).pow(2.4)
                }
            }
        return 0.2126 * ch(c.red) + 0.7152 * ch(c.green) + 0.0722 * ch(c.blue)
    }

    private fun tokensPath(): String =
        checkNotNull(System.getProperty("tally.tokensFile")) { "tally.tokensFile is not set (app/build.gradle.kts)" }
}

/** Just enough JSON for design/tokens.json: objects, arrays, strings, numbers. */
private class Json(
    private val s: String,
) {
    private var i = 0

    fun value(): Any {
        ws()
        return when (val c = s[i]) {
            '{' -> {
                obj()
            }

            '[' -> {
                arr()
            }

            '"' -> {
                str()
            }

            else -> {
                check(c == '-' || c.isDigit()) { "bad JSON at $i" }
                num()
            }
        }
    }

    private fun ws() {
        while (s[i].isWhitespace()) i++
    }

    private fun obj(): Map<String, Any> {
        val m = LinkedHashMap<String, Any>()
        i++
        ws()
        if (s[i] == '}') {
            i++
            return m
        }
        while (true) {
            ws()
            val k = str()
            ws()
            check(s[i++] == ':')
            m[k] = value()
            ws()
            if (s[i++] == '}') return m
        }
    }

    private fun arr(): List<Any> {
        val l = mutableListOf<Any>()
        i++
        ws()
        if (s[i] == ']') {
            i++
            return l
        }
        while (true) {
            l += value()
            ws()
            if (s[i++] == ']') return l
        }
    }

    private fun str(): String {
        val b = StringBuilder()
        i++
        while (s[i] != '"') {
            if (s[i] == '\\') i++
            b.append(s[i++])
        }
        i++
        return b.toString()
    }

    private fun num(): Number {
        val st = i
        while (i < s.length && (s[i].isDigit() || s[i] in "-+.eE")) i++
        return s.substring(st, i).toDouble()
    }
}
