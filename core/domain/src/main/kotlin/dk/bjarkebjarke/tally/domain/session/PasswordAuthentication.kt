package dk.bjarkebjarke.tally.domain.session

/**
 * Firebase Authentication's email and password calls (M1.md, M1-15); M1-99 implements them. Throws nothing but
 * `CancellationException`. [PasswordAccount] never passes a blank email or an empty password: Firebase throws on those.
 */
interface PasswordAuthentication {
    /** Creates a password account and signs it in, its email not verified yet (AUTH-05). */
    suspend fun createUser(
        email: String,
        password: String,
    ): PasswordAnswer

    /** Signs in with an email and its password (AUTH-07). */
    suspend fun signIn(
        email: String,
        password: String,
    ): PasswordAnswer

    /** Firebase writes its next email in the app's language (`useAppLanguage`, OQ-29). */
    fun useAppLanguage()

    /** Sends the verification email to the signed-in user (AUTH-06); [PasswordAnswer.NotSignedIn] when nobody is. */
    suspend fun sendEmailVerification(): PasswordAnswer

    /** Sends a password reset email (AUTH-08) if the email has an account; enumeration protection hides which. */
    suspend fun sendPasswordReset(email: String): PasswordAnswer

    /**
     * Asks the server whether the signed-in user's email is verified now (AUTH-06): [PasswordAnswer.Done] once it is,
     * with the ID token renewed so the rules (`email_verified`) and the start gate see it at once;
     * [PasswordAnswer.NotVerified] while it is not; [PasswordAnswer.NotSignedIn] when nobody is signed in.
     */
    suspend fun reloadEmailVerified(): PasswordAnswer
}

/**
 * What Firebase answered, as far as the app tells answers apart; M1-99 maps Firebase's exceptions to it. [EmailInUse]:
 * sign-up for an email that has an account (`EMAIL_EXISTS`, which enumeration protection does not hide).
 * [WeakPassword]: the project's password policy refused the password (M1.md R1). [Refused]: a refused sign-in (a wrong
 * password or an email with no password account, one `INVALID_LOGIN_CREDENTIALS` under enumeration protection, or a
 * disabled account), and for a reset without enumeration protection an unknown email. [NoConnection]: the request did
 * not reach Firebase. [Failed]: anything else.
 */
enum class PasswordAnswer {
    Done,
    NotSignedIn,
    NotVerified,
    EmailInUse,
    InvalidEmail,
    WeakPassword,
    Refused,
    TooManyAttempts,
    NoConnection,
    Failed,
}
