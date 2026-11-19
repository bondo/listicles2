package fixture

import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier

// A stateless screen keeps explicit event lambdas (state hoisting), so LongParameterList ignores @Composable.
@Composable
fun StatelessScreen(
    title: String,
    subtitle: String,
    items: List<String>,
    onAdd: () -> Unit,
    onRemove: (String) -> Unit,
    onRename: (String) -> Unit,
    onShare: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Text(title + subtitle + items.joinToString(), modifier = modifier)
    onAdd()
    onRemove(title)
    onRename(subtitle)
    onShare()
}
