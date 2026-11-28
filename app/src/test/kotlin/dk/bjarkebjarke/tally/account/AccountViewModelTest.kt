package dk.bjarkebjarke.tally.account

import dk.bjarkebjarke.tally.domain.account.AccountProfile
import dk.bjarkebjarke.tally.domain.session.SignOut
import dk.bjarkebjarke.tally.testing.FakeAccountProfiles
import dk.bjarkebjarke.tally.testing.FakeAuthentication
import dk.bjarkebjarke.tally.testing.FakeConnectivity
import dk.bjarkebjarke.tally.testing.FakeCrashReports
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

/** M1-25 (AUTH-03, privacy Q3): what the Account screen shows and what its switch and "Sign out" do, with fakes. */
@OptIn(ExperimentalCoroutinesApi::class)
class AccountViewModelTest {
    private val steps = mutableListOf<String>()
    private val connectivity = FakeConnectivity()
    private val userData = FakeLocalUserData(steps = steps)
    private val authentication = FakeAuthentication(steps = steps)
    private val credentials = FakeGoogleCredentials(steps = steps)
    private val crashReports = FakeCrashReports()
    private val profile = AccountProfile(name = "Sam Jensen", email = "sam@example.com")

    @Before
    fun mainDispatcher() = Dispatchers.setMain(UnconfinedTestDispatcher())

    @After
    fun resetDispatcher() = Dispatchers.resetMain()

    private fun viewModel() =
        AccountViewModel(
            FakeAccountProfiles(profile),
            crashReports,
            SignOut(
                connectivity,
                userData,
                authentication,
                credentials,
                CoroutineScope(SupervisorJob() + UnconfinedTestDispatcher()),
            ),
        )

    @Test
    fun showsTheProfileAndTheSwitchOffUntilTheUserTurnsItOn() {
        viewModel().uiState.value shouldBe AccountUiState(profile, crashReportsOn = false)
    }

    @Test
    fun theSwitchShowsWhatWasStored() {
        crashReports.sending = true
        viewModel().uiState.value.crashReportsOn shouldBe true
    }

    @Test
    fun theSwitchWritesThroughAndShowsTheNewValue() {
        val viewModel = viewModel()
        viewModel.setCrashReports(true)
        crashReports.sending shouldBe true
        viewModel.uiState.value.crashReportsOn shouldBe true
        viewModel.setCrashReports(false)
        crashReports.sending shouldBe false
        viewModel.uiState.value.crashReportsOn shouldBe false
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
        viewModel.uiState.value shouldBe AccountUiState(profile, crashReportsOn = false, failed = true)
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
