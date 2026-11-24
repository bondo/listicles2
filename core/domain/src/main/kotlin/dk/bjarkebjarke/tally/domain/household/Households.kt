package dk.bjarkebjarke.tally.domain.household

/**
 * Create, invite, revoke and join (HH-01, HH-02, HH-03): the writes of PLAN 3.1, which the Firestore rules check. Each
 * needs a connection (SYNC-03, OQ-22), so a screen runs it through `Connectivity.whenOnline`. A member's name in the
 * household is a copy of their `users/{uid}.name` (AUTH-12, P9), which the name step saved before the home opened.
 * An implementation throws nothing but `CancellationException`.
 */
interface Households {
    /** HH-01: a household named [name] (validated with `Validation.name`, saved trimmed), its owner the caller. */
    suspend fun create(name: String): Membership

    /** HH-02: a new single-use invite to the caller's household [householdId]; its code, or null when it failed. */
    suspend fun createInvite(householdId: String): String?

    /** HH-02: its creator or the household owner revokes the invite; false when the server refused or it was gone. */
    suspend fun revokeInvite(code: String): Boolean

    /** HH-03: the invite as the join screen shows it: its own household name (P2), never a name from the link. */
    suspend fun invite(code: String): InviteLookup

    /** HH-03: joins the household of [code] in one batch that uses the invite up. */
    suspend fun join(code: String): Membership
}

/** How a create or a join ended. */
sealed interface Membership {
    data class Member(
        val householdId: String,
    ) : Membership

    /**
     * One household per user (PLAN 3): the caller's `householdId` is set, so nothing was written (HH-01 offers no
     * create; HH-03 says to leave that household first). A stale value counts until the start-up self-heal clears it.
     */
    data object AlreadyInHousehold : Membership

    /** HH-03: the invite is expired, used, revoked or was never made, or its household was deleted. */
    data object InviteUnusable : Membership

    /** A read or the batch failed, or the caller has no saved name; nothing was written. */
    data object Failed : Membership
}

/** What the join screen shows for a code (HH-03). */
sealed interface InviteLookup {
    data class Open(
        val householdName: String,
    ) : InviteLookup

    /** Expired, used, revoked or never made, or its household was deleted: HH-03's message, and nothing to join. */
    data object Unusable : InviteLookup

    /** The server could not be asked. */
    data object Failed : InviteLookup
}
