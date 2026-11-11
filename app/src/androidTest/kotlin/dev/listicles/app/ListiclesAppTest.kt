package dev.listicles.app

import androidx.compose.runtime.mutableStateOf
import androidx.compose.ui.graphics.luminance
import androidx.compose.ui.graphics.toPixelMap
import androidx.compose.ui.test.captureToImage
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.onRoot
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class ListiclesAppTest {
    @get:Rule
    val compose = createComposeRule()

    @Test
    fun showsWelcomeText() {
        val welcome = InstrumentationRegistry.getInstrumentation().targetContext.getString(R.string.welcome)
        compose.setContent { ListiclesApp() }
        compose.onNodeWithText(welcome).assertExists()
    }

    @Test
    fun showsWelcomeTextInDarkTheme() {
        val welcome = InstrumentationRegistry.getInstrumentation().targetContext.getString(R.string.welcome)
        compose.setContent { ListiclesApp(darkTheme = true) }
        compose.onNodeWithText(welcome).assertExists()
    }

    /** R9-09: unlike the text assertions above, this fails if the dark flag does not reach the rendered pixels. */
    @Test
    fun darkThemeRendersADarkBackgroundAndLightThemeALightOne() {
        val dark = mutableStateOf(true)
        compose.setContent { ListiclesApp(darkTheme = dark.value) }

        val darkLuminance = backgroundLuminance()
        dark.value = false
        compose.waitForIdle()
        val lightLuminance = backgroundLuminance()

        assertTrue("dark background luminance $darkLuminance should be below 0.2", darkLuminance < DARK_MAX)
        assertTrue("light background luminance $lightLuminance should be above 0.8", lightLuminance > LIGHT_MIN)
    }

    private fun backgroundLuminance(): Float {
        val pixels = compose.onRoot().captureToImage().toPixelMap()
        // The corner is Scaffold background, away from the centered text.
        return pixels[CORNER_PX, CORNER_PX].luminance()
    }

    private companion object {
        const val CORNER_PX = 2
        const val DARK_MAX = 0.2f
        const val LIGHT_MIN = 0.8f
    }
}
