package dk.bjarkebjarke.tally.home

import androidx.compose.ui.test.assertHasClickAction
import androidx.compose.ui.test.junit4.v2.createComposeRule
import androidx.compose.ui.test.onNodeWithContentDescription
import androidx.compose.ui.test.performClick
import dk.bjarkebjarke.tally.TallyTheme
import io.kotest.matchers.shouldBe
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

/** M1-25 (wireframe 02): the home's avatar opens Account; with no Account to open there is no button. */
@RunWith(RobolectricTestRunner::class)
class HomeScreenAvatarTest {
    @get:Rule
    val compose = createComposeRule()

    private var opened = 0

    @Test
    @Config(qualifiers = "en")
    fun theAvatarOpensAccount() {
        compose.setContent { TallyTheme(false) { HomeScreen(avatarInitial = "S", onAccount = { opened++ }) } }
        compose.onNodeWithContentDescription("Account").assertHasClickAction()
        compose.onNodeWithContentDescription("Account").performClick()
        opened shouldBe 1
    }

    @Test
    @Config(qualifiers = "en")
    fun withoutAnAccountThereIsNoAvatarButton() {
        compose.setContent { TallyTheme(false) { HomeScreen() } }
        compose.onNodeWithContentDescription("Account").assertDoesNotExist()
    }
}
