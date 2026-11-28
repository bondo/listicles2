package dk.bjarkebjarke.tally.data.config

import com.google.firebase.firestore.FirebaseFirestoreException
import dk.bjarkebjarke.tally.data.session.FirestoreSession
import dk.bjarkebjarke.tally.domain.config.MinVersionRemote
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.tasks.await

/**
 * M1-82: `config/app.minVersionCode` with one `get()`, allowed signed out by the rules (START-01). A missing document
 * or field is a success of `null`; anything else that goes wrong is a failed [Result], never a throw.
 */
class FirestoreMinVersionRemote(
    private val session: FirestoreSession,
) : MinVersionRemote {
    override suspend fun fetch(): Result<Long?> =
        try {
            val snapshot =
                session
                    .firestore()
                    .document(CONFIG_PATH)
                    .get()
                    .await()
            val value = snapshot.get(FIELD)
            Result.success(value?.let { it as? Long ?: error("$FIELD is not a whole number") })
        } catch (expected: CancellationException) {
            throw expected
        } catch (expected: FirebaseFirestoreException) {
            Result.failure(expected)
        } catch (expected: IllegalStateException) {
            // A terminated instance (a sign-out clearing the session) or a field of the wrong type.
            Result.failure(expected)
        }

    private companion object {
        const val CONFIG_PATH = "config/app"
        const val FIELD = "minVersionCode"
    }
}
