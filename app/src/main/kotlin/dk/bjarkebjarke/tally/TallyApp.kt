package dk.bjarkebjarke.tally

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.tooling.preview.PreviewLightDark
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.navigation3.runtime.entryProvider
import androidx.navigation3.ui.NavDisplay
import dk.bjarkebjarke.tally.home.HomeScreen
import dk.bjarkebjarke.tally.start.StartRoute
import dk.bjarkebjarke.tally.start.StartUiState
import dk.bjarkebjarke.tally.start.StartViewModel

/** The app root: collects the start-up state of [viewModel] (checklist sections 1 and 2: state hoisted to the root). */
@Composable
fun TallyApp(
    viewModel: StartViewModel,
    modifier: Modifier = Modifier,
) {
    val state by viewModel.uiState.collectAsStateWithLifecycle()
    TallyApp(state, modifier)
}

/**
 * The stateless root: one Navigation 3 [NavDisplay] whose back stack is the step the start-up gates chose (P10). A
 * changed step replaces the stack, so Back never returns to a passed gate; with one entry, system Back leaves the app.
 */
@Composable
fun TallyApp(
    state: StartUiState,
    modifier: Modifier = Modifier,
    darkTheme: Boolean = isSystemInDarkTheme(),
) {
    TallyTheme(darkTheme) {
        Surface(modifier.fillMaxSize()) {
            if (state is StartUiState.Ready) {
                val backStack = remember(state.route) { listOf(state.route) }
                NavDisplay(
                    backStack = backStack,
                    onBack = {},
                    entryProvider =
                        entryProvider {
                            entry<StartRoute.SignIn> { SignInPlaceholder() }
                            entry<StartRoute.Home> { HomeScreen() }
                        },
                )
            }
        }
    }
}

/** Sign-in until M1-16 builds wireframe 01: the app name and its tagline. */
@Composable
private fun SignInPlaceholder(modifier: Modifier = Modifier) {
    Column(
        modifier.fillMaxSize().safeDrawingPadding().padding(Sizes.screenGutter),
        verticalArrangement = Arrangement.Center,
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Text(
            stringResource(R.string.app_name),
            Modifier.semantics { heading() },
            style = MaterialTheme.typography.headlineSmall,
        )
        Text(stringResource(R.string.app_tag), textAlign = TextAlign.Center, style = MaterialTheme.typography.bodyLarge)
    }
}

@Preview(locale = "da")
@PreviewLightDark
@Composable
private fun SignInPreview() {
    TallyApp(StartUiState.Ready(StartRoute.SignIn))
}
