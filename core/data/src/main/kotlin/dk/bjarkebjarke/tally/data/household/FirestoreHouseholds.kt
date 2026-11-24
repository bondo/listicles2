package dk.bjarkebjarke.tally.data.household

import com.google.firebase.auth.FirebaseAuth
import dk.bjarkebjarke.tally.data.session.FirestoreSession
import dk.bjarkebjarke.tally.domain.household.Households
import dk.bjarkebjarke.tally.domain.household.Membership

/** Test-first draft (M1-18): HouseholdsEmulatorTest fails against it until the implementation commit. */
class FirestoreHouseholds(
    session: FirestoreSession,
    auth: FirebaseAuth,
    clock: () -> Long = System::currentTimeMillis,
) : Households {
    private val draft = listOf(session, auth, clock)

    override suspend fun create(name: String): Membership = Membership.Failed

    override suspend fun createInvite(householdId: String): String? = draft.firstOrNull { it == householdId } as? String

    override suspend fun join(code: String): Membership = Membership.Failed
}
