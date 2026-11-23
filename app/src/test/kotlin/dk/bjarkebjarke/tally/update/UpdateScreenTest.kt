package dk.bjarkebjarke.tally.update

import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.platform.UriHandler
import androidx.compose.ui.test.assertHasClickAction
import androidx.compose.ui.test.junit4.v2.createComposeRule
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import dk.bjarkebjarke.tally.TallyTheme
import io.kotest.matchers.shouldBe
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

/** M1-27 (START-01, wireframe 41): the full-screen "Update the app", in English and Danish. */
@RunWith(RobolectricTestRunner::class)
class UpdateScreenTest {
    @get:Rule
    val compose = createComposeRule()

    private val opened = mutableListOf<String>()
    private var uriHandler: UriHandler =
        object : UriHandler {
            override fun openUri(uri: String) {
                opened += uri
            }
        }

    private fun show() =
        compose.setContent {
            CompositionLocalProvider(LocalUriHandler provides uriHandler) { TallyTheme(false) { UpdateScreen() } }
        }

    @Test
    @Config(qualifiers = "en")
    fun english() {
        show()
        compose.onNodeWithText("Update the app").assertExists()
        compose
            .onNodeWithText(
                "This version of Tally is too old to work. Get the new version, then open it.",
            ).assertExists()
        compose.onNodeWithText("Opens the releases page on GitHub.").assertExists()
        compose.onNodeWithText("Get the update").assertHasClickAction()
    }

    @Test
    @Config(qualifiers = "da")
    fun danish() {
        show()
        compose.onNodeWithText("Opdater appen").assertExists()
        compose
            .onNodeWithText(
                "Denne version af Tally er for gammel til at virke. Hent den nye version, og åbn den.",
            ).assertExists()
        compose.onNodeWithText("Åbner siden med udgivelser på GitHub.").assertExists()
        compose.onNodeWithText("Hent opdateringen").assertHasClickAction()
    }

    @Test
    @Config(qualifiers = "en")
    fun theButtonOpensTheReleasesPage() {
        show()
        opened shouldBe emptyList()
        compose.onNodeWithText("Get the update").performClick()
        opened shouldBe listOf(RELEASES_URL)
        RELEASES_URL shouldBe "https://github.com/bondo/listicles2/releases"
    }

    /** R1-03: with no browser the handler throws IllegalArgumentException; the screen stays up instead of crashing. */
    @Test
    @Config(qualifiers = "en")
    fun noAppToOpenTheLinkDoesNotCrash() {
        uriHandler =
            object : UriHandler {
                override fun openUri(uri: String): Unit = throw IllegalArgumentException("No activity found")
            }
        show()
        compose.onNodeWithText("Get the update").performClick()
        compose.onNodeWithText("Update the app").assertExists()
    }
}
