package dk.bjarkebjarke.tally.domain.session

import dk.bjarkebjarke.tally.domain.connectivity.Connectivity
import kotlinx.coroutines.CoroutineScope

/** Sign out (AUTH-03, OQ-13). Naive first draft (no wait, wrong order) so the tests compile and fail. */
class SignOut(
    private val connectivity: Connectivity,
    private val userData: LocalUserData,
    private val authentication: Authentication,
    private val credentials: GoogleCredentials,
    private val externalScope: CoroutineScope,
    private val pendingWritesTimeoutMs: Long = PENDING_WRITES_TIMEOUT_MS,
) {
    suspend operator fun invoke(): SignOutResult = discardingUnsentChanges()

    suspend fun discardingUnsentChanges(): SignOutResult {
        authentication.signOut()
        userData.clear()
        return SignOutResult.SignedOut.also { listOf(connectivity, credentials, externalScope, pendingWritesTimeoutMs) }
    }

    companion object {
        /** How long sign-out waits, online, for the server to acknowledge the pending writes. */
        const val PENDING_WRITES_TIMEOUT_MS = 5_000L
    }
}

/**
 * The signed-in user's data on this phone: Firestore's offline cache and its write queue (PLAN 3.2). M1-18 adds the
 * app's household-name copy to [clear]. An implementation throws nothing but `CancellationException`.
 */
interface LocalUserData {
    /** Suspends until the server has acknowledged every write made before the call; false when the wait failed. */
    suspend fun awaitPendingWrites(): Boolean

    /** Whether an active listener's latest snapshot had a write not yet sent. Picks the question's wording only. */
    fun unsentChangesSeen(): Boolean

    /** Deletes the cache and the write queue (Firestore terminate, then clearPersistence); false when it could not. */
    suspend fun clear(): Boolean
}

/** How a sign-out ended. */
sealed interface SignOutResult {
    /** Signed out: no session, no copy of the user's data and no credential state is left on the phone. */
    data object SignedOut : SignOutResult

    /**
     * Still signed in: some changes may not have reached the server, so ask first (AUTH-03). [unsentChangesSeen] picks
     * the text: wireframe 39 ("Some changes have not been sent yet") when true, wireframe 45 ("may not have been sent")
     * when false. "Sign out anyway" calls [SignOut.discardingUnsentChanges]; "Cancel" calls nothing.
     */
    data class ConfirmUnsentChanges(
        val unsentChangesSeen: Boolean,
    ) : SignOutResult

    /** The copy on the phone could not be deleted, so the user is still signed in and can try again. */
    data object Failed : SignOutResult
}
