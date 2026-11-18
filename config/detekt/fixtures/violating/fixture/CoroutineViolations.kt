package fixture

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.GlobalScope
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

// GlobalCoroutineUsage: work that outlives its caller needs an injected scope.
fun startWork() {
    GlobalScope.launch { }
}

// InjectDispatcher: dispatchers are injected so tests can replace them.
suspend fun loadOnIo() {
    withContext(Dispatchers.IO) { }
}
