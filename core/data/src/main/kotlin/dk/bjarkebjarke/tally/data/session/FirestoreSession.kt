package dk.bjarkebjarke.tally.data.session

import com.google.firebase.firestore.FirebaseFirestore
import com.google.firebase.firestore.FirebaseFirestoreException
import dk.bjarkebjarke.tally.domain.session.LocalUserData
import kotlinx.coroutines.NonCancellable
import kotlinx.coroutines.tasks.await
import kotlinx.coroutines.withContext

/**
 * The signed-in user's Firestore instance, one per session, and its copy on the phone (PLAN 3.2; steps 1 to 3 and 6 of
 * the M1-14 sign-out). Repositories ask [firestore] at every use and never keep the instance: [clear] terminates it and
 * deletes its cache and write queue, and the first [firestore] call after that makes a new instance with [newInstance],
 * because a terminated one allows nothing but `clearPersistence`. [newInstance] is the app's only way to an instance:
 * while [clear] runs, [firestore] still answers the terminated one, so nothing opens the files again before they are
 * deleted. `SignOut` calls [awaitPendingWrites] and [clear] in turn, one sign-out at a time, so they never overlap.
 */
class FirestoreSession(
    private val newInstance: () -> FirebaseFirestore,
) : LocalUserData {
    private val lock = Any()
    private var current: FirebaseFirestore? = null

    /** For the data layer only (checklist section 1): nothing outside `:core:data` touches Firestore. */
    internal fun firestore(): FirebaseFirestore = synchronized(lock) { current ?: newInstance().also { current = it } }

    override suspend fun awaitPendingWrites(): Boolean =
        try {
            firestore().waitForPendingWrites().await()
            true
        } catch (expected: FirebaseFirestoreException) {
            // Firestore fails the wait when the signed-in user changes before the server acknowledged every write.
            false
        }

    /** No listener reports unsent writes before M2 (lists and items), so the question uses wireframe 45's text. */
    override fun unsentChangesSeen(): Boolean = false

    /**
     * Once started it finishes, also for a cancelled caller, so it never leaves a terminated instance over files it has
     * not deleted.
     */
    override suspend fun clear(): Boolean {
        val instance = firestore()
        return try {
            withContext(NonCancellable) {
                instance.terminate().await()
                instance.clearPersistence().await()
            }
            true
        } catch (expected: FirebaseFirestoreException) {
            // The files could not be deleted; the next try starts from a new instance.
            false
        } finally {
            drop(instance)
        }
    }

    private fun drop(instance: FirebaseFirestore) {
        synchronized(lock) { if (current === instance) current = null }
    }
}
