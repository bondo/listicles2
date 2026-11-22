package dk.bjarkebjarke.tally.domain

enum class EmailError { Empty }

enum class PasswordError { TooShort }

enum class NameError { Empty, TooLong }

/**
 * Input rules for sign-up and profile fields (M1-13). Lengths are counted in Unicode code points,
 * not UTF-16 chars, as the Firestore rules count them: with a regex, because their `size()` counts
 * UTF-16 units (docs/milestones/M1.md P4).
 * Callers show the matching field error; the texts live in resources, not here.
 */
object Validation {
    const val MIN_PASSWORD_CODE_POINTS = 12
    const val MAX_NAME_CODE_POINTS = 50

    /** Trimmed and non-empty only: Firebase decides whether an address is valid (AUTH-10). */
    fun email(raw: String): EmailError? = if (normalizedEmail(raw).isEmpty()) EmailError.Empty else null

    /** The value to send to Firebase. */
    fun normalizedEmail(raw: String): String = raw.trim()

    /** 12 or more code points and no other rule (OQ-26); the password is never trimmed. */
    fun password(raw: String): PasswordError? =
        if (codePoints(raw) < MIN_PASSWORD_CODE_POINTS) PasswordError.TooShort else null

    /** 1 to 50 code points after trimming. */
    fun name(raw: String): NameError? {
        val count = codePoints(normalizedName(raw))
        return when {
            count == 0 -> NameError.Empty
            count > MAX_NAME_CODE_POINTS -> NameError.TooLong
            else -> null
        }
    }

    /** The value to save: exactly what [name] validated, so the stored name never exceeds 50 code points. */
    fun normalizedName(raw: String): String = raw.trim()

    private fun codePoints(s: String): Int = s.codePointCount(0, s.length)
}
