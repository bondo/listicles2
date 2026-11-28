package dk.bjarkebjarke.tally.domain.household

/**
 * Create a household, invite to it and join it (HH-01, HH-02, HH-03): the writes of PLAN 3.1, which the Firestore
 * rules check. Each needs a connection (SYNC-03, OQ-22), so a screen runs it through `Connectivity.whenOnline`; a write
 * that loses it on the way stays queued, and the call waits until it is sent (a cancelled call's write still goes out).
 */
interface Households {
    /** HH-01: a household named [name], trimmed (the screen checked it with `Validation.name`), owned by the caller. */
    suspend fun create(name: String): Membership

    /** HH-02: a new single-use invite to the caller's household [householdId]: its code, or null when it failed. */
    suspend fun createInvite(householdId: String): String?

    /** HH-03: the invite [code] from a link as the join screen shows it, with its own household name (P2). */
    suspend fun invite(code: String): InviteLookup

    /** HH-03: joins the household of the invite [code] in one batch that uses the invite up (PLAN 3.1 Join). */
    suspend fun join(code: String): Membership
}

/** How a create or a join ended. */
sealed interface Membership {
    data class Member(
        val householdId: String,
    ) : Membership

    /** One household per user (PLAN 3): the caller's `householdId` is set, stale or not, so nothing was written. */
    data object AlreadyInHousehold : Membership

    /** HH-03: the invite is expired, used, revoked or never made, its creator left, or its household was deleted. */
    data object InviteUnusable : Membership

    /** Signed out, no saved name (AUTH-12), or a read or the batch failed. */
    data object Failed : Membership
}

/** What the join screen shows for a code (HH-03). */
sealed interface InviteLookup {
    data class Open(
        val householdName: String,
    ) : InviteLookup

    /** Expired, used, revoked or never made, or its household was deleted: HH-03's message, and nothing to join. */
    data object Unusable : InviteLookup

    /** Signed out, or the server could not be asked. */
    data object Failed : InviteLookup
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

/**
 * An invite the rules let the caller read, as the join screen shows it: open while [expiresAtMs] is after [nowMs] (the
 * phone's clock; the join's rule then checks the server's), with its stored [householdName] (P2). The rules deny the
 * read of a used, revoked or never-made code, so only the expiry is the app's to check.
 */
fun inviteLookup(
    householdName: String?,
    expiresAtMs: Long?,
    nowMs: Long,
): InviteLookup =
    if (householdName == null || expiresAtMs == null || expiresAtMs < nowMs) { // test first: `<` is the bug
        InviteLookup.Unusable
    } else {
        InviteLookup.Open(householdName)
    }
