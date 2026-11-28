package dk.bjarkebjarke.tally.account

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.tooling.preview.PreviewFontScale
import androidx.compose.ui.tooling.preview.PreviewLightDark
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import dk.bjarkebjarke.tally.R
import dk.bjarkebjarke.tally.Sizes
import dk.bjarkebjarke.tally.Spacing
import dk.bjarkebjarke.tally.TallyTheme
import dk.bjarkebjarke.tally.domain.account.AccountProfile
import kotlinx.coroutines.launch

/** The Account screen: [viewModel]'s state on the stateless [AccountScreen]. */
@Composable
fun AccountRoute(
    viewModel: AccountViewModel,
    onBack: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val state by viewModel.uiState.collectAsStateWithLifecycle()
    // The view model outlives a sign-out in this activity: read the account again at every opening.
    LaunchedEffect(viewModel) { viewModel.opened() }
    val actions =
        AccountActions(
            onBack,
            viewModel::signOut,
            viewModel::signOutAnyway,
            viewModel::cancelSignOut,
            viewModel::failureShown,
        )
    AccountScreen(state, actions, modifier)
}

/**
 * Wireframe 18: who is signed in, "Sign out" and the privacy
 * link (privacy Q10). M1-19, M1-22, M1-23, M1-32 and M1-39 add their rows. The sign-out question is wireframe 39 or 45;
 * a failed sign-out is a snackbar, reported shown at once.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AccountScreen(
    state: AccountUiState,
    actions: AccountActions,
    modifier: Modifier = Modifier,
) {
    val snackbar = remember { SnackbarHostState() }
    val failure = if (state.failed) stringResource(R.string.account_sign_out_failed) else null
    val scope = rememberCoroutineScope()
    val onFailureShown by rememberUpdatedState(actions.onFailureShown)
    LaunchedEffect(failure) {
        if (failure != null) {
            scope.launch { snackbar.showSnackbar(failure) }
            onFailureShown()
        }
    }
    val uriHandler = LocalUriHandler.current
    val privacyUrl = stringResource(R.string.account_privacy_url)
    Scaffold(
        modifier,
        topBar = {
            TopAppBar(
                title = { Text(stringResource(R.string.account_title), Modifier.semantics { heading() }) },
                navigationIcon = {
                    IconButton(actions.onBack) {
                        Icon(painterResource(R.drawable.ic_arrow_back), stringResource(R.string.account_back))
                    }
                },
            )
        },
        snackbarHost = { SnackbarHost(snackbar) },
    ) { padding ->
        Column(Modifier.padding(padding)) {
            ProfileHeader(state.profile)
            HorizontalDivider()
            RowText(
                R.string.account_sign_out,
                R.string.account_sign_out_body,
                Modifier
                    .fillMaxWidth()
                    .clickable(enabled = !state.signingOut, role = Role.Button, onClick = actions.onSignOut)
                    .heightIn(min = Sizes.listRowMin)
                    .padding(horizontal = Sizes.screenGutter, vertical = Spacing.s),
            )
            RowText(
                R.string.account_privacy,
                null,
                Modifier
                    .fillMaxWidth()
                    .clickable(role = Role.Button) { openLink(uriHandler::openUri, privacyUrl) }
                    .heightIn(min = Sizes.listRowMin)
                    .padding(horizontal = Sizes.screenGutter, vertical = Spacing.s),
            )
        }
    }
    state.question?.let { SignOutQuestionDialog(it, actions) }
}

/** No browser (or a restricted profile) makes the handler throw; the screen stays as it is. */
private fun openLink(
    open: (String) -> Unit,
    url: String,
) {
    try {
        open(url)
    } catch (_: IllegalArgumentException) {
        // Nothing can open the link.
    }
}

@Composable
private fun ProfileHeader(profile: AccountProfile) {
    Row(
        Modifier.fillMaxWidth().padding(Sizes.screenGutter),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(Spacing.l),
    ) {
        Surface(Modifier.size(Sizes.minTouchTarget), CircleShape, MaterialTheme.colorScheme.primaryContainer) {
            Box(contentAlignment = Alignment.Center) {
                Text(initialOf(profile), style = MaterialTheme.typography.titleMedium)
            }
        }
        Column {
            profile.name?.let { Text(it, style = MaterialTheme.typography.titleMedium) }
            profile.email?.let {
                Text(
                    it,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    style = MaterialTheme.typography.bodyMedium,
                )
            }
        }
    }
}

/** The first letter of the name, else of the email; empty when the sign-in gave neither. */
fun initialOf(profile: AccountProfile): String =
    (profile.name ?: profile.email)?.firstOrNull { it.isLetterOrDigit() }?.uppercase().orEmpty()

@Composable
private fun RowText(
    title: Int,
    body: Int?,
    modifier: Modifier = Modifier,
) {
    val colors = MaterialTheme.colorScheme
    Column(modifier, verticalArrangement = Arrangement.Center) {
        Text(
            stringResource(title),
            color = colors.onSurface,
            style = MaterialTheme.typography.bodyLarge,
        )
        body?.let {
            Text(stringResource(it), color = colors.onSurfaceVariant, style = MaterialTheme.typography.bodyMedium)
        }
    }
}

@Composable
private fun SignOutQuestionDialog(
    question: SignOutQuestion,
    actions: AccountActions,
) {
    AlertDialog(
        onDismissRequest = actions.onCancel,
        title = { Text(stringResource(R.string.sign_out_question_title)) },
        text = {
            val text =
                when (question) {
                    SignOutQuestion.NotSentYet -> R.string.sign_out_not_sent
                    SignOutQuestion.MayNotBeSent -> R.string.sign_out_may_not_be_sent
                }
            Text(stringResource(text))
        },
        dismissButton = { TextButton(actions.onCancel) { Text(stringResource(R.string.sign_out_cancel)) } },
        confirmButton = {
            TextButton(actions.onSignOutAnyway) {
                Text(stringResource(R.string.sign_out_anyway), color = MaterialTheme.colorScheme.error)
            }
        },
    )
}

@Preview(locale = "da")
@PreviewLightDark
@PreviewFontScale
@Composable
private fun AccountScreenPreview() {
    TallyTheme {
        AccountScreen(
            AccountUiState(AccountProfile("Sam Jensen", "sam@example.com")),
            AccountActions({}, {}, {}, {}, {}),
        )
    }
}
