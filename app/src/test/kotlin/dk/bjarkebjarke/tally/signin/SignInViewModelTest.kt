package dk.bjarkebjarke.tally.signin

import dk.bjarkebjarke.tally.domain.session.GoogleCredentials
import dk.bjarkebjarke.tally.domain.session.GoogleIdToken
import dk.bjarkebjarke.tally.domain.session.GoogleSignIn
import dk.bjarkebjarke.tally.domain.session.GoogleSignInResult
import dk.bjarkebjarke.tally.testing.FakeAuthentication
import dk.bjarkebjarke.tally.testing.FakeConnectivity
import dk.bjarkebjarke.tally.testing.FakeGoogleCredentials
import io.kotest.matchers.shouldBe
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.UnconfinedTestDispatcher
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.setMain
import org.junit.After
import org.junit.Before
import org.junit.Test

/** M1-16 (AUTH-01, SYNC-03): what "Continue with Google" leaves on the sign-in screen, with fakes for every outcome. */
@OptIn(ExperimentalCoroutinesApi::class)
class SignInViewModelTest {
    private val connectivity = FakeConnectivity()
    private val credentials = FakeGoogleCredentials()
    private val authentication = FakeAuthentication()

    @Before
    fun mainDispatcher() = Dispatchers.setMain(UnconfinedTestDispatcher())

    @After
    fun resetDispatcher() = Dispatchers.resetMain()

    private fun viewModel() = SignInViewModel(GoogleSignIn(connectivity, credentials, authentication))

    @Test
    fun startsWithNoMessageAndNothingRunning() {
        viewModel().uiState.value shouldBe SignInUiState()
    }

    @Test
    fun signedInShowsNothingAndSignsInWithThePickedToken() {
        val viewModel = viewModel()
        viewModel.continueWithGoogle()
        viewModel.uiState.value shouldBe SignInUiState()
        authentication.googleIdTokens shouldBe listOf("fake-google-id-token")
    }

    @Test
    fun offlineShowsTheNeedsConnectionMessageAndNeverOpensThePicker() {
        connectivity.online = false
        val viewModel = viewModel()
        viewModel.continueWithGoogle()
        viewModel.uiState.value shouldBe SignInUiState(message = SignInMessage.NeedsConnection)
        credentials.steps shouldBe emptyList()
    }

    @Test
    fun aClosedPickerShowsNothing() {
        credentials.answer = GoogleIdToken.Cancelled
        val viewModel = viewModel()
        viewModel.continueWithGoogle()
        viewModel.uiState.value shouldBe SignInUiState()
    }

    @Test
    fun noGoogleAccountOnThePhoneShowsTheNoAccountMessage() {
        credentials.answer = GoogleIdToken.NoAccount
        val viewModel = viewModel()
        viewModel.continueWithGoogle()
        viewModel.uiState.value shouldBe SignInUiState(message = SignInMessage.NoAccount)
    }

    @Test
    fun aFailedPickerOrFirebaseShowsTheFailedMessage() {
        credentials.answer = GoogleIdToken.Failed
        val first = viewModel()
        first.continueWithGoogle()
        first.uiState.value shouldBe SignInUiState(message = SignInMessage.Failed)

        authentication.googleResult = GoogleSignInResult.Failed
        credentials.answer = GoogleIdToken.Picked("t")
        val second = viewModel()
        second.continueWithGoogle()
        second.uiState.value shouldBe SignInUiState(message = SignInMessage.Failed)
    }

    /** M1-121: the non-Gmail collision has its own message (wireframe 44). */
    @Test
    fun aGoogleAccountWhoseEmailHasAPasswordAccountShowsTheCollisionMessage() {
        authentication.googleResult = GoogleSignInResult.EmailHasPasswordAccount
        val viewModel = viewModel()
        viewModel.continueWithGoogle()
        viewModel.uiState.value shouldBe SignInUiState(message = SignInMessage.EmailHasPasswordAccount)
    }

    @Test
    fun aShownMessageIsCleared() {
        connectivity.online = false
        val viewModel = viewModel()
        viewModel.continueWithGoogle()
        viewModel.messageShown()
        viewModel.uiState.value shouldBe SignInUiState()
    }

    @Test
    fun aNewTryClearsTheOldMessage() {
        connectivity.online = false
        val viewModel = viewModel()
        viewModel.continueWithGoogle()
        connectivity.online = true
        viewModel.continueWithGoogle()
        viewModel.uiState.value shouldBe SignInUiState()
    }

    /** R1-02: while the picker is open the screen is busy, a second tap opens no second picker, and busy ends after. */
    @Test
    fun aSecondTapWhileBusyOpensNoSecondPicker() {
        val gate = CompletableDeferred<GoogleIdToken>()
        val picker = GatedCredentials(gate)
        val viewModel = SignInViewModel(GoogleSignIn(connectivity, picker, authentication))
        viewModel.continueWithGoogle()
        viewModel.uiState.value shouldBe SignInUiState(busy = true)
        viewModel.continueWithGoogle()
        picker.pickers shouldBe 1
        gate.complete(GoogleIdToken.Picked("t"))
        viewModel.uiState.value shouldBe SignInUiState()
        authentication.googleIdTokens shouldBe listOf("t")
    }

    private class GatedCredentials(
        private val gate: CompletableDeferred<GoogleIdToken>,
    ) : GoogleCredentials {
        var pickers = 0

        override suspend fun idToken(): GoogleIdToken {
            pickers++
            return gate.await()
        }

        override suspend fun clearCredentialState() = Unit
    }
}
