package dk.bjarkebjarke.tally.domain

enum class EmailError { Empty }

enum class PasswordError { TooShort }

enum class NameError { Empty, TooLong }

/**
 * Input rules for sign-up and profile fields (M1-13). Lengths are counted in Unicode code points,
 * not UTF-16 chars, as the Firestore rules count them: with a regex, because their `size()` counts
 * UTF-16 units (docs/milestones/M1.md P4). A name is blank as PLAN 3.1 field validation defines it
 * for the rules as well (M1-90).
 * Callers show the matching field error; the texts live in resources, not here.
 */
object Validation {
    const val MIN_PASSWORD_CODE_POINTS = 12
    const val MAX_NAME_CODE_POINTS = 50

    // The blank code points of a name (PLAN 3.1 P4, M1-90): U+0000 to U+0020, which the rules' trim() strips, and
    // Unicode White_Space above them. The rules' validName refuses a name of these alone, so the app and the rules
    // accept the same names. All are in the BMP, so no char of a surrogate pair is one.
    private const val LAST_TRIMMED = 0x20
    private val WHITE_SPACE: Set<Int> =
        (listOf('\u0085', '\u00A0', '\u1680', '\u2028', '\u2029', '\u202F', '\u205F', '\u3000') + ('\u2000'..'\u200A'))
            .map { it.code }
            .toSet()

    /** Trimmed and non-empty only: Firebase decides whether an address is valid (AUTH-10). */
    fun email(raw: String): EmailError? = if (normalizedEmail(raw).isEmpty()) EmailError.Empty else null

    /** The value to send to Firebase. */
    fun normalizedEmail(raw: String): String = raw.trim()

    /** 12 or more code points and no other rule (OQ-26); the password is never trimmed. */
    fun password(raw: String): PasswordError? =
        if (codePoints(raw) < MIN_PASSWORD_CODE_POINTS) PasswordError.TooShort else null

    /** 1 to 50 code points once the blank code points at either end are removed ([normalizedName]). */
    fun name(raw: String): NameError? {
        val count = codePoints(normalizedName(raw))
        return when {
            count == 0 -> NameError.Empty
            count > MAX_NAME_CODE_POINTS -> NameError.TooLong
            else -> null
        }
    }

    /**
     * The value to save: [raw] without the blank code points at either end, exactly what [name] validated, so the
     * stored name is never blank and never exceeds 50 code points.
     */
    fun normalizedName(raw: String): String = raw.trim { isBlank(it.code) }

    private fun isBlank(codePoint: Int): Boolean = codePoint <= LAST_TRIMMED || codePoint in WHITE_SPACE

    private fun codePoints(s: String): Int = s.codePointCount(0, s.length)
}
