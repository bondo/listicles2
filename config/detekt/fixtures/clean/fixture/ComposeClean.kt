package fixture

import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier

@Composable
fun Greeting(
    name: String,
    modifier: Modifier = Modifier,
) {
    Text("hello $name", modifier = modifier)
}

@Composable
fun NameList(
    names: List<String>,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Text(names.joinToString(), modifier = modifier)
    onClick()
}
