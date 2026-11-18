package fixture

import kotlinx.coroutines.GlobalScope
import kotlinx.coroutines.launch

// GlobalCoroutineUsage: work that outlives its caller needs an injected scope.
fun startWork() {
    GlobalScope.launch { }
}
