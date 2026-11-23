package dk.bjarkebjarke.tally.update

import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.test.junit4.v2.createComposeRule
import androidx.compose.ui.test.onRoot
import androidx.compose.ui.unit.Density
import com.github.takahirom.roborazzi.captureRoboImage
import dk.bjarkebjarke.tally.ScreenshotOptions
import dk.bjarkebjarke.tally.TallyTheme
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode

/**
 * M1-27 (R1-05) goldens of the "Update the app" screen: light and dark in English and Danish, and one Danish light
 * golden at 200 % font scale (owner decision Q3 A). Same small fixed device as TallyAppScreenshotTest.
 */
@RunWith(RobolectricTestRunner::class)
@GraphicsMode(GraphicsMode.Mode.NATIVE)
class UpdateScreenScreenshotTest {
    @get:Rule
    val compose = createComposeRule()

    @Test
    @Config(qualifiers = "en-$DEVICE")
    fun englishLight() = capture("UpdateScreen_en_light.png") { TallyTheme(false) { UpdateScreen() } }

    @Test
    @Config(qualifiers = "en-$DEVICE")
    fun englishDark() = capture("UpdateScreen_en_dark.png") { TallyTheme(true) { UpdateScreen() } }

    @Test
    @Config(qualifiers = "da-$DEVICE")
    fun danishLight() = capture("UpdateScreen_da_light.png") { TallyTheme(false) { UpdateScreen() } }

    @Test
    @Config(qualifiers = "da-$DEVICE")
    fun danishDark() = capture("UpdateScreen_da_dark.png") { TallyTheme(true) { UpdateScreen() } }

    @Test
    @Config(qualifiers = "da-$DEVICE")
    fun danishLightAt200PercentFontScale() =
        capture("UpdateScreen_da_light_font200.png") {
            CompositionLocalProvider(
                LocalDensity provides Density(LocalDensity.current.density, fontScale = FONT_SCALE_200),
            ) {
                TallyTheme(false) { UpdateScreen() }
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
    }
}
