package dk.bjarkebjarke.tally.domain

enum class EmailError { Empty }

enum class PasswordError { TooShort }

enum class NameError { Empty, TooLong }

/** Naive first draft (UTF-16 length, no trimming) so the tests compile and fail; the real rules follow. */
object Validation {
    const val MIN_PASSWORD_CODE_POINTS = 12
    const val MAX_NAME_CODE_POINTS = 50

    fun email(raw: String): EmailError? = if (raw.isEmpty()) EmailError.Empty else null

    fun normalizedEmail(raw: String): String = raw

    fun password(raw: String): PasswordError? =
        if (raw.length < MIN_PASSWORD_CODE_POINTS) PasswordError.TooShort else null

    fun name(raw: String): NameError? =
        when {
            raw.isEmpty() -> NameError.Empty
            raw.length > MAX_NAME_CODE_POINTS -> NameError.TooLong
            else -> null
        }
}
