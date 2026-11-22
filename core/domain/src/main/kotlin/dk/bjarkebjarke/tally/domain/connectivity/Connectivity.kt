package dk.bjarkebjarke.tally.domain.connectivity

/** Whether the phone can reach the server right now. Actions that need the server check it first (SYNC-03). */
fun interface Connectivity {
    fun isOnline(): Boolean
}

/** The outcome of an action that needs a connection: its value, or "This needs a connection" (SYNC-03). */
sealed interface ConnectionResult<out T> {
    data class Done<out T>(
        val value: T,
    ) : ConnectionResult<T>

    data object NeedsConnection : ConnectionResult<Nothing>
}

/** Runs [action] only when online, checked at every call; offline it returns [ConnectionResult.NeedsConnection]. */
inline fun <T> Connectivity.whenOnline(action: () -> T): ConnectionResult<T> =
    ConnectionResult.Done(action()) // stub until the implementation commit: ignores the connection
