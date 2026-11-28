package dk.bjarkebjarke.tally.account

import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.platform.UriHandler
import androidx.compose.ui.test.assertIsNotEnabled
import androidx.compose.ui.test.junit4.v2.createComposeRule
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import dk.bjarkebjarke.tally.TallyTheme
import dk.bjarkebjarke.tally.domain.account.AccountProfile
import io.kotest.matchers.shouldBe
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

/** M1-25 (AUTH-03, wireframes 18, 39 and 45): the Account screen in English and Danish, its switch and its dialog. */
@RunWith(RobolectricTestRunner::class)
class AccountScreenTest {
    @get:Rule
    val compose = createComposeRule()

    private val profile = AccountProfile(name = "Sam Jensen", email = "sam@example.com")
    private val calls = mutableListOf<String>()
    private val opened = mutableListOf<String>()
    private val uriHandler =
        object : UriHandler {
            override fun openUri(uri: String) {
                opened += uri
            }
        }

    private fun show(state: AccountUiState = AccountUiState(profile)) =
        compose.setContent {
            CompositionLocalProvider(LocalUriHandler provides uriHandler) {
                TallyTheme(false) {
                    AccountScreen(
                        state,
                        AccountActions(
                            onBack = { calls += "back" },
                            onSignOut = { calls += "signOut" },
                            onSignOutAnyway = { calls += "anyway" },
                            onCancel = { calls += "cancel" },
                            onFailureShown = { calls += "shown" },
                        ),
                    )
                }
            }
        }

    @Test
    @Config(qualifiers = "en")
    fun english() {
        show()
        compose.onNodeWithText("Sam Jensen").assertExists()
        compose.onNodeWithText("sam@example.com").assertExists()
        compose.onNodeWithText("Sign out").assertExists()
        compose.onNodeWithText("Removes your lists from this phone").assertExists()
        compose.onNodeWithText("Privacy policy").assertExists()
    }

    @Test
    @Config(qualifiers = "da")
    fun danish() {
        show()
        compose.onNodeWithText("Log ud").assertExists()
        compose.onNodeWithText("Fjerner dine lister fra denne telefon").assertExists()
        compose.onNodeWithText("Privatlivspolitik").assertExists()
    }

    @Test
    @Config(qualifiers = "en")
    fun signOutWaitsWhileItRuns() {
        show(AccountUiState(profile, signingOut = true))
        compose.onNodeWithText("Sign out").assertIsNotEnabled()
    }

    @Test
    @Config(qualifiers = "en")
    fun signOutCallsBackAndThePrivacyLinkOpensTheEnglishText() {
        show()
        compose.onNodeWithText("Sign out").performClick()
        compose.onNodeWithText("Privacy policy").performClick()
        calls shouldBe listOf("signOut")
        opened shouldBe listOf("https://github.com/bondo/tally/blob/main/docs/privacy/privacy-en.md")
    }

    @Test
    @Config(qualifiers = "da")
    fun thePrivacyLinkOpensTheDanishText() {
        show()
        compose.onNodeWithText("Privatlivspolitik").performClick()
        opened shouldBe listOf("https://github.com/bondo/tally/blob/main/docs/privacy/privacy-da.md")
    }

    @Test
    @Config(qualifiers = "en")
    fun wireframe39AsksWithTheUnsentChangeText() {
        show(AccountUiState(profile, question = SignOutQuestion.NotSentYet))
        compose.onNodeWithText("Sign out?").assertExists()
        compose
            .onNodeWithText(
                "Some changes have not been sent yet. If you sign out now, they will be lost.",
            ).assertExists()
        compose.onNodeWithText("Cancel").performClick()
        compose.onNodeWithText("Sign out anyway").performClick()
        calls shouldBe listOf("cancel", "anyway")
    }

    @Test
    @Config(qualifiers = "en")
    fun wireframe45AsksWithoutClaimingAChangeIsUnsent() {
        show(AccountUiState(profile, question = SignOutQuestion.MayNotBeSent))
        compose
            .onNodeWithText("Changes you made may not have been sent yet. If you sign out now, they may be lost.")
            .assertExists()
    }

    @Test
    @Config(qualifiers = "da")
    fun theQuestionInDanish() {
        show(AccountUiState(profile, question = SignOutQuestion.NotSentYet))
        compose.onNodeWithText("Log ud?").assertExists()
        compose.onNodeWithText("Nogle ændringer er ikke sendt endnu. Hvis du logger ud nu, går de tabt.").assertExists()
        compose.onNodeWithText("Annuller").assertExists()
        compose.onNodeWithText("Log ud alligevel").assertExists()
    }

    @Test
    @Config(qualifiers = "en")
    fun aFailedSignOutIsAMessageReportedShownAtOnce() {
        show(AccountUiState(profile, failed = true))
        compose.onNodeWithText("Could not sign out. Try again.").assertExists()
        compose.waitForIdle()
        calls shouldBe listOf("shown")
    }
}
