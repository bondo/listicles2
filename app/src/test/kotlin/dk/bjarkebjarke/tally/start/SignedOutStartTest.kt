package dk.bjarkebjarke.tally.start

import androidx.compose.ui.test.junit4.v2.createAndroidComposeRule
import androidx.compose.ui.test.onNodeWithText
import dagger.hilt.android.testing.BindValue
import dagger.hilt.android.testing.HiltAndroidRule
import dagger.hilt.android.testing.HiltAndroidTest
import dagger.hilt.android.testing.HiltTestApplication
import dagger.hilt.android.testing.UninstallModules
import dk.bjarkebjarke.tally.MainActivity
import dk.bjarkebjarke.tally.R
import dk.bjarkebjarke.tally.domain.session.SessionState
import dk.bjarkebjarke.tally.testing.FakeSessionState
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

/** M1-60: the real activity, its Hilt ViewModel and the root, with a signed-out session, open on sign-in. */
@HiltAndroidTest
@UninstallModules(SessionModule::class)
@RunWith(RobolectricTestRunner::class)
@Config(application = HiltTestApplication::class)
class SignedOutStartTest {
    @get:Rule(order = 0)
    val hilt = HiltAndroidRule(this)

    @get:Rule(order = 1)
    val compose = createAndroidComposeRule<MainActivity>()

    @BindValue
    @JvmField
    val session: SessionState = FakeSessionState(signedIn = false)

    @Test
    fun signedOutStartShowsSignIn() {
        compose.onNodeWithText(compose.activity.getString(R.string.app_tag)).assertExists()
        compose.onNodeWithText(compose.activity.getString(R.string.lists_empty_title)).assertDoesNotExist()
    }
}
