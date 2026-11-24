package dk.bjarkebjarke.tally.signin

import androidx.compose.ui.test.assertHasClickAction
import androidx.compose.ui.test.assertIsNotEnabled
import androidx.compose.ui.test.junit4.v2.createComposeRule
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import dk.bjarkebjarke.tally.TallyTheme
import io.kotest.matchers.shouldBe
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

/** M1-16 (AUTH-01, wireframe 01): the sign-in screen in English and Danish, its two buttons and its messages. */
@RunWith(RobolectricTestRunner::class)
class SignInScreenTest {
    @get:Rule
    val compose = createComposeRule()

    private var google = 0
    private var email = 0
    private var shown = 0

    private fun show(state: SignInUiState = SignInUiState()) =
        compose.setContent {
            TallyTheme(false) { SignInScreen(state, { google++ }, { email++ }, { shown++ }) }
        }

    @Test
    @Config(qualifiers = "en")
    fun english() {
        show()
        compose.onNodeWithText("Collections and lists, shared with your household").assertExists()
        compose.onNodeWithText("Continue with Google").assertHasClickAction()
        compose.onNodeWithText("Use email and password").assertHasClickAction()
        compose
            .onNodeWithText("Your lists are kept with your account, so they follow you to a new phone.")
            .assertExists()
    }

    @Test
    @Config(qualifiers = "da")
    fun danish() {
        show()
        compose.onNodeWithText("Samlinger og lister, delt med din husstand").assertExists()
        compose.onNodeWithText("Fortsæt med Google").assertHasClickAction()
        compose.onNodeWithText("Brug e-mail og adgangskode").assertHasClickAction()
        compose
            .onNodeWithText("Dine lister gemmes med din konto, så de følger med til en ny telefon.")
            .assertExists()
    }

    @Test
    fun theButtonsCallTheirCallbacks() {
        show()
        compose.onNodeWithText("Continue with Google").performClick()
        google shouldBe 1
        email shouldBe 0
        compose.onNodeWithText("Use email and password").performClick()
        google shouldBe 1
        email shouldBe 1
    }

    @Test
    fun noMessageShowsNothingExtra() {
        show()
        compose.onNodeWithText("This needs a connection").assertDoesNotExist()
    }

    @Test
    @Config(qualifiers = "en")
    fun needsConnectionIsASnackbarAndIsReportedShown() {
        show(SignInUiState(message = SignInMessage.NeedsConnection))
        compose.onNodeWithText("This needs a connection").assertExists()
        compose.waitUntil { shown == 1 }
    }

    @Test
    @Config(qualifiers = "da")
    fun needsConnectionInDanish() {
        show(SignInUiState(message = SignInMessage.NeedsConnection))
        compose.onNodeWithText("Det kræver internetforbindelse").assertExists()
    }

    @Test
    @Config(qualifiers = "en")
    fun noAccountMessageInEnglish() {
        show(SignInUiState(message = SignInMessage.NoAccount))
        compose.onNodeWithText("This phone has no Google account. Add one, or use email and password.").assertExists()
    }

    @Test
    @Config(qualifiers = "da")
    fun noAccountMessageInDanish() {
        show(SignInUiState(message = SignInMessage.NoAccount))
        compose
            .onNodeWithText("Der er ingen Google-konto på denne telefon. Tilføj en, eller brug e-mail og adgangskode.")
            .assertExists()
    }

    @Test
    @Config(qualifiers = "en")
    fun failedMessageInEnglish() {
        show(SignInUiState(message = SignInMessage.Failed))
        compose.onNodeWithText("Could not sign in. Try again.").assertExists()
    }

    @Test
    @Config(qualifiers = "da")
    fun failedMessageInDanish() {
        show(SignInUiState(message = SignInMessage.Failed))
        compose.onNodeWithText("Kunne ikke logge ind. Prøv igen.").assertExists()
    }

    @Test
    fun whileSigningInTheGoogleButtonIsDisabledSoItCannotBeTappedTwice() {
        show(SignInUiState(busy = true))
        compose.onNodeWithText("Continue with Google").assertIsNotEnabled()
    }
}
