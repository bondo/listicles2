package dk.bjarkebjarke.tally.domain.session

import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.flow.catch
import kotlinx.coroutines.flow.conflate
import kotlinx.coroutines.launch
import java.util.concurrent.atomic.AtomicBoolean

/**
 * Deletes the copy on the phone ([LocalUserData.clear]) whenever nobody is signed in (#357, privacy section 2), whoever
 * ended the session. [SignOut] deletes it before it signs out of Firebase, so this clear then finds nothing left; but
 * Firebase also signs out by itself when it cannot refresh the session's token (the account was disabled or deleted,
 * or its password changed on another phone), and without this the copy would stay, shared with the next account that
 * signs in on the phone.
 *
 * A signed-out start clears too: a copy that a stopped process left behind goes before anyone signs in. A clear that
 * fails is tried again only at the next signed-out state, so an account that signs in before then still finds the copy.
 * One clear at a time; when it ends, only the latest of the states that came meanwhile counts (conflated). Nothing is
 * written to the copy while a clear runs, so a session that came and went needs one more clear at most, and a sign-out
 * that a sign-in followed never reaches the live session's copy. A failing session counts as signed out, as at the
 * start-up root, and ends the watch.
 */
class SignedOutCleanup(
    private val session: SessionState,
    private val userData: LocalUserData,
    private val externalScope: CoroutineScope,
) {
    private val started = AtomicBoolean(false)

    /**
     * Watches in [externalScope], an application-wide scope, for the rest of the process. Only the first call starts
     * it: MainActivity calls it at every creation, once its start-up root is ready (M1-89).
     */
    fun start() {
        if (started.compareAndSet(false, true)) externalScope.launch { watch() }
    }

    private suspend fun watch() =
        session
            .signedIn()
            .catch { emit(false) }
            .conflate()
            .collect { signedIn -> if (!signedIn) userData.clear() }
}
