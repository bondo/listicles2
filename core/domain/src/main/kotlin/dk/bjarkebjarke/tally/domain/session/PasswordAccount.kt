package dk.bjarkebjarke.tally.domain.session

import dk.bjarkebjarke.tally.domain.connectivity.Connectivity

/** Email and password sign-in (AUTH-05..08, AUTH-10). Naive first draft so the tests compile and fail. */
class PasswordAccount(
    private val connectivity: Connectivity,
    private val authentication: PasswordAuthentication,
) {
    suspend fun createAccount(
        email: String,
        password: String,
    ): CreateAccountResult =
        if (authentication.createUser(email, password) == PasswordAnswer.Done) {
            CreateAccountResult.CheckYourEmail
        } else {
            CreateAccountResult.Failed.also { connectivity.isOnline() }
        }

    suspend fun signIn(
        email: String,
        password: String,
    ): PasswordSignInResult =
        if (authentication.signIn(email, password) == PasswordAnswer.Done) {
            PasswordSignInResult.SignedIn
        } else {
            PasswordSignInResult.WrongEmailOrPassword
        }

    suspend fun resetPassword(email: String): PasswordResetResult =
        if (authentication.sendPasswordReset(email) == PasswordAnswer.Done) {
            PasswordResetResult.SentIfAccountExists
        } else {
            PasswordResetResult.Failed
        }

    suspend fun sendVerificationAgain(): VerificationResult =
        if (authentication.sendEmailVerification() == PasswordAnswer.Done) {
            VerificationResult.Sent
        } else {
            VerificationResult.Failed
        }

    suspend fun checkVerified(): VerificationResult =
        if (authentication.reloadEmailVerified() == PasswordAnswer.Done) {
            VerificationResult.Verified
        } else {
            VerificationResult.NotVerifiedYet
        }
}

/** How "Create account" ended (AUTH-05). */
enum class CreateAccountResult {
    /** The "check your email" screen (AUTH-06): the same for a new account and for an email that has one (AUTH-10). */
    CheckYourEmail,

    /** The email field's error: not a valid address. */
    InvalidEmail,

    /** The password field's error: fewer than 12 characters (OQ-26). */
    PasswordTooShort,

    /** "Too many attempts, try again later". */
    TooManyAttempts,

    /** "This needs a connection" (SYNC-03). */
    NeedsConnection,

    /** Anything else: no account was created, and the user can try again. */
    Failed,
}

/** How a password sign-in ended (AUTH-07). */
enum class PasswordSignInResult {
    /** Signed in: the start gates open the lists, or the verify screen while the email is not verified (P10). */
    SignedIn,

    /** "Wrong email or password": one message for every refused sign-in (OQ-34(c), AUTH-10). */
    WrongEmailOrPassword,

    /** "Too many attempts, try again later". */
    TooManyAttempts,

    /** The first sign-in needs a connection (AUTH-07, SYNC-03). */
    NeedsConnection,
}

/** How "Reset password" ended (AUTH-08). */
enum class PasswordResetResult {
    /** "If an account exists for this email, we sent an email with a link", whether or not one exists (AUTH-10). */
    SentIfAccountExists,

    /** The email field's error: not a valid address. */
    InvalidEmail,

    /** "Too many attempts, try again later". */
    TooManyAttempts,

    /** "This needs a connection" (SYNC-03). */
    NeedsConnection,

    /** Anything else: no email was sent, and the user can try again. */
    Failed,
}

/** How "Continue" or "Send again" on the "check your email" screen ended (AUTH-06). */
enum class VerificationResult {
    /** "Continue": the email is verified, and the start gates move on (P10). */
    Verified,

    /** "Continue": "not verified yet"; the user stays on the screen. */
    NotVerifiedYet,

    /** "Send again": a new email is on its way. */
    Sent,

    /** "Try again later": Firebase takes no more emails or checks for now. */
    TryAgainLater,

    /** "This needs a connection" (SYNC-03). */
    NeedsConnection,

    /** Anything else; the user can try again. */
    Failed,
}
