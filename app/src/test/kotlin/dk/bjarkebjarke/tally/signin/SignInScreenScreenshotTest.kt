package dk.bjarkebjarke.tally.signin

import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.test.junit4.v2.createComposeRule
import androidx.compose.ui.test.onRoot
import androidx.compose.ui.unit.Density
import com.github.takahirom.roborazzi.captureRoboImage
import dk.bjarkebjarke.tally.ScreenshotOptions
import dk.bjarkebjarke.tally.TallyApp
import dk.bjarkebjarke.tally.domain.start.StartStep
import dk.bjarkebjarke.tally.start.StartUiState
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode

/**
 * M1-99 goldens of the sign-in screen (wireframe 01): light and dark in English and Danish, and one Danish light
 * golden at 200 % font scale, where the labels wrap. Rendered through TallyApp, as the app hosts the screen. Same small
 * fixed device as UpdateScreenScreenshotTest.
 */
@RunWith(RobolectricTestRunner::class)
@GraphicsMode(GraphicsMode.Mode.NATIVE)
class SignInScreenScreenshotTest {
    @get:Rule
    val compose = createComposeRule()

    @Test
    @Config(qualifiers = "en-$DEVICE")
    fun englishLight() = capture("SignInScreen_en_light.png") { TallyApp(SIGN_IN, darkTheme = false) }

    @Test
    @Config(qualifiers = "en-$DEVICE")
    fun englishDark() = capture("SignInScreen_en_dark.png") { TallyApp(SIGN_IN, darkTheme = true) }

    @Test
    @Config(qualifiers = "da-$DEVICE")
    fun danishLight() = capture("SignInScreen_da_light.png") { TallyApp(SIGN_IN, darkTheme = false) }

    @Test
    @Config(qualifiers = "da-$DEVICE")
    fun danishDark() = capture("SignInScreen_da_dark.png") { TallyApp(SIGN_IN, darkTheme = true) }

    @Test
    @Config(qualifiers = "da-$DEVICE")
    fun danishLightAt200PercentFontScale() =
        capture("SignInScreen_da_light_font200.png") {
            CompositionLocalProvider(
                LocalDensity provides Density(LocalDensity.current.density, fontScale = FONT_SCALE_200),
            ) {
                TallyApp(SIGN_IN, darkTheme = false)
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
        val SIGN_IN = StartUiState.Ready(StartStep.SignIn)
    }
}
