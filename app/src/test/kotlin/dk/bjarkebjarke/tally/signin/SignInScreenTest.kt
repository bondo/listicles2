package dk.bjarkebjarke.tally.signin

import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.semantics.SemanticsActions
import androidx.compose.ui.test.assertHasClickAction
import androidx.compose.ui.test.assertIsNotEnabled
import androidx.compose.ui.test.getUnclippedBoundsInRoot
import androidx.compose.ui.test.junit4.v2.createComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.text.TextLayoutResult
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.Density
import androidx.compose.ui.unit.dp
import dk.bjarkebjarke.tally.TallyTheme
import io.kotest.matchers.comparables.shouldBeGreaterThan
import io.kotest.matchers.comparables.shouldBeGreaterThanOrEqualTo
import io.kotest.matchers.comparables.shouldBeLessThanOrEqualTo
import io.kotest.matchers.floats.plusOrMinus
import io.kotest.matchers.shouldBe
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode

/** M1-16 (AUTH-01, wireframe 01): the sign-in screen in English and Danish, its two buttons and its messages. */
@RunWith(RobolectricTestRunner::class)
class SignInScreenTest {
    @get:Rule
    val compose = createComposeRule()

    private var google = 0
    private var email = 0
    private var shown = 0

    private fun show(
        state: SignInUiState = SignInUiState(),
        fontScale: Float = 1f,
    ) = compose.setContent {
        CompositionLocalProvider(LocalDensity provides Density(LocalDensity.current.density, fontScale)) {
            TallyTheme(false) { SignInScreen(state, { google++ }, { email++ }, { shown++ }) }
        }
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

    /** R1-03: a label that wraps (Danish at 200 % font scale) stays centred in its button. */
    @Test
    fun theButtonLabelsAreCentred() {
        show()
        for (label in listOf("Continue with Google", "Use email and password")) {
            textStyle(label).textAlign shouldBe TextAlign.Center
        }
    }

    /** R1-04: wireframe 01's outlined button has a primary label; the filled one keeps its on-primary label. */
    @Test
    fun theOutlinedButtonLabelIsPrimary() {
        var primary = Color.Unspecified
        compose.setContent {
            TallyTheme(false) {
                primary = MaterialTheme.colorScheme.primary
                SignInScreen(SignInUiState(), {}, {}, {})
            }
        }
        textStyle("Use email and password").color shouldBe primary
    }

    /** R1-04: the mark is shown; the two buttons are one group (4 dp between their bounds), apart from the tagline. */
    @Test
    fun theMarkIsShownAndTheButtonsAreGrouped() {
        show()
        compose.onNodeWithTag(SIGN_IN_MARK_TAG).assertExists()
        val google = compose.onNodeWithText("Continue with Google").getUnclippedBoundsInRoot()
        val email = compose.onNodeWithText("Use email and password").getUnclippedBoundsInRoot()
        (email.top - google.bottom).value shouldBe 4f
        val tagline =
            compose
                .onNodeWithText(
                    "Collections and lists, shared with your household",
                ).getUnclippedBoundsInRoot()
        (google.top - tagline.bottom) shouldBeGreaterThan 12.dp
    }

    /** R2-03: at 200 % font the pills fill their touch targets, so the gap cannot come from the inset. */
    @Test
    @GraphicsMode(GraphicsMode.Mode.NATIVE)
    @Config(qualifiers = "w360dp-h640dp-xhdpi")
    fun theButtonsHaveARealGapAt200PercentFontScale() {
        show(fontScale = 2f)
        val google = compose.onNodeWithText("Continue with Google").getUnclippedBoundsInRoot()
        val email = compose.onNodeWithText("Use email and password").getUnclippedBoundsInRoot()
        (email.top - google.bottom) shouldBeGreaterThan 0.dp
    }

    /** R2-02: when the label wraps (200 % font), the icon stays beside its first line, not at the pill's edge. */
    @Test
    @GraphicsMode(GraphicsMode.Mode.NATIVE)
    @Config(qualifiers = "da-w360dp-h640dp-xhdpi")
    fun theIconStaysBesideTheFirstLabelLineAt200PercentFontScale() {
        show(fontScale = 2f)
        val label = "Brug e-mail og adgangskode"
        val text = compose.onNodeWithText(label, useUnmergedTree = true)
        val results = mutableListOf<TextLayoutResult>()
        text
            .fetchSemanticsNode()
            .config[SemanticsActions.GetTextLayoutResult]
            .action
            ?.invoke(results)
        val layout = results.single()
        layout.lineCount shouldBeGreaterThan 1
        val node = text.fetchSemanticsNode().boundsInRoot
        val icon =
            compose
                .onNodeWithTag(
                    SIGN_IN_EMAIL_ICON_TAG,
                    useUnmergedTree = true,
                ).fetchSemanticsNode()
                .boundsInRoot
        val firstLineLeft = node.left + layout.getLineLeft(0)
        val firstLineTop = node.top + layout.getLineTop(0)
        val firstLineBottom = node.top + layout.getLineBottom(0)
        val tolerance = compose.density.density // 1 dp in px
        icon.left shouldBe (firstLineLeft plusOrMinus tolerance)
        val iconMiddle = (icon.top + icon.bottom) / 2
        iconMiddle shouldBeGreaterThanOrEqualTo firstLineTop
        iconMiddle shouldBeLessThanOrEqualTo firstLineBottom
    }

    @Test
    fun bothButtonsShowTheirIcon() {
        show()
        compose.onNodeWithTag(SIGN_IN_GOOGLE_ICON_TAG, useUnmergedTree = true).assertExists()
        compose.onNodeWithTag(SIGN_IN_EMAIL_ICON_TAG, useUnmergedTree = true).assertExists()
    }

    private fun textStyle(label: String): TextStyle {
        val results = mutableListOf<TextLayoutResult>()
        compose
            .onNodeWithText(label, useUnmergedTree = true)
            .fetchSemanticsNode()
            .config[SemanticsActions.GetTextLayoutResult]
            .action
            ?.invoke(results)
        return results.single().layoutInput.style
    }

    @Test
    fun whileSigningInTheGoogleButtonIsDisabledSoItCannotBeTappedTwice() {
        show(SignInUiState(busy = true))
        compose.onNodeWithText("Continue with Google").assertIsNotEnabled()
    }
}
