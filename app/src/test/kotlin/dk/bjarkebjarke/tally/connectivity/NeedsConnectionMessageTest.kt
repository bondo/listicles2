package dk.bjarkebjarke.tally.connectivity

import androidx.compose.material3.Text
import androidx.compose.ui.test.junit4.v2.createComposeRule
import androidx.compose.ui.test.onNodeWithText
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

/** M1-30 (SYNC-03): the one message for an action that needs a connection, in English and Danish (wireframes text). */
@RunWith(RobolectricTestRunner::class)
class NeedsConnectionMessageTest {
    @get:Rule
    val compose = createComposeRule()

    @Test
    @Config(qualifiers = "en")
    fun english() {
        compose.setContent { Text(needsConnectionMessage()) }
        compose.onNodeWithText("This needs a connection").assertExists()
    }

    @Test
    @Config(qualifiers = "da")
    fun danish() {
        compose.setContent { Text(needsConnectionMessage()) }
        compose.onNodeWithText("Det kræver internetforbindelse").assertExists()
    }
}
