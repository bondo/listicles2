package dk.bjarkebjarke.tally.data.session

import com.google.firebase.FirebaseException
import com.google.firebase.FirebaseNetworkException
import com.google.firebase.FirebaseTooManyRequestsException
import com.google.firebase.auth.FirebaseAuth
import com.google.firebase.auth.FirebaseAuthException
import com.google.firebase.auth.FirebaseAuthInvalidUserException
import com.google.firebase.auth.FirebaseAuthUserCollisionException
import dk.bjarkebjarke.tally.domain.session.PasswordAnswer
import dk.bjarkebjarke.tally.domain.session.PasswordAuthentication
import kotlinx.coroutines.tasks.await

/** Email and password over Firebase Authentication (M1-121: the calls of M1-15), on the session of the app's Auth. */
class FirebasePasswordAuthentication(
    private val auth: FirebaseAuth,
) : PasswordAuthentication {
    constructor() : this(FirebaseAuth.getInstance())

    override suspend fun createUser(
        email: String,
        password: String,
    ) = answer { auth.createUserWithEmailAndPassword(email, password).await() }

    override suspend fun signIn(
        email: String,
        password: String,
    ) = answer { auth.signInWithEmailAndPassword(email, password).await() }

    override fun useAppLanguage() = auth.useAppLanguage()

    override suspend fun sendEmailVerification(): PasswordAnswer {
        val user = auth.currentUser ?: return PasswordAnswer.NotSignedIn
        return answer { user.sendEmailVerification().await() }
    }

    override suspend fun sendPasswordReset(email: String) = answer { auth.sendPasswordResetEmail(email).await() }

    /** Once verified, a new ID token at once: the rules' `email_verified` and the M1-127 gate see it now, not later. */
    override suspend fun reloadEmailVerified(): PasswordAnswer {
        val user = auth.currentUser ?: return PasswordAnswer.NotSignedIn
        var verified = false
        val answer =
            answer {
                user.reload().await()
                verified = user.isEmailVerified
                if (verified) user.getIdToken(true).await()
            }
        return if (answer == PasswordAnswer.Done && !verified) PasswordAnswer.NotVerified else answer
    }

    private suspend fun answer(call: suspend () -> Unit): PasswordAnswer =
        try {
            call()
            PasswordAnswer.Done
        } catch (expected: FirebaseException) {
            passwordAnswer(expected)
        }
}

/**
 * Firebase's exception as a [PasswordAnswer]. Enumeration protection makes every refused sign-in one
 * `ERROR_INVALID_CREDENTIAL`; a disabled account (or, without it, an unknown email) names the user. Both are
 * [PasswordAnswer.Refused].
 */
internal fun passwordAnswer(failure: FirebaseException): PasswordAnswer =
    when (failure) {
        is FirebaseNetworkException -> {
            PasswordAnswer.NoConnection
        }

        is FirebaseTooManyRequestsException -> {
            PasswordAnswer.TooManyAttempts
        }

        is FirebaseAuthUserCollisionException -> {
            PasswordAnswer.EmailInUse
        }

        is FirebaseAuthInvalidUserException -> {
            PasswordAnswer.Refused
        }

        is FirebaseAuthException -> {
            when (failure.errorCode) {
                "ERROR_INVALID_EMAIL" -> PasswordAnswer.InvalidEmail

                // The second is the project's password policy (M1.md R1), which the emulator does not have.
                "ERROR_WEAK_PASSWORD", "ERROR_PASSWORD_DOES_NOT_MEET_REQUIREMENTS" -> PasswordAnswer.WeakPassword

                "ERROR_INVALID_CREDENTIAL", "ERROR_WRONG_PASSWORD" -> PasswordAnswer.Refused

                else -> PasswordAnswer.Failed
            }
        }

        else -> {
            PasswordAnswer.Failed
        }
    }
