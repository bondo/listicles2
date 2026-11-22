package dk.bjarkebjarke.tally.start

import android.content.Context
import androidx.activity.ComponentActivity
import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.test.SemanticsMatcher
import androidx.compose.ui.test.assert
import androidx.compose.ui.test.junit4.v2.createAndroidComposeRule
import androidx.compose.ui.test.onNodeWithText
import androidx.test.core.app.ApplicationProvider
import dk.bjarkebjarke.tally.R
import dk.bjarkebjarke.tally.TallyApp
import dk.bjarkebjarke.tally.domain.session.SessionState
import dk.bjarkebjarke.tally.testing.FakeSessionState
import io.kotest.matchers.shouldBe
import kotlinx.coroutines.flow.flow
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
    val compose = createAndroidComposeRule<ComponentActivity>()

    private val session = FakeSessionState()
    private val context: Context = ApplicationProvider.getApplicationContext()
    private val signIn = context.getString(R.string.app_tag)
    private val home = context.getString(R.string.lists_empty_title)

    private fun start(source: SessionState = session): StartViewModel {
        val viewModel = StartViewModel(source)
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
        // PR 311 R1-03: the screen title is a heading (stories.md: screen titles are headings).
        compose.onNodeWithText(context.getString(R.string.lists_title)).assert(isHeading)
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

    /** PR 311 R1-04: a passed gate is not on the back stack, so system Back on the home leaves the app. */
    @Test
    fun backOnTheHomeAfterSigningInLeavesTheApp() {
        session.signedIn = false
        start()
        session.signedIn = true
        compose.onNodeWithText(home).assertExists()
        compose.activity.onBackPressedDispatcher
            .hasEnabledCallbacks()
            .shouldBe(false)
    }

    /** PR 311 R1-02 (checklist section 4): a failing session source opens sign-in instead of crashing the app. */
    @Test
    fun aFailingSessionSourceShowsSignIn() {
        val viewModel = start(SessionState { flow { throw IllegalStateException("session source failed") } })
        compose.onNodeWithText(signIn).assertExists()
        viewModel.uiState.value shouldBe StartUiState.Ready(StartRoute.SignIn)
    }

    private val isHeading = SemanticsMatcher.keyIsDefined(SemanticsProperties.Heading)
}
