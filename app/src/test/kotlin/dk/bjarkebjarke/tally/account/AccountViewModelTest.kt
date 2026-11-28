package dk.bjarkebjarke.tally.account

import dk.bjarkebjarke.tally.domain.account.AccountProfile
import dk.bjarkebjarke.tally.domain.session.SignOut
import dk.bjarkebjarke.tally.testing.FakeAccountProfiles
import dk.bjarkebjarke.tally.testing.FakeAuthentication
import dk.bjarkebjarke.tally.testing.FakeConnectivity
import dk.bjarkebjarke.tally.testing.FakeGoogleCredentials
import dk.bjarkebjarke.tally.testing.FakeLocalUserData
import io.kotest.matchers.shouldBe
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.test.UnconfinedTestDispatcher
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.setMain
import org.junit.After
import org.junit.Before
import org.junit.Test

/** M1-25 (AUTH-03): what the Account view model shows and what "Sign out" does, with fakes. */
@OptIn(ExperimentalCoroutinesApi::class)
class AccountViewModelTest {
    private val steps = mutableListOf<String>()
    private val connectivity = FakeConnectivity()
    private val userData = FakeLocalUserData(steps = steps)
    private val authentication = FakeAuthentication(steps = steps)
    private val credentials = FakeGoogleCredentials(steps = steps)
    private val profile = AccountProfile(name = "Sam Jensen", email = "sam@example.com")

    @Before
    fun mainDispatcher() = Dispatchers.setMain(UnconfinedTestDispatcher())

    @After
    fun resetDispatcher() = Dispatchers.resetMain()

    private val profiles = FakeAccountProfiles(profile)

    private fun viewModel() =
        AccountViewModel(
            profiles,
            SignOut(
                connectivity,
                userData,
                authentication,
                credentials,
                CoroutineScope(SupervisorJob() + UnconfinedTestDispatcher()),
            ),
        )

    @Test
    fun showsTheSignedInProfileAndNoQuestion() {
        viewModel().uiState.value shouldBe AccountUiState(profile)
    }

    @Test
    fun openingReadsTheAccountSignedInNow() {
        val viewModel = viewModel()
        profiles.profile = AccountProfile("Alex", "alex@example.com")
        viewModel.opened()
        viewModel.uiState.value.profile shouldBe AccountProfile("Alex", "alex@example.com")
    }

    @Test
    fun signOutWithAllChangesSentRunsEveryStepInOrderWithoutAsking() {
        val viewModel = viewModel()
        viewModel.signOut()
        steps shouldBe
            listOf("awaitPendingWrites", "clear", "cleared", "signOut", "clearCredentialState")
        viewModel.uiState.value.question shouldBe null
    }

    @Test
    fun offlineAsksWithTheNoUnsentChangeKnownWordingAndSignsNothingOut() {
        connectivity.online = false
        val viewModel = viewModel()
        viewModel.signOut()
        viewModel.uiState.value.question shouldBe SignOutQuestion.MayNotBeSent
        steps shouldBe emptyList()
    }

    @Test
    fun anUnsentChangeKnownAsksWithTheUnsentWording() {
        connectivity.online = false
        userData.unsentChangesSeen = true
        val viewModel = viewModel()
        viewModel.signOut()
        viewModel.uiState.value.question shouldBe SignOutQuestion.NotSentYet
    }

    @Test
    fun cancelClosesTheQuestionAndSignsNothingOut() {
        connectivity.online = false
        val viewModel = viewModel()
        viewModel.signOut()
        viewModel.cancelSignOut()
        viewModel.uiState.value.question shouldBe null
        steps shouldBe emptyList()
    }

    @Test
    fun signOutAnywayClearsTheCopyAndSignsOut() {
        connectivity.online = false
        val viewModel = viewModel()
        viewModel.signOut()
        viewModel.signOutAnyway()
        viewModel.uiState.value.question shouldBe null
        steps shouldBe listOf("clear", "cleared", "signOut", "clearCredentialState")
    }

    @Test
    fun aCopyThatCannotBeDeletedKeepsTheUserSignedInAndSaysSo() {
        userData.clearFails = true
        val viewModel = viewModel()
        viewModel.signOut()
        viewModel.uiState.value shouldBe AccountUiState(profile, failed = true)
        steps.contains("signOut") shouldBe false
        viewModel.failureShown()
        viewModel.uiState.value.failed shouldBe false
    }

    @Test
    fun signOutIsBusyWhileItRunsAndASecondTapDoesNothing() {
        val gate = CompletableDeferred<Unit>()
        userData.clearGate = gate
        val viewModel = viewModel()
        viewModel.signOut()
        viewModel.uiState.value.signingOut shouldBe true
        viewModel.signOut()
        steps.count { it == "awaitPendingWrites" } shouldBe 1
        gate.complete(Unit)
        viewModel.uiState.value.signingOut shouldBe false
    }
}
