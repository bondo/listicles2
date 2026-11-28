package dk.bjarkebjarke.tally

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.ColorScheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp

private const val RADIX_HEX = 16
private const val OPAQUE = 0xFF000000L

/** A token value without the leading #, e.g. rgb("006878"). */
private fun rgb(hex: String): Color = Color(hex.toLong(RADIX_HEX) or OPAQUE)

// Written by hand from design/tokens.json (Petrol, T1); ThemeTokensTest checks parity and WCAG AA contrast.
private val LightScheme =
    lightColorScheme(
        primary = rgb("006878"),
        onPrimary = rgb("FFFFFF"),
        primaryContainer = rgb("A7EDFF"),
        onPrimaryContainer = rgb("00212A"),
        secondary = rgb("516163"),
        onSecondary = rgb("FFFFFF"),
        secondaryContainer = rgb("D4E6E8"),
        onSecondaryContainer = rgb("0E1E20"),
        tertiary = rgb("7B5818"),
        onTertiary = rgb("FFFFFF"),
        tertiaryContainer = rgb("FFDEAE"),
        onTertiaryContainer = rgb("2D1600"),
        error = rgb("BA1A1A"),
        onError = rgb("FFFFFF"),
        errorContainer = rgb("FFDAD6"),
        onErrorContainer = rgb("410002"),
        surface = rgb("F6FAFB"),
        onSurface = rgb("181C1D"),
        onSurfaceVariant = rgb("3F484A"),
        surfaceContainerLowest = rgb("FFFFFF"),
        surfaceContainerLow = rgb("F0F4F5"),
        surfaceContainer = rgb("EBEEEF"),
        surfaceContainerHigh = rgb("E5E9EA"),
        surfaceContainerHighest = rgb("DFE3E4"),
        outline = rgb("6F797B"),
        outlineVariant = rgb("BFC8CA"),
        inverseSurface = rgb("2C3132"),
        inverseOnSurface = rgb("EDF1F2"),
        inversePrimary = rgb("7DD3E7"),
        scrim = rgb("000000"),
        background = rgb("F6FAFB"),
        onBackground = rgb("181C1D"),
        surfaceVariant = rgb("DBE4E6"),
        surfaceTint = rgb("006878"),
        surfaceBright = rgb("F6FAFB"),
        surfaceDim = rgb("D7DBDB"),
        primaryFixed = rgb("A7EDFF"),
        primaryFixedDim = rgb("7DD3E7"),
        onPrimaryFixed = rgb("00212A"),
        onPrimaryFixedVariant = rgb("004E5B"),
        secondaryFixed = rgb("D4E6E8"),
        secondaryFixedDim = rgb("B8CACC"),
        onSecondaryFixed = rgb("0E1E20"),
        onSecondaryFixedVariant = rgb("394A4B"),
        tertiaryFixed = rgb("FFDEAE"),
        tertiaryFixedDim = rgb("EEBF75"),
        onTertiaryFixed = rgb("2D1600"),
        onTertiaryFixedVariant = rgb("604100"),
    )

private val DarkScheme =
    darkColorScheme(
        primary = rgb("7DD3E7"),
        onPrimary = rgb("003742"),
        primaryContainer = rgb("004E5B"),
        onPrimaryContainer = rgb("A7EDFF"),
        secondary = rgb("B8CACC"),
        onSecondary = rgb("233335"),
        secondaryContainer = rgb("394A4B"),
        onSecondaryContainer = rgb("D4E6E8"),
        tertiary = rgb("EEBF75"),
        onTertiary = rgb("462B00"),
        tertiaryContainer = rgb("604100"),
        onTertiaryContainer = rgb("FFDEAE"),
        error = rgb("FFB4AB"),
        onError = rgb("690005"),
        errorContainer = rgb("93000A"),
        onErrorContainer = rgb("FFDAD6"),
        surface = rgb("0F1415"),
        onSurface = rgb("DFE3E4"),
        onSurfaceVariant = rgb("BFC8CA"),
        surfaceContainerLowest = rgb("0A0F10"),
        surfaceContainerLow = rgb("181C1D"),
        surfaceContainer = rgb("1C2021"),
        surfaceContainerHigh = rgb("262B2C"),
        surfaceContainerHighest = rgb("313636"),
        outline = rgb("899294"),
        outlineVariant = rgb("3F484A"),
        inverseSurface = rgb("DFE3E4"),
        inverseOnSurface = rgb("2C3132"),
        inversePrimary = rgb("006878"),
        scrim = rgb("000000"),
        background = rgb("0F1415"),
        onBackground = rgb("DFE3E4"),
        surfaceVariant = rgb("3F484A"),
        surfaceTint = rgb("7DD3E7"),
        surfaceBright = rgb("353A3B"),
        surfaceDim = rgb("0F1415"),
        primaryFixed = rgb("A7EDFF"),
        primaryFixedDim = rgb("7DD3E7"),
        onPrimaryFixed = rgb("00212A"),
        onPrimaryFixedVariant = rgb("004E5B"),
        secondaryFixed = rgb("D4E6E8"),
        secondaryFixedDim = rgb("B8CACC"),
        onSecondaryFixed = rgb("0E1E20"),
        onSecondaryFixedVariant = rgb("394A4B"),
        tertiaryFixed = rgb("FFDEAE"),
        tertiaryFixedDim = rgb("EEBF75"),
        onTertiaryFixed = rgb("2D1600"),
        onTertiaryFixedVariant = rgb("604100"),
    )

/** Static schemes (no dynamic color) so screenshots and contrast checks are deterministic. */
fun colorSchemeFor(darkTheme: Boolean): ColorScheme = if (darkTheme) DarkScheme else LightScheme

/**
 * Type scale (T2): the Material 3 defaults. The eight styles of tokens.json equal the defaults, and every other style
 * (display*, headlineLarge/Medium, titleSmall, labelSmall) is the Material 3 default too; ThemeTokensTest checks both.
 */
fun colorSchemeTypography(): Typography = Typography()

/** The spacing tokens of design/tokens.json in dp (ThemeTokensTest checks parity). */
object Spacing {
    val xxs = 2.dp
    val xs = 4.dp
    val s = 8.dp
    val m = 12.dp
    val l = 16.dp
    val xl = 24.dp
    val xxl = 32.dp
}

/** The size tokens of design/tokens.json in dp (ThemeTokensTest checks parity). */
object Sizes {
    val minTouchTarget = 48.dp
    val topAppBar = 64.dp
    val listRowMin = 56.dp
    val fab = 56.dp
    val icon = 24.dp
    val offlineBar = 32.dp
    val screenGutter = 16.dp
}

/** Wireframe 02's empty-state circle and its icon (`.bubble` in wireframes.html); not design tokens. */
val EmptyStateBubble = 96.dp
val EmptyStateIcon = 44.dp

/** Wireframe 01's `.logo` (72 dp, 20 dp corners) and `.btn .ms` (18 dp); not design tokens. */
val SignInMarkSize = 72.dp
val SignInMarkCorner = 20.dp
val SignInButtonIconSize = 18.dp

@Composable
fun TallyTheme(
    darkTheme: Boolean = isSystemInDarkTheme(),
    content: @Composable () -> Unit,
) {
    MaterialTheme(colorScheme = colorSchemeFor(darkTheme), typography = colorSchemeTypography(), content = content)
}
