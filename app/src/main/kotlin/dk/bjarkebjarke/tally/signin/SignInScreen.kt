package dk.bjarkebjarke.tally.signin

import androidx.annotation.StringRes
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.tooling.preview.PreviewFontScale
import androidx.compose.ui.tooling.preview.PreviewLightDark
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import dk.bjarkebjarke.tally.R
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
        Column(
            Modifier
                .fillMaxSize()
                .padding(padding)
                .padding(Sizes.screenGutter),
            verticalArrangement = Arrangement.spacedBy(Spacing.l, Alignment.CenterVertically),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Text(
                stringResource(R.string.app_name),
                Modifier.semantics { heading() },
                style = MaterialTheme.typography.headlineSmall,
            )
            Text(
                stringResource(R.string.app_tag),
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                style = MaterialTheme.typography.bodyLarge,
                textAlign = TextAlign.Center,
            )
            Button(onGoogle, Modifier.fillMaxWidth(), enabled = !state.busy) {
                Text(stringResource(R.string.signin_google), textAlign = TextAlign.Center)
            }
            OutlinedButton(onEmail, Modifier.fillMaxWidth()) {
                Text(stringResource(R.string.signin_email), textAlign = TextAlign.Center)
            }
            Text(
                stringResource(R.string.signin_note),
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                style = MaterialTheme.typography.bodySmall,
                textAlign = TextAlign.Center,
            )
        }
    }
}

@StringRes
private fun SignInMessage.text(): Int =
    when (this) {
        SignInMessage.NeedsConnection -> R.string.needs_connection
        SignInMessage.NoAccount -> R.string.signin_no_account
        SignInMessage.EmailHasPasswordAccount -> R.string.signin_email_has_password
        SignInMessage.Failed -> R.string.signin_failed
    }

@Preview(locale = "da")
@PreviewLightDark
@PreviewFontScale
@Composable
private fun SignInScreenPreview() {
    TallyTheme { SignInScreen(SignInUiState(), {}, {}, {}) }
}
