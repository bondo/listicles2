package dk.bjarkebjarke.tally.domain.household

/**
 * Create a household, invite to it and join it (HH-01, HH-02, HH-03): the batches of PLAN 3.1, which the Firestore
 * rules check. Each needs a connection (SYNC-03, OQ-22), so a screen runs it through `Connectivity.whenOnline`.
 */
interface Households {
    /** HH-01: a household named [name] (validated with `Validation.name`, saved trimmed), its owner the caller. */
    suspend fun create(name: String): Membership

    /** HH-02: a new single-use invite to the caller's household [householdId]: its code, or null when it failed. */
    suspend fun createInvite(householdId: String): String?

    /** HH-03: joins the household of the invite [code] in one batch that uses the invite up. */
    suspend fun join(code: String): Membership
}

/** How a create or a join ended. */
sealed interface Membership {
    data class Member(
        val householdId: String,
    ) : Membership

    /**
     * One household per user (PLAN 3): the caller's `householdId` is set (HH-01 offers no create; HH-03 asks to leave
     * that household first). A stale value counts until the start-up self-heal clears it.
     */
    data object AlreadyInHousehold : Membership

    /** HH-03: the invite is expired, used, revoked or was never made, or its household was deleted. */
    data object InviteUnusable : Membership

    /** Signed out, no saved name (AUTH-12), or a read or the batch failed. */
    data object Failed : Membership
}

/** Test-first draft (M1-18): HouseholdsTest fails against it until the next commit. */
fun membershipBlocker(
    householdId: String?,
    name: String?,
): Membership? = if (householdId == name) null else Membership.Failed
