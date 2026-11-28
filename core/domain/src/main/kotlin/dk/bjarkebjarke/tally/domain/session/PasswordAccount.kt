package dk.bjarkebjarke.tally.domain.session

import dk.bjarkebjarke.tally.domain.Validation
import dk.bjarkebjarke.tally.domain.connectivity.Connectivity

/**
 * Email and password sign-in (AUTH-05..08; M1.md, M1-15). No answer tells whether an email has an account or by which
 * method (AUTH-10). Each action checks its input, then the connection (SYNC-03), then asks Firebase; every email goes
 * out in the app's language, set right before it, as the user can change it in between (OQ-29).
 *
 * Send again is "Try again later", without asking Firebase, within [RESEND_COOLDOWN_MS] of the last email and after
 * [MAX_EMAILS_PER_WINDOW] in [EMAIL_WINDOW_MS], the sign-up's email included (AUTH-06). The sign-up counts for an email
 * that had an account too, which got none, so both get the same answers (AUTH-10, R1-01). Firebase states no per-user
 * limit (docs/auth/limits: per project only), so the app keeps its own, meant to be stricter. [nowMs] is a monotonic
 * clock in milliseconds; the count lives in this instance, so the app keeps one for both screens (M1-121: a singleton).
 */
class PasswordAccount(
    private val connectivity: Connectivity,
    private val authentication: PasswordAuthentication,
    private val nowMs: () -> Long,
) {
    /** When the sign-up's email and each Send again went out (or, with nobody signed in, would have), oldest first. */
    private val emails = ArrayDeque<Long>()

    /**
     * "Create account" (AUTH-05): a new account is signed in, not verified, runs [saveName] (the name, M1-17 and M1-39)
     * and gets the verification email. An email that has an account ends the same with no name saved, no email and
     * nobody signed in (R3-01): only a new account has somewhere to save the name (R1-02).
     */
    suspend fun createAccount(
        email: String,
        password: String,
        saveName: suspend () -> Unit,
    ): SignUpResult =
        when {
            Validation.email(email) != null -> SignUpResult.InvalidEmail
            Validation.password(password) != null -> SignUpResult.PasswordTooShort
            !connectivity.isOnline() -> SignUpResult.NeedsConnection
            else -> created(authentication.createUser(Validation.normalizedEmail(email), password), saveName)
        }

    /** "Sign in" (AUTH-07): one answer for every failed sign-in, whatever went wrong (OQ-34(c)). */
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

    /** "Reset password" (AUTH-08): one answer whether or not the email has an account (AUTH-10, OQ-34(b)). */
    suspend fun resetPassword(email: String): PasswordResetResult {
        val address = Validation.normalizedEmail(email)
        return when {
            address.isEmpty() -> PasswordResetResult.InvalidEmail
            !connectivity.isOnline() -> PasswordResetResult.NeedsConnection
            else -> resetSent(inAppLanguage { authentication.sendPasswordReset(address) })
        }
    }

    /**
     * "Send again" (AUTH-06), within the limits above; offline it asks nothing and uses none of them. With nobody
     * signed in nothing is sent, and the answer is the same (AUTH-10).
     */
    suspend fun sendVerificationAgain(): VerificationResult =
        when {
            !connectivity.isOnline() -> VerificationResult.NeedsConnection
            else -> sentAgain(nowMs())
        }

    /** "Continue" (AUTH-06): verified once the link was opened; with nobody signed in, not yet (AUTH-10). */
    suspend fun checkVerified(): VerificationResult =
        when {
            !connectivity.isOnline() -> VerificationResult.NeedsConnection
            else -> verified(authentication.reloadEmailVerified())
        }

    private suspend fun created(
        answer: PasswordAnswer,
        saveName: suspend () -> Unit,
    ): SignUpResult {
        if (answer == PasswordAnswer.Done) {
            saveName()
            // Whatever this answers, the user checks their email: the verify screen has "Send again" (AUTH-06).
            inAppLanguage { authentication.sendEmailVerification() }
        }
        val result =
            when (answer) {
                PasswordAnswer.Done, PasswordAnswer.EmailInUse -> SignUpResult.CheckYourEmail
                PasswordAnswer.InvalidEmail -> SignUpResult.InvalidEmail
                PasswordAnswer.WeakPassword -> SignUpResult.PasswordTooShort
                PasswordAnswer.TooManyAttempts -> SignUpResult.TooManyAttempts
                PasswordAnswer.NoConnection -> SignUpResult.NeedsConnection
                else -> SignUpResult.Failed
            }
        if (result == SignUpResult.CheckYourEmail) synchronized(emails) { emails.addLast(nowMs()) }
        return result
    }

    /** Counts one more email at [now] and answers true, or answers false when that would break the limits. */
    private fun tookEmail(now: Long): Boolean =
        synchronized(emails) {
            while (emails.isNotEmpty() && emails.first() <= now - EMAIL_WINDOW_MS) emails.removeFirst()
            val spaced = emails.lastOrNull()?.let { now - it >= RESEND_COOLDOWN_MS } ?: true
            val free = spaced && emails.size < MAX_EMAILS_PER_WINDOW
            if (free) emails.addLast(now)
            free
        }

    /** Within the limits, sends the email again; one that never went out uses none of them (R2-01). */
    private suspend fun sentAgain(now: Long): VerificationResult {
        if (!tookEmail(now)) return VerificationResult.TryAgainLater
        val result = verificationSent(inAppLanguage { authentication.sendEmailVerification() })
        if (result == VerificationResult.NeedsConnection || result == VerificationResult.Failed) {
            synchronized(emails) { emails.remove(now) }
        }
        return result
    }

    private suspend fun inAppLanguage(send: suspend () -> PasswordAnswer): PasswordAnswer {
        authentication.useAppLanguage()
        return send()
    }

    /** The limits of Send again (see the class). */
    companion object {
        const val RESEND_COOLDOWN_MS = 60_000L
        const val MAX_EMAILS_PER_WINDOW = 5
        const val EMAIL_WINDOW_MS = 3_600_000L
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

/**
 * How "Create account" ended (AUTH-05). [CheckYourEmail]: the "check your email" screen (AUTH-06), the same for a new
 * account and for an email that has one (AUTH-10). [InvalidEmail] and [PasswordTooShort] (under 12 characters, OQ-26)
 * are field errors. [Failed]: anything else; the user can try again.
 */
enum class SignUpResult { CheckYourEmail, InvalidEmail, PasswordTooShort, TooManyAttempts, NeedsConnection, Failed }

/**
 * How a password sign-in ended (AUTH-07). [SignedIn]: the start gates open the lists, or the verify screen while the
 * email is not verified (P10). [WrongEmailOrPassword]: one message for every refused sign-in (OQ-34(c), AUTH-10).
 */
enum class PasswordSignInResult { SignedIn, WrongEmailOrPassword, TooManyAttempts, NeedsConnection }

/**
 * How "Reset password" ended (AUTH-08). [SentIfAccountExists]: "If an account exists for this email, we sent an email
 * with a link", whether or not one exists (AUTH-10). [InvalidEmail] is a field error; [Failed]: anything else.
 */
enum class PasswordResetResult { SentIfAccountExists, InvalidEmail, TooManyAttempts, NeedsConnection, Failed }

/**
 * How "Continue" ([Verified], [NotVerifiedYet]) or "Send again" ([Sent]) on the "check your email" screen ended
 * (AUTH-06). [TryAgainLater]: Firebase takes no more emails or checks for now.
 */
enum class VerificationResult { Verified, NotVerifiedYet, Sent, TryAgainLater, NeedsConnection, Failed }
