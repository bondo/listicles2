package dk.bjarkebjarke.tally.data.household

import com.google.firebase.Timestamp
import com.google.firebase.auth.FirebaseAuth
import com.google.firebase.firestore.FieldValue
import com.google.firebase.firestore.FirebaseFirestore
import com.google.firebase.firestore.FirebaseFirestoreException
import com.google.firebase.firestore.Source
import com.google.firebase.firestore.WriteBatch
import dk.bjarkebjarke.tally.data.session.FirestoreSession
import dk.bjarkebjarke.tally.domain.Validation
import dk.bjarkebjarke.tally.domain.household.Households
import dk.bjarkebjarke.tally.domain.household.Invites
import dk.bjarkebjarke.tally.domain.household.Membership
import dk.bjarkebjarke.tally.domain.household.membership
import kotlinx.coroutines.tasks.await
import java.security.SecureRandom
import java.util.Date

/**
 * [Households] over Firestore (M1-18): the batches of PLAN 3.1 in the shape the rules accept (M1-10 create household,
 * M1-12 create invite, M1-54 join), as the user Firebase Auth has signed in, on [session]'s instance (M1-67). Each
 * reads from the server first, so offline it fails before anything is queued.
 */
class FirestoreHouseholds(
    private val session: FirestoreSession,
    private val auth: FirebaseAuth,
    private val random: SecureRandom = SecureRandom(),
    private val clock: () -> Long = System::currentTimeMillis,
) : Households {
    override suspend fun create(name: String): Membership {
        val db = session.firestore()
        val household = db.collection(HOUSEHOLDS).document() // a Firestore auto-id (P3)
        return becomeMember(db, household.id, refused = Membership.Failed) { uid, displayName ->
            val fields =
                mapOf(
                    NAME to Validation.normalizedName(name),
                    "createdBy" to uid,
                    "createdAt" to FieldValue.serverTimestamp(),
                    "ownerUid" to uid,
                    "deleted" to false,
                )
            val owner =
                mapOf(
                    "role" to "owner",
                    "displayName" to displayName,
                    "joinedAt" to FieldValue.serverTimestamp(),
                )
            set(household, fields).set(household.collection(MEMBERS).document(uid), owner)
        }
    }

    override suspend fun join(code: String): Membership {
        if (!Invites.isWellFormed(code)) return Membership.InviteUnusable
        val db = session.firestore()
        val householdId = Invites.householdId(code)
        // Refused: the invite was used, revoked or expired, its creator left, or the household was deleted.
        return becomeMember(db, householdId, refused = Membership.InviteUnusable) { uid, displayName ->
            val member =
                mapOf(
                    "role" to "member",
                    "displayName" to displayName,
                    "joinedAt" to FieldValue.serverTimestamp(),
                    "viaInvite" to code,
                )
            set(
                db
                    .collection(HOUSEHOLDS)
                    .document(householdId)
                    .collection(MEMBERS)
                    .document(uid),
                member,
            ).delete(db.collection(INVITES).document(code))
        }
    }

    override suspend fun createInvite(householdId: String): String? {
        val uid = auth.currentUser?.uid ?: return null
        val db = session.firestore()
        return try {
            val household =
                db
                    .collection(HOUSEHOLDS)
                    .document(householdId)
                    .get(Source.SERVER)
                    .await()
            val code = Invites.newCode(householdId, random)
            val invite =
                mapOf(
                    HOUSEHOLD_ID to householdId,
                    "householdName" to household.getString(NAME),
                    "createdBy" to uid,
                    "createdAt" to FieldValue.serverTimestamp(),
                    "expiresAt" to Timestamp(Date(Invites.expiresAt(clock()))),
                )
            db
                .collection(INVITES)
                .document(code)
                .set(invite)
                .await()
            code
        } catch (expected: FirebaseFirestoreException) {
            null
        }
    }

    /**
     * The create-household and join batches (PLAN 3.1): what [writes] adds for the caller's uid and name (P9), and the
     * caller's `users/{uid}` set to [householdId] (the one-household check). [refused] is a denied batch's result.
     */
    private suspend fun becomeMember(
        db: FirebaseFirestore,
        householdId: String,
        refused: Membership,
        writes: WriteBatch.(uid: String, displayName: String) -> WriteBatch,
    ): Membership {
        val uid = auth.currentUser?.uid ?: return Membership.Failed
        return try {
            val user =
                db
                    .collection(USERS)
                    .document(uid)
                    .get(Source.SERVER)
                    .await()
            membership(user.getString(HOUSEHOLD_ID), user.getString(NAME)) { displayName ->
                db
                    .batch()
                    .writes(uid, displayName)
                    .update(user.reference, HOUSEHOLD_ID, householdId)
                    .commit()
                    .await()
                Membership.Member(householdId)
            }
        } catch (expected: FirebaseFirestoreException) {
            if (expected.code == FirebaseFirestoreException.Code.PERMISSION_DENIED) refused else Membership.Failed
        }
    }

    private companion object {
        const val USERS = "users"
        const val HOUSEHOLDS = "households"
        const val MEMBERS = "members"
        const val INVITES = "invites"
        const val HOUSEHOLD_ID = "householdId"
        const val NAME = "name"
    }
}
