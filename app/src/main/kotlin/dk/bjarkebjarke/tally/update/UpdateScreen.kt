package dk.bjarkebjarke.tally.update

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.platform.UriHandler
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.tooling.preview.PreviewFontScale
import androidx.compose.ui.tooling.preview.PreviewLightDark
import dk.bjarkebjarke.tally.R
import dk.bjarkebjarke.tally.Sizes
import dk.bjarkebjarke.tally.Spacing
import dk.bjarkebjarke.tally.TallyTheme

/** Where new versions are published: GitHub APKs cannot be force-updated (PLAN 3). */
const val RELEASES_URL = "https://github.com/bondo/listicles2/releases"

/**
 * START-01, wireframe 41: the full-screen "Update the app" shown before sign-in when this version is below the minimum.
 * No back and no skip: it is the only step on the stack, and its only action opens the releases page.
 */
@Composable
fun UpdateScreen(modifier: Modifier = Modifier) {
    val uriHandler = LocalUriHandler.current
    Column(
        modifier.fillMaxSize().safeDrawingPadding().padding(Sizes.screenGutter),
        verticalArrangement = Arrangement.spacedBy(Spacing.l, Alignment.CenterVertically),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Text(
            stringResource(R.string.gate_update_title),
            Modifier.semantics { heading() },
            style = MaterialTheme.typography.headlineSmall,
            textAlign = TextAlign.Center,
        )
        Text(
            stringResource(R.string.gate_update_body),
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            style = MaterialTheme.typography.bodyLarge,
            textAlign = TextAlign.Center,
        )
        Button({ openReleases(uriHandler) }, Modifier.fillMaxWidth().padding(top = Spacing.s)) {
            Text(stringResource(R.string.gate_update_button))
        }
        Text(
            stringResource(R.string.gate_update_note),
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            style = MaterialTheme.typography.bodySmall,
            textAlign = TextAlign.Center,
        )
    }
}

/** No browser (or a restricted profile) makes the handler throw; this screen has no other action, so it stays up. */
private fun openReleases(uriHandler: UriHandler) {
    try {
        uriHandler.openUri(RELEASES_URL)
    } catch (_: IllegalArgumentException) {
        // Nothing can open the link: the screen stays as it is.
    }
}

@Preview(locale = "da")
@PreviewLightDark
@PreviewFontScale
@Composable
private fun UpdateScreenPreview() {
    TallyTheme { Surface(Modifier.fillMaxSize()) { UpdateScreen() } }
}
