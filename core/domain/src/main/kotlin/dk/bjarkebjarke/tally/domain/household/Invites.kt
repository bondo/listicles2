package dk.bjarkebjarke.tally.domain.household

import java.security.SecureRandom

/** Test-first draft (M1-18): InvitesTest fails against it until the next commit. */
object Invites {
    const val LIFETIME_MS = 0L

    fun newCode(
        householdId: String,
        random: SecureRandom,
    ): String = householdId + random.nextInt()

    fun isWellFormed(code: String): Boolean = code.isNotEmpty()

    fun householdId(code: String): String = code

    fun expiresAt(nowMs: Long): Long = nowMs
}
