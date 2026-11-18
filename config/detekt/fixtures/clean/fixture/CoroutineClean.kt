package fixture

import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

fun startWork(scope: CoroutineScope) {
    scope.launch { }
}

suspend fun loadOn(dispatcher: CoroutineDispatcher) {
    withContext(dispatcher) { }
}
