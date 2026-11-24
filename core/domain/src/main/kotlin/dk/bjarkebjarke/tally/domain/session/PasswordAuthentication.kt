package dk.bjarkebjarke.tally.domain.session

/**
 * Firebase Authentication's email and password calls (docs/milestones/M1.md, M1-15), as [PasswordAccount] uses them;
 * M1-95 implements them over Firebase. An implementation throws nothing but `CancellationException`. [PasswordAccount]
 * never passes a blank email or an empty password: Firebase throws on those.
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

    /** Sends a password reset email (AUTH-08) when the email has an account; enumeration protection hides which. */
    suspend fun sendPasswordReset(email: String): PasswordAnswer

    /**
     * Asks the server whether the signed-in user's email is verified now (AUTH-06): [PasswordAnswer.Done] once it is,
     * with the user's ID token renewed so the rules (`email_verified`) and the start gate see it at once;
     * [PasswordAnswer.NotVerified] while it is not; [PasswordAnswer.NotSignedIn] when nobody is signed in.
     */
    suspend fun reloadEmailVerified(): PasswordAnswer
}

/** What Firebase answered, as far as the app tells answers apart. M1-95 maps Firebase's exceptions to it. */
enum class PasswordAnswer {
    Done,

    /** Nobody is signed in on this phone. */
    NotSignedIn,

    /** The signed-in user's email is not verified yet. */
    NotVerified,

    /** Sign-up for an email that already has an account: `EMAIL_EXISTS`, which enumeration protection does not hide. */
    EmailInUse,

    /** Not a valid email address. */
    InvalidEmail,

    /** The project's password policy refused the password (Require mode, 12 or more characters, M1.md R1). */
    WeakPassword,

    /**
     * A refused sign-in: a wrong password or an email with no password account (one `INVALID_LOGIN_CREDENTIALS` under
     * enumeration protection), or a disabled account; for a reset without enumeration protection, an unknown email.
     */
    Refused,

    /** Firebase blocks requests from this phone or account for a while. */
    TooManyAttempts,

    /** The request did not reach Firebase. */
    NoConnection,

    /** Anything else. */
    Failed,
}
