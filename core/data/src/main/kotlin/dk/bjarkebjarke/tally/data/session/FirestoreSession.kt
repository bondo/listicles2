package dk.bjarkebjarke.tally.data.session

import com.google.firebase.firestore.FirebaseFirestore
import dk.bjarkebjarke.tally.domain.session.LocalUserData

/** Test-first draft (M1-67): keeps no instance, never waits and clears nothing; the next commit implements it. */
class FirestoreSession(
    private val newInstance: () -> FirebaseFirestore,
) : LocalUserData {
    fun firestore(): FirebaseFirestore = newInstance()

    override suspend fun awaitPendingWrites(): Boolean = false

    override fun unsentChangesSeen(): Boolean = false

    override suspend fun clear(): Boolean = false
}
