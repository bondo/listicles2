package fixture

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

// InjectDispatcher: dispatchers are injected so tests can replace them (needs type resolution).
suspend fun loadOnIo() {
    withContext(Dispatchers.IO) { }
}
