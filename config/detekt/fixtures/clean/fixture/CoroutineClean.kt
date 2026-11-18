package fixture

import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.launch

fun startWork(scope: CoroutineScope) {
    scope.launch { }
}
