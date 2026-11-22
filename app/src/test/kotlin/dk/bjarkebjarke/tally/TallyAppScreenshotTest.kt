package dk.bjarkebjarke.tally

import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.test.junit4.v2.createComposeRule
import androidx.compose.ui.test.onRoot
import androidx.compose.ui.unit.Density
import com.github.takahirom.roborazzi.captureRoboImage
import dk.bjarkebjarke.tally.start.StartRoute
import dk.bjarkebjarke.tally.start.StartUiState
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode

/**
 * M1-03 goldens of the TallyApp screen (since M1-60 the root on the M1 home, Q1 A): light and dark in English and
 * Danish, and one Danish light golden at 200 % font scale (owner decision Q3 A). The device is small and fixed so the
 * PNGs stay small (the guard allows 300 KB).
 * `scripts/screenshots.sh verify` compares against app/src/test/screenshots; a plain unit test run captures nothing.
 */
@RunWith(RobolectricTestRunner::class)
@GraphicsMode(GraphicsMode.Mode.NATIVE)
class TallyAppScreenshotTest {
    @get:Rule
    val compose = createComposeRule()

    @Test
    @Config(qualifiers = "en-$DEVICE")
    fun englishLight() = capture("TallyApp_en_light.png") { TallyApp(HOME, darkTheme = false) }

    @Test
    @Config(qualifiers = "en-$DEVICE")
    fun englishDark() = capture("TallyApp_en_dark.png") { TallyApp(HOME, darkTheme = true) }

    @Test
    @Config(qualifiers = "da-$DEVICE")
    fun danishLight() = capture("TallyApp_da_light.png") { TallyApp(HOME, darkTheme = false) }

    @Test
    @Config(qualifiers = "da-$DEVICE")
    fun danishDark() = capture("TallyApp_da_dark.png") { TallyApp(HOME, darkTheme = true) }

    @Test
    @Config(qualifiers = "da-$DEVICE")
    fun danishLightAt200PercentFontScale() =
        capture("TallyApp_da_light_font200.png") {
            CompositionLocalProvider(
                LocalDensity provides Density(LocalDensity.current.density, fontScale = FONT_SCALE_200),
            ) {
                TallyApp(HOME, darkTheme = false)
            }
        }

    private fun capture(
        fileName: String,
        content: @Composable () -> Unit,
    ) {
        compose.setContent(content)
        compose.onRoot().captureRoboImage("src/test/screenshots/$fileName", roborazziOptions = ScreenshotOptions.exact)
    }

    private companion object {
        const val DEVICE = "w360dp-h640dp-xhdpi"
        const val FONT_SCALE_200 = 2f
        val HOME = StartUiState.Ready(StartRoute.Home)
    }
}
