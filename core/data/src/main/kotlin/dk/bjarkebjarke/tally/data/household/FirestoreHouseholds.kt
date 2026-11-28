package dk.bjarkebjarke.tally.data.household

import com.google.android.gms.tasks.Task
import com.google.android.gms.tasks.Tasks
import com.google.firebase.Timestamp
import com.google.firebase.auth.FirebaseAuth
import com.google.firebase.firestore.FieldValue
import com.google.firebase.firestore.FirebaseFirestoreException
import com.google.firebase.firestore.Source
import dk.bjarkebjarke.tally.data.session.FirestoreSession
import dk.bjarkebjarke.tally.domain.Validation
import dk.bjarkebjarke.tally.domain.household.Households
import dk.bjarkebjarke.tally.domain.household.InviteLookup
import dk.bjarkebjarke.tally.domain.household.Invites
import dk.bjarkebjarke.tally.domain.household.Membership
import dk.bjarkebjarke.tally.domain.household.membership
import kotlinx.coroutines.tasks.await
import java.security.SecureRandom
import java.util.Date

/**
 * [Households] over Firestore (M1-18): the writes of PLAN 3.1 as the rules accept them (M1-10 create household, M1-12
 * create invite), for the user Firebase Auth has signed in, on [session]'s instance (M1-67). The reads a write depends
 * on come from the server, so a call made offline fails before anything is queued.
 */
class FirestoreHouseholds(
    private val session: FirestoreSession,
    private val auth: FirebaseAuth,
    private val random: SecureRandom = SecureRandom(),
    private val clock: () -> Long = System::currentTimeMillis,
) : Households {
    /**
     * One batch: the household under a Firestore auto-id (P3), the caller's owner member doc (P1) with the
     * `displayName` copied from `users/{uid}.name` (P9), and `users/{uid}` set to it (the one-household check), as
     * [membership] allows.
     */
    override suspend fun create(name: String): Membership {
        val uid = auth.currentUser?.uid ?: return Membership.Failed
        val db = session.firestore()
        return try {
            val user = started { db.document("users/$uid").get(Source.SERVER) }.await()
            membership(user.getString(HOUSEHOLD_ID), user.getString("name")) { displayName ->
                val household = db.collection(HOUSEHOLDS).document()
                val fields = mapOf("createdBy" to uid, "createdAt" to NOW, "ownerUid" to uid, "deleted" to false)
                val owner = mapOf("role" to "owner", "displayName" to displayName, "joinedAt" to NOW)
                started {
                    db
                        .batch()
                        .set(household, fields + ("name" to Validation.normalizedName(name)))
                        .set(household.collection("members").document(uid), owner)
                        .update(user.reference, HOUSEHOLD_ID, household.id)
                        .commit()
                }.await()
                Membership.Member(household.id)
            }
        } catch (expected: FirebaseFirestoreException) {
            Membership.Failed
        }
    }

    /** The household's name copied from the server (P2), created now by the caller, expiring as [Invites] says. */
    override suspend fun createInvite(householdId: String): String? {
        val uid = auth.currentUser?.uid ?: return null
        val db = session.firestore()
        return try {
            val household = started { db.document("$HOUSEHOLDS/$householdId").get(Source.SERVER) }.await()
            val code = Invites.newCode(householdId, random)
            val expiresAt = Timestamp(Date(Invites.expiresAt(clock())))
            val invite = mapOf(HOUSEHOLD_ID to householdId, "createdBy" to uid, "expiresAt" to expiresAt)
            val fields = invite + mapOf("createdAt" to NOW, "householdName" to household.getString("name"))
            started { db.document("invites/$code").set(fields) }.await()
            code
        } catch (expected: FirebaseFirestoreException) {
            null
        }
    }

    // Test first: stubs until M1-100's next commits.
    override suspend fun invite(code: String): InviteLookup =
        if (Invites.isWellFormed(code)) InviteLookup.Failed else InviteLookup.Unusable

    override suspend fun join(code: String): Membership =
        if (Invites.isWellFormed(code)) Membership.Failed else Membership.InviteUnusable

    /**
     * The task [call] starts. While a sign-out's `clear()` runs, [session] still answers its terminated instance, whose
     * calls throw IllegalStateException (FirestoreSession): the task then fails as a Firestore error. Only the call is
     * guarded, never `await()`: a CancellationException is an IllegalStateException too, and it must go on.
     */
    private fun <T> started(call: () -> Task<T>): Task<T> =
        try {
            call()
        } catch (expected: IllegalStateException) {
            val terminated = FirebaseFirestoreException("terminated", FirebaseFirestoreException.Code.ABORTED, expected)
            Tasks.forException(terminated)
        }

    private companion object {
        const val HOUSEHOLDS = "households"
        const val HOUSEHOLD_ID = "householdId"

        /** The server's time of the write, which the rules compare with `request.time`. */
        val NOW: FieldValue = FieldValue.serverTimestamp()
    }
}
