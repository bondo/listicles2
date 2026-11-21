package dev.listicles.app

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.size
import androidx.compose.runtime.mutableStateOf
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.luminance
import androidx.compose.ui.graphics.toPixelMap
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.test.captureToImage
import androidx.compose.ui.test.junit4.accessibility.enableAccessibilityChecks
import androidx.compose.ui.test.junit4.v2.createComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.onRoot
import androidx.compose.ui.test.performClick
import androidx.compose.ui.unit.dp
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import dk.bjarkebjarke.tally.R
import dk.bjarkebjarke.tally.TallyApp
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class ListiclesAppTest {
    @get:Rule
    val compose = createComposeRule()

    /** P15: ATF checks (touch target size, contrast, labels) run before every action of every test in this class. */
    @Before
    fun enableChecks() {
        compose.enableAccessibilityChecks()
    }

    @Test
    fun showsWelcomeText() {
        val welcome = InstrumentationRegistry.getInstrumentation().targetContext.getString(R.string.welcome)
        compose.setContent { TallyApp() }
        compose.onNodeWithText(welcome).assertExists()
    }

    @Test
    fun showsWelcomeTextInDarkTheme() {
        val welcome = InstrumentationRegistry.getInstrumentation().targetContext.getString(R.string.welcome)
        compose.setContent { TallyApp(darkTheme = true) }
        compose.onNodeWithText(welcome).assertExists()
    }

    /** R9-09: unlike the text assertions above, this fails if the dark flag does not reach the rendered pixels. */
    @Test
    fun darkThemeRendersADarkBackgroundAndLightThemeALightOne() {
        val dark = mutableStateOf(true)
        compose.setContent { TallyApp(darkTheme = dark.value) }

        val darkLuminance = backgroundLuminance()
        dark.value = false
        compose.waitForIdle()
        val lightLuminance = backgroundLuminance()

        assertTrue("dark background luminance $darkLuminance should be below 0.2", darkLuminance < DARK_MAX)
        assertTrue("light background luminance $lightLuminance should be above 0.8", lightLuminance > LIGHT_MIN)
    }

    /** M1-03: proves the checks are live: a tiny unlabelled click target must fail, not pass silently. */
    @Test
    fun accessibilityChecksRejectATinyUnlabelledClickTarget() {
        compose.setContent {
            Box(Modifier.size(TINY_DP.dp).testTag(TAG).clickable { })
        }
        val failure = runCatching { compose.onNodeWithTag(TAG).performClick() }.exceptionOrNull()
        val message = "performClick passed on a tiny unlabelled target: the accessibility checks are not running"
        assertNotNull(message, failure)
    }

    private fun backgroundLuminance(): Float {
        val pixels = compose.onRoot().captureToImage().toPixelMap()
        // The corner is Scaffold background, away from the centered text.
        return pixels[CORNER_PX, CORNER_PX].luminance()
    }

    private companion object {
        const val TAG = "tiny-target"
        const val TINY_DP = 8
        const val CORNER_PX = 2
        const val DARK_MAX = 0.2f
        const val LIGHT_MIN = 0.8f
    }
}
