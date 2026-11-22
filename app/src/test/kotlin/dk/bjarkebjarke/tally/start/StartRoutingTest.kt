package dk.bjarkebjarke.tally.start

import android.content.Context
import androidx.compose.ui.test.junit4.v2.createComposeRule
import androidx.compose.ui.test.onNodeWithText
import androidx.test.core.app.ApplicationProvider
import dk.bjarkebjarke.tally.R
import dk.bjarkebjarke.tally.TallyApp
import dk.bjarkebjarke.tally.testing.FakeSessionState
import io.kotest.matchers.shouldBe
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

/**
 * M1-60: the start-up root routes on the session (P10 step 2, signed in, and step 6, the M1 home of Q1 A). M1-62 adds
 * the other gates to this test. The real [StartViewModel] runs against a [FakeSessionState].
 */
@RunWith(RobolectricTestRunner::class)
class StartRoutingTest {
    @get:Rule
    val compose = createComposeRule()

    private val session = FakeSessionState()
    private val context: Context = ApplicationProvider.getApplicationContext()
    private val signIn = context.getString(R.string.app_tag)
    private val home = context.getString(R.string.lists_empty_title)

    private fun start(): StartViewModel {
        val viewModel = StartViewModel(session)
        compose.setContent { TallyApp(viewModel) }
        return viewModel
    }

    @Test
    fun showsNeitherScreenUntilTheSessionIsKnown() {
        val viewModel = start()
        compose.onNodeWithText(signIn).assertDoesNotExist()
        compose.onNodeWithText(home).assertDoesNotExist()
        viewModel.uiState.value shouldBe StartUiState.Loading
    }

    @Test
    fun signedOutStartShowsSignIn() {
        session.signedIn = false
        val viewModel = start()
        compose.onNodeWithText(signIn).assertExists()
        compose.onNodeWithText(home).assertDoesNotExist()
        viewModel.uiState.value shouldBe StartUiState.Ready(StartRoute.SignIn)
    }

    @Test
    fun signedInStartShowsTheHome() {
        session.signedIn = true
        val viewModel = start()
        compose.onNodeWithText(home).assertExists()
        compose.onNodeWithText(context.getString(R.string.lists_title)).assertExists()
        compose.onNodeWithText(context.getString(R.string.lists_empty_body)).assertExists()
        compose.onNodeWithText(signIn).assertDoesNotExist()
        viewModel.uiState.value shouldBe StartUiState.Ready(StartRoute.Home)
    }

    @Test
    fun signingInAndOutWhileOpenReplacesTheScreen() {
        session.signedIn = false
        start()
        session.signedIn = true
        compose.onNodeWithText(home).assertExists()
        compose.onNodeWithText(signIn).assertDoesNotExist()
        session.signedIn = false
        compose.onNodeWithText(signIn).assertExists()
        compose.onNodeWithText(home).assertDoesNotExist()
    }
}
