package fixture

import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.withContext

suspend fun loadOn(dispatcher: CoroutineDispatcher) {
    withContext(dispatcher) { }
}
