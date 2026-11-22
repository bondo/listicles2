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
import dk.bjarkebjarke.tally.domain.start.EmailVerification
import dk.bjarkebjarke.tally.domain.start.HouseholdNotice
import dk.bjarkebjarke.tally.domain.start.StartStep
import dk.bjarkebjarke.tally.testing.FakeEmailVerification
import dk.bjarkebjarke.tally.testing.FakeHouseholdNotices
import dk.bjarkebjarke.tally.testing.FakeNameState
import dk.bjarkebjarke.tally.testing.FakeSessionState
import dk.bjarkebjarke.tally.testing.FakeUpdateGate
import io.kotest.matchers.shouldBe
import kotlinx.coroutines.flow.flow
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

/** M1-60 and M1-62: the start-up root routes over all gates of P10. The real [StartViewModel] runs against fakes. */
@RunWith(RobolectricTestRunner::class)
class StartRoutingTest {
    @get:Rule
    val compose = createAndroidComposeRule<ComponentActivity>()

    private val update = FakeUpdateGate()
    private val session = FakeSessionState()
    private val email = FakeEmailVerification()
    private val name = FakeNameState()
    private val notices = FakeHouseholdNotices()
    private val context: Context = ApplicationProvider.getApplicationContext()
    private val signIn = context.getString(R.string.app_tag)
    private val home = context.getString(R.string.lists_empty_title)

    private fun start(source: SessionState = session): StartViewModel {
        val viewModel = StartViewModel(update, source, email, name, notices)
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
        viewModel.uiState.value shouldBe StartUiState.Ready(StartStep.SignIn)
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
        viewModel.uiState.value shouldBe StartUiState.Ready(StartStep.Home)
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
        viewModel.uiState.value shouldBe StartUiState.Ready(StartStep.SignIn)
    }

    private fun text(id: Int) = context.getString(id)

    @Test
    fun anUpdateRequiredStopsEvenASignedInStart() {
        update.required = true
        session.signedIn = true
        val viewModel = start()
        compose.onNodeWithText(text(R.string.gate_update_title)).assertExists()
        compose.onNodeWithText(home).assertDoesNotExist()
        viewModel.uiState.value shouldBe StartUiState.Ready(StartStep.Update)
    }

    @Test
    fun anUpdateRequiredStopsASignedOutStartToo() {
        update.required = true
        session.signedIn = false
        start().uiState.value shouldBe StartUiState.Ready(StartStep.Update)
        compose.onNodeWithText(signIn).assertDoesNotExist()
    }

    @Test
    fun anUnverifiedEmailShowsTheVerifyStep() {
        session.signedIn = true
        email.isVerified = false
        val viewModel = start()
        compose.onNodeWithText(text(R.string.gate_verify_title)).assertExists()
        compose.onNodeWithText(home).assertDoesNotExist()
        viewModel.uiState.value shouldBe StartUiState.Ready(StartStep.VerifyEmail)
    }

    @Test
    fun aMissingNameShowsTheNameStep() {
        session.signedIn = true
        name.isSaved = false
        val viewModel = start()
        compose.onNodeWithText(text(R.string.gate_name_title)).assertExists()
        compose.onNodeWithText(home).assertDoesNotExist()
        viewModel.uiState.value shouldBe StartUiState.Ready(StartStep.EnterName)
    }

    @Test
    fun aRemovalNoticeShowsBeforeTheHome() {
        session.signedIn = true
        notices.notice = HouseholdNotice.Removed
        val viewModel = start()
        compose.onNodeWithText(text(R.string.gate_notice_removed)).assertExists()
        compose.onNodeWithText(home).assertDoesNotExist()
        viewModel.uiState.value shouldBe StartUiState.Ready(StartStep.Notice(HouseholdNotice.Removed))
    }

    @Test
    fun aDeletedHouseholdNoticeShowsItsOwnText() {
        session.signedIn = true
        notices.notice = HouseholdNotice.HouseholdDeleted
        start()
        compose.onNodeWithText(text(R.string.gate_notice_deleted)).assertExists()
        compose.onNodeWithText(text(R.string.gate_notice_removed)).assertDoesNotExist()
    }

    @Test
    fun signedOutIgnoresTheLaterGates() {
        session.signedIn = false
        email.isVerified = false
        name.isSaved = false
        notices.notice = HouseholdNotice.Removed
        start().uiState.value shouldBe StartUiState.Ready(StartStep.SignIn)
    }

    @Test
    fun theEarliestFailingGateWins() {
        session.signedIn = true
        email.isVerified = false
        name.isSaved = false
        notices.notice = HouseholdNotice.Removed
        val viewModel = start()
        viewModel.uiState.value shouldBe StartUiState.Ready(StartStep.VerifyEmail)
        email.isVerified = true
        compose.waitForIdle()
        viewModel.uiState.value shouldBe StartUiState.Ready(StartStep.EnterName)
        name.isSaved = true
        compose.waitForIdle()
        viewModel.uiState.value shouldBe StartUiState.Ready(StartStep.Notice(HouseholdNotice.Removed))
        notices.notice = null
        compose.waitForIdle()
        viewModel.uiState.value shouldBe StartUiState.Ready(StartStep.Home)
        compose.onNodeWithText(home).assertExists()
    }

    @Test
    fun aFailingGateSourceOpensSignInNotTheHome() {
        session.signedIn = true
        val failing = EmailVerification { flow { throw IllegalStateException("gate failed") } }
        val viewModel = StartViewModel(update, session, failing, name, notices)
        compose.setContent { TallyApp(viewModel) }
        viewModel.uiState.value shouldBe StartUiState.Ready(StartStep.SignIn)
    }

    private val isHeading = SemanticsMatcher.keyIsDefined(SemanticsProperties.Heading)
}
