package dk.bjarkebjarke.tally.domain.household

/**
 * Create a household and invite to it (HH-01, HH-02): the writes of PLAN 3.1, which the Firestore rules check. Each
 * needs a connection (SYNC-03, OQ-22), so a screen runs it through `Connectivity.whenOnline`.
 */
interface Households {
    /** HH-01: a household named [name] (validated with `Validation.name`, saved trimmed), its owner the caller. */
    suspend fun create(name: String): Membership

    /** HH-02: a new single-use invite to the caller's household [householdId]: its code, or null when it failed. */
    suspend fun createInvite(householdId: String): String?
}

/** How a create (or, later, a join) ended. */
sealed interface Membership {
    data class Member(
        val householdId: String,
    ) : Membership

    /** One household per user (PLAN 3): the caller's `householdId` is set, stale or not, so nothing was written. */
    data object AlreadyInHousehold : Membership

    /** Signed out, no saved name (AUTH-12), or a read or the batch failed. */
    data object Failed : Membership
}

/**
 * A create or join as the caller's `users/{uid}` allows it: a set [householdId] stops it (one household per user), and
 * so does a missing [name] (AUTH-12); otherwise [batch] runs with the name as the new member doc's `displayName` (P9).
 */
suspend fun membership(
    householdId: String?,
    name: String?,
    batch: suspend (displayName: String) -> Membership,
): Membership =
    when {
        householdId != null -> Membership.AlreadyInHousehold
        name == null -> Membership.Failed
        else -> batch(name)
    }
