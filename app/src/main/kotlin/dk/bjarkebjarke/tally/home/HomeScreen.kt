package dk.bjarkebjarke.tally.home

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.tooling.preview.PreviewFontScale
import androidx.compose.ui.tooling.preview.PreviewLightDark
import dk.bjarkebjarke.tally.EmptyStateBubble
import dk.bjarkebjarke.tally.EmptyStateIcon
import dk.bjarkebjarke.tally.R
import dk.bjarkebjarke.tally.Spacing
import dk.bjarkebjarke.tally.TallyTheme

/**
 * The M1 home (Q1 A, see #194): the Lists screen of wireframe 02 in its empty state, without "Create list"; M2 fills
 * it. The top bar's household icon comes with the household screen (M1-19) and the avatar with Account (M1-25), so no
 * button here leads nowhere.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun HomeScreen(modifier: Modifier = Modifier) {
    Scaffold(
        modifier,
        topBar = { TopAppBar(title = { Text(stringResource(R.string.lists_title)) }) },
    ) { padding ->
        Column(
            Modifier.fillMaxSize().padding(padding).padding(horizontal = Spacing.xxl, vertical = Spacing.xl),
            verticalArrangement = Arrangement.spacedBy(Spacing.m, Alignment.CenterVertically),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Surface(
                Modifier.padding(bottom = Spacing.s).size(EmptyStateBubble),
                shape = CircleShape,
                color = MaterialTheme.colorScheme.secondaryContainer,
            ) {
                Box(contentAlignment = Alignment.Center) {
                    Icon(painterResource(R.drawable.ic_checklist), null, Modifier.size(EmptyStateIcon))
                }
            }
            Text(
                stringResource(R.string.lists_empty_title),
                Modifier.semantics { heading() },
                style = MaterialTheme.typography.titleLarge,
                textAlign = TextAlign.Center,
            )
            Text(
                stringResource(R.string.lists_empty_body),
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                style = MaterialTheme.typography.bodyMedium,
                textAlign = TextAlign.Center,
            )
        }
    }
}

@Preview(locale = "da")
@PreviewLightDark
@PreviewFontScale
@Composable
private fun HomeScreenPreview() {
    TallyTheme { HomeScreen() }
}
