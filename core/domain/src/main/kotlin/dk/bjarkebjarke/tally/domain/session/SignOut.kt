package dk.bjarkebjarke.tally.domain.session

import dk.bjarkebjarke.tally.domain.connectivity.Connectivity
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.async
import kotlinx.coroutines.withTimeoutOrNull

/**
 * Sign out (AUTH-03; OQ-13, decided 2026-11-17; docs/milestones/M1.md, M1-14), in this order:
 * 1. online ([Connectivity]), wait at most [pendingWritesTimeoutMs] for the server to acknowledge every pending write.
 *    Whenever that wait does not complete (offline, timeout or a failed wait), ask first
 *    ([SignOutResult.ConfirmUnsentChanges]): the write queue survives without any listener, so what listeners saw
 *    picks only the wording;
 * 2. and 3. [LocalUserData.clear]: Firestore `terminate`, then `clearPersistence`;
 * 4. [Authentication.signOut], only after step 3 has finished, and never when it failed;
 * 5. [GoogleCredentials.clearCredentialState], as Google asks at every sign-out;
 * 6. the data layer makes a new Firestore instance at the next use (the next sign-in).
 *
 * Steps 2 to 5 run in [externalScope], an application-wide scope with a `SupervisorJob`: once started they finish even
 * when the screen that asked goes away, which signing out itself causes. M1-32 ends account deletion through
 * [discardingUnsentChanges]. The screen disables "Sign out" while one runs (M1-25); a new screen can still start one
 * while the previous one's steps 2 and 3 run, and [LocalUserData.awaitPendingWrites] then answers a failed wait. One
 * started after step 3 runs the steps again, on a new Firestore instance. [SignedOutCleanup] clears again after step 4,
 * and is what clears when Firebase signs out by itself (M1-89).
 */
class SignOut(
    private val connectivity: Connectivity,
    private val userData: LocalUserData,
    private val authentication: Authentication,
    private val credentials: GoogleCredentials,
    private val externalScope: CoroutineScope,
    private val pendingWritesTimeoutMs: Long = PENDING_WRITES_TIMEOUT_MS,
) {
    /** "Sign out": steps 1 to 6, or the question when the pending writes were not all acknowledged in time. */
    suspend operator fun invoke(): SignOutResult {
        val allSent =
            connectivity.isOnline() &&
                withTimeoutOrNull(pendingWritesTimeoutMs) { userData.awaitPendingWrites() } == true
        if (allSent) return discardingUnsentChanges()
        return SignOutResult.ConfirmUnsentChanges(userData.unsentChangesSeen())
    }

    /** "Sign out anyway": steps 2 to 6, whatever was not sent yet. */
    suspend fun discardingUnsentChanges(): SignOutResult =
        externalScope
            .async {
                if (!userData.clear()) return@async SignOutResult.Failed
                authentication.signOut()
                credentials.clearCredentialState()
                SignOutResult.SignedOut
            }.await()

    companion object {
        /** How long sign-out waits, online, for the server to acknowledge the pending writes. */
        const val PENDING_WRITES_TIMEOUT_MS = 5_000L
    }
}

/**
 * The signed-in user's data on this phone: Firestore's offline cache and its write queue (PLAN 3.2), and every other
 * store the app keeps there for the account (M1-101's household-name copy, M1-25's last-opened times). [clear] deletes
 * them all: it is all that runs when Firebase signs out by itself ([SignedOutCleanup]). An implementation throws
 * nothing but `CancellationException`.
 */
interface LocalUserData {
    /** Suspends until the server has acknowledged every write made before the call; false when the wait failed. */
    suspend fun awaitPendingWrites(): Boolean

    /** Whether an active listener's latest snapshot had a write not yet sent. Picks the question's wording only. */
    fun unsentChangesSeen(): Boolean

    /**
     * Deletes the cache and the write queue (Firestore terminate, then clearPersistence); false when it could not.
     * Nothing is written to the copy while it runs. [SignOut] calls it, and [SignedOutCleanup] whenever nobody is
     * signed in: also with nothing left to delete, and while another clear runs.
     */
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
