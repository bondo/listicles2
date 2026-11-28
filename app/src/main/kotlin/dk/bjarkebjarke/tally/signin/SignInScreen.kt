package dk.bjarkebjarke.tally.signin

import androidx.annotation.DrawableRes
import androidx.annotation.StringRes
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.InlineTextContent
import androidx.compose.foundation.text.appendInlineContent
import androidx.compose.material3.Button
import androidx.compose.material3.Icon
import androidx.compose.material3.LocalContentColor
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.takeOrElse
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.text
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.Placeholder
import androidx.compose.ui.text.PlaceholderVerticalAlign
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.tooling.preview.PreviewFontScale
import androidx.compose.ui.tooling.preview.PreviewLightDark
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import dk.bjarkebjarke.tally.R
import dk.bjarkebjarke.tally.SignInButtonIconSize
import dk.bjarkebjarke.tally.SignInMarkCorner
import dk.bjarkebjarke.tally.SignInMarkSize
import dk.bjarkebjarke.tally.Sizes
import dk.bjarkebjarke.tally.Spacing
import dk.bjarkebjarke.tally.TallyTheme
import kotlinx.coroutines.launch

/** The sign-in step of the start gates: [viewModel]'s state on the stateless [SignInScreen]. */
@Composable
fun SignInRoute(
    viewModel: SignInViewModel,
    onEmail: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val state by viewModel.uiState.collectAsStateWithLifecycle()
    SignInScreen(state, viewModel::continueWithGoogle, onEmail, viewModel::messageShown, modifier)
}

/**
 * AUTH-01, wireframe 01: the app name, "Continue with Google" as the main button and "Use email and password" as the
 * second. A message (no connection, no Google account, failure) is a snackbar; a closed picker shows nothing.
 */
@Composable
fun SignInScreen(
    state: SignInUiState,
    onGoogle: () -> Unit,
    onEmail: () -> Unit,
    onMessageShow: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val snackbar = remember { SnackbarHostState() }
    val message = state.message?.let { stringResource(it.text()) }
    val scope = rememberCoroutineScope()
    val currentOnMessageShow by rememberUpdatedState(onMessageShow)
    LaunchedEffect(message) {
        if (message != null) {
            // Reported at once, so the same message shows again after the next try; the snackbar outlives the state.
            scope.launch { snackbar.showSnackbar(message) }
            currentOnMessageShow()
        }
    }
    Scaffold(modifier.fillMaxSize(), snackbarHost = { SnackbarHost(snackbar) }) { padding ->
        // The Scaffold's padding is the one source of the system bars' insets (R1-01).
        SignInContent(state, onGoogle, onEmail, Modifier.padding(padding))
    }
}

/** The mark, the name, the two buttons and the note, centred. */
@Composable
private fun SignInContent(
    state: SignInUiState,
    onGoogle: () -> Unit,
    onEmail: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Column(
        modifier.fillMaxSize().padding(Sizes.screenGutter),
        verticalArrangement = Arrangement.Center,
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Surface(
            Modifier.size(SignInMarkSize).testTag(SIGN_IN_MARK_TAG),
            shape = RoundedCornerShape(SignInMarkCorner),
            color = MaterialTheme.colorScheme.primary,
        ) {
            Box(contentAlignment = Alignment.Center) {
                Icon(painterResource(R.drawable.ic_tally_mark), null, tint = MaterialTheme.colorScheme.onPrimary)
            }
        }
        Text(
            stringResource(R.string.app_name),
            Modifier.padding(top = Spacing.l).semantics { heading() },
            style = MaterialTheme.typography.headlineSmall,
        )
        Text(
            stringResource(R.string.app_tag),
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            style = MaterialTheme.typography.bodyLarge,
            textAlign = TextAlign.Center,
        )
        // One group, as wireframe 01's `.stack`: 4 dp between the buttons' bounds, so about 12 dp between the pills.
        Column(Modifier.padding(top = Spacing.l), verticalArrangement = Arrangement.spacedBy(Spacing.xs)) {
            Button(onGoogle, Modifier.fillMaxWidth(), enabled = !state.busy) {
                ButtonLabel(R.drawable.ic_login, R.string.signin_google, SIGN_IN_GOOGLE_ICON_TAG)
            }
            OutlinedButton(onEmail, Modifier.fillMaxWidth()) {
                ButtonLabel(
                    R.drawable.ic_mail,
                    R.string.signin_email,
                    SIGN_IN_EMAIL_ICON_TAG,
                    MaterialTheme.colorScheme.primary,
                )
            }
        }
        Text(
            stringResource(R.string.signin_note),
            Modifier.padding(top = Spacing.s),
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            style = MaterialTheme.typography.bodySmall,
            textAlign = TextAlign.Center,
        )
    }
}

/**
 * A button's leading icon and its label, centred also when the label wraps (200 % font scale). The icon is inline
 * content of the label, so it stays at the start of the first line (R2-02) and the lines centre as one block.
 */
@Composable
private fun ButtonLabel(
    @DrawableRes icon: Int,
    @StringRes label: Int,
    iconTag: String,
    color: Color = Color.Unspecified,
) {
    val text = stringResource(label)
    // Dp to sp through the density, so the placeholder stays the same dp size at any font scale.
    val (width, height) =
        with(LocalDensity.current) {
            (SignInButtonIconSize + Spacing.s).toSp() to
                SignInButtonIconSize.toSp()
        }
    val content =
        mapOf(
            ICON_ID to
                InlineTextContent(Placeholder(width, height, PlaceholderVerticalAlign.TextCenter)) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Icon(
                            painterResource(icon),
                            null,
                            Modifier.size(SignInButtonIconSize).testTag(iconTag),
                            color.takeOrElse { LocalContentColor.current },
                        )
                        Spacer(Modifier.width(Spacing.s))
                    }
                },
        )
    Text(
        buildAnnotatedString {
            appendInlineContent(ICON_ID)
            append(text)
        },
        // The label alone is the accessible text: the inline icon's placeholder character is not.
        Modifier.semantics { this.text = AnnotatedString(text) },
        color = color,
        textAlign = TextAlign.Center,
        inlineContent = content,
    )
}

private const val ICON_ID = "icon"

const val SIGN_IN_MARK_TAG = "signin_mark"
const val SIGN_IN_GOOGLE_ICON_TAG = "signin_google_icon"
const val SIGN_IN_EMAIL_ICON_TAG = "signin_email_icon"

@StringRes
private fun SignInMessage.text(): Int =
    when (this) {
        SignInMessage.NeedsConnection -> R.string.needs_connection
        SignInMessage.NoAccount -> R.string.signin_no_account
        SignInMessage.Failed -> R.string.signin_failed
    }

@Preview(locale = "da")
@PreviewLightDark
@PreviewFontScale
@Composable
private fun SignInScreenPreview() {
    TallyTheme { SignInScreen(SignInUiState(), {}, {}, {}) }
}
