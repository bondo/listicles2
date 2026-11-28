package dk.bjarkebjarke.tally.domain.household

import java.security.SecureRandom

/**
 * Invite codes and their expiry (PLAN 3.1 Create invite, P3, #243). A code is `<householdId>_<secret>`: the household's
 * 20-character auto-id and 22 characters of `[A-Za-z0-9_-]` from a secure random source (132 bits). The rules accept
 * an expiry up to 7 days after the server's time; the app stays a margin inside, so a phone clock up to an hour fast
 * is not refused.
 */
object Invites {
    /** 7 days minus the 1-hour margin. */
    const val LIFETIME_MS = (7 * 24 - 1) * 60 * 60 * 1000L

    private const val SECRET_LENGTH = 22
    private const val SECRET_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"

    fun newCode(
        householdId: String,
        random: SecureRandom,
    ): String {
        val secret = CharArray(SECRET_LENGTH) { SECRET_ALPHABET[random.nextInt(SECRET_ALPHABET.length)] }
        return "${householdId}_${String(secret)}"
    }

    fun expiresAt(nowMs: Long): Long = nowMs + LIFETIME_MS
}
