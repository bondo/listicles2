package dk.bjarkebjarke.tally.signin

import androidx.activity.ComponentActivity
import androidx.compose.ui.test.getUnclippedBoundsInRoot
import androidx.compose.ui.test.junit4.v2.createAndroidComposeRule
import androidx.compose.ui.test.onNodeWithText
import androidx.core.graphics.Insets
import androidx.core.view.ViewCompat
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsCompat
import dk.bjarkebjarke.tally.TallyTheme
import io.kotest.matchers.shouldBe
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

/**
 * M1-16 (R1-01): the system bars' insets are applied once. The column is centred, so a status bar of [BAR_DP] moves the
 * heading down by half of it; padding twice would move it by all of it.
 */
@RunWith(RobolectricTestRunner::class)
@Config(qualifiers = "mdpi")
class SignInScreenInsetsTest {
    @get:Rule
    val compose = createAndroidComposeRule<ComponentActivity>()

    @Test
    fun aStatusBarMovesTheCentredColumnByHalfItsHeight() {
        WindowCompat.setDecorFitsSystemWindows(compose.activity.window, false)
        compose.setContent { TallyTheme(false) { SignInScreen(SignInUiState(), {}, {}, {}) } }
        val before =
            compose
                .onNodeWithText("Tally")
                .getUnclippedBoundsInRoot()
                .top.value

        compose.runOnUiThread {
            val bars =
                WindowInsetsCompat
                    .Builder()
                    .setInsets(
                        WindowInsetsCompat.Type.systemBars(),
                        Insets.of(0, BAR_DP, 0, 0),
                    ).build()
            ViewCompat.dispatchApplyWindowInsets(compose.activity.window.decorView, bars)
        }
        compose.waitForIdle()
        val after =
            compose
                .onNodeWithText("Tally")
                .getUnclippedBoundsInRoot()
                .top.value

        (after - before) shouldBe (BAR_DP / 2f)
    }

    private companion object {
        const val BAR_DP = 100
    }
}
