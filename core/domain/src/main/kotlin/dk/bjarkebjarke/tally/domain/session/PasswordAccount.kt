package dk.bjarkebjarke.tally.domain.session

import dk.bjarkebjarke.tally.domain.Validation
import dk.bjarkebjarke.tally.domain.connectivity.Connectivity

/**
 * Email and password sign-in (AUTH-05..08; docs/milestones/M1.md, M1-15) over [PasswordAuthentication]. No answer tells
 * whether an email has an account or which method it uses (AUTH-10, email enumeration protection): sign-up for an
 * email that has one ends like a new account, every refused sign-in is one answer, and so is every reset. Each action
 * checks its input first, then the connection (SYNC-03), then asks Firebase. Every email goes out in the app's
 * language, set right before it, because the user can change the language in between (OQ-29).
 */
class PasswordAccount(
    private val connectivity: Connectivity,
    private val authentication: PasswordAuthentication,
) {
    /**
     * "Create account" (AUTH-05), for the email and password fields; M1-17 saves the name. A new account is signed in,
     * not verified, and gets the verification email. An email that already has an account, by either method, ends the
     * same, with no account, no email and nobody signed in (AUTH-10, R3-01): only a new account leaves a session.
     */
    suspend fun createAccount(
        email: String,
        password: String,
    ): CreateAccountResult =
        when {
            Validation.email(email) != null -> CreateAccountResult.InvalidEmail
            Validation.password(password) != null -> CreateAccountResult.PasswordTooShort
            !connectivity.isOnline() -> CreateAccountResult.NeedsConnection
            else -> created(authentication.createUser(Validation.normalizedEmail(email), password))
        }

    /**
     * "Sign in" with an email and password (AUTH-07). Every refusal is [PasswordSignInResult.WrongEmailOrPassword]: a
     * wrong password, an email with no account or only a Google account, a disabled account, an empty field, and any
     * other failure (OQ-34(c)).
     */
    suspend fun signIn(
        email: String,
        password: String,
    ): PasswordSignInResult {
        val address = Validation.normalizedEmail(email)
        return when {
            address.isEmpty() || password.isEmpty() -> PasswordSignInResult.WrongEmailOrPassword
            !connectivity.isOnline() -> PasswordSignInResult.NeedsConnection
            else -> signedIn(authentication.signIn(address, password))
        }
    }

    /**
     * "Reset password" (AUTH-08): one answer whether or not the email has an account, and whatever method it uses
     * (AUTH-10). For an email with only a Google account the reset may add a password to that same account (OQ-34(b),
     * decided; M1-95 records what Firebase does).
     */
    suspend fun resetPassword(email: String): PasswordResetResult {
        val address = Validation.normalizedEmail(email)
        return when {
            address.isEmpty() -> PasswordResetResult.InvalidEmail
            !connectivity.isOnline() -> PasswordResetResult.NeedsConnection
            else -> resetSent(inAppLanguage { authentication.sendPasswordReset(address) })
        }
    }

    /**
     * "Send again" on the "check your email" screen (AUTH-06). With nobody signed in, as after sign-up for an email
     * that had an account, nothing is sent and the answer is the same (AUTH-10).
     */
    suspend fun sendVerificationAgain(): VerificationResult =
        when {
            !connectivity.isOnline() -> VerificationResult.NeedsConnection
            else -> verificationSent(inAppLanguage { authentication.sendEmailVerification() })
        }

    /**
     * "Continue" on the "check your email" screen (AUTH-06): [VerificationResult.Verified] once the link was opened;
     * "not verified yet" before, and also with nobody signed in (AUTH-10).
     */
    suspend fun checkVerified(): VerificationResult =
        when {
            !connectivity.isOnline() -> VerificationResult.NeedsConnection
            else -> verified(authentication.reloadEmailVerified())
        }

    private suspend fun created(answer: PasswordAnswer): CreateAccountResult {
        // Whatever this answers, the user checks their email: the verify screen has "Send again" (AUTH-06).
        if (answer == PasswordAnswer.Done) inAppLanguage { authentication.sendEmailVerification() }
        return when (answer) {
            PasswordAnswer.Done, PasswordAnswer.EmailInUse -> CreateAccountResult.CheckYourEmail
            PasswordAnswer.InvalidEmail -> CreateAccountResult.InvalidEmail
            PasswordAnswer.WeakPassword -> CreateAccountResult.PasswordTooShort
            PasswordAnswer.TooManyAttempts -> CreateAccountResult.TooManyAttempts
            PasswordAnswer.NoConnection -> CreateAccountResult.NeedsConnection
            else -> CreateAccountResult.Failed
        }
    }

    private suspend fun inAppLanguage(send: suspend () -> PasswordAnswer): PasswordAnswer {
        authentication.useAppLanguage()
        return send()
    }
}

// Firebase's answer as the screens show it; none tells whether the email has an account (AUTH-10).

private fun signedIn(answer: PasswordAnswer): PasswordSignInResult =
    when (answer) {
        PasswordAnswer.Done -> PasswordSignInResult.SignedIn
        PasswordAnswer.TooManyAttempts -> PasswordSignInResult.TooManyAttempts
        PasswordAnswer.NoConnection -> PasswordSignInResult.NeedsConnection
        else -> PasswordSignInResult.WrongEmailOrPassword
    }

private fun resetSent(answer: PasswordAnswer): PasswordResetResult =
    when (answer) {
        PasswordAnswer.Done, PasswordAnswer.Refused -> PasswordResetResult.SentIfAccountExists
        PasswordAnswer.InvalidEmail -> PasswordResetResult.InvalidEmail
        PasswordAnswer.TooManyAttempts -> PasswordResetResult.TooManyAttempts
        PasswordAnswer.NoConnection -> PasswordResetResult.NeedsConnection
        else -> PasswordResetResult.Failed
    }

private fun verificationSent(answer: PasswordAnswer): VerificationResult =
    when (answer) {
        PasswordAnswer.Done, PasswordAnswer.NotSignedIn -> VerificationResult.Sent
        PasswordAnswer.TooManyAttempts -> VerificationResult.TryAgainLater
        PasswordAnswer.NoConnection -> VerificationResult.NeedsConnection
        else -> VerificationResult.Failed
    }

private fun verified(answer: PasswordAnswer): VerificationResult =
    when (answer) {
        PasswordAnswer.Done -> VerificationResult.Verified
        PasswordAnswer.NotVerified, PasswordAnswer.NotSignedIn -> VerificationResult.NotVerifiedYet
        PasswordAnswer.TooManyAttempts -> VerificationResult.TryAgainLater
        PasswordAnswer.NoConnection -> VerificationResult.NeedsConnection
        else -> VerificationResult.Failed
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
