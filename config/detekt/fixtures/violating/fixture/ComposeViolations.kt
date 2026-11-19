package fixture

import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.MutableState
import androidx.compose.ui.Modifier

// ModifierMissing: a public composable that emits UI has no modifier parameter.
@Composable
fun Greeting() {
    Text("hello")
}

// ComposableNaming: a composable that emits UI must be PascalCase.
@Composable
fun greetingLabel(modifier: Modifier = Modifier) {
    Text("hello", modifier = modifier)
}

// MutableStateParam: state is passed as a value and an event callback, not as MutableState.
@Composable
fun Counter(
    count: MutableState<Int>,
    modifier: Modifier = Modifier,
) {
    Text("${count.value}", modifier = modifier)
}

// ParameterNaming: event callbacks are present tense (onClick), not past tense.
@Composable
fun Tapper(
    onClicked: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Text("tap", modifier = modifier)
}

// ComposableParamOrder: required parameters come before the modifier.
@Composable
fun Ordered(
    modifier: Modifier = Modifier,
    title: String,
) {
    Text(title, modifier = modifier)
}
