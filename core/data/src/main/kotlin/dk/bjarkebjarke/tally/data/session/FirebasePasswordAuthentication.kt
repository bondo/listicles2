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
import dk.bjarkebjarke.tally.domain.start.EmailVerification
import kotlinx.coroutines.channels.awaitClose
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.callbackFlow
import kotlinx.coroutines.flow.conflate
import kotlinx.coroutines.flow.distinctUntilChanged
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.tasks.await

/**
 * Email and password over Firebase Authentication (M1-121, the calls of M1-15), and the email-verified start gate
 * (AUTH-06, M1-62), on the same Auth session as [FirebaseAuthentication].
 */
class FirebasePasswordAuthentication(
    private val auth: FirebaseAuth,
) : PasswordAuthentication,
    EmailVerification {
    /** The app's session: the default Firebase app's Auth. */
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

    /** Once verified, a new ID token at once: the rules' `email_verified` and [verified] see it now, not in an hour. */
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

    /**
     * The `email_verified` claim of the signed-in user's ID token, which the rules check, so the gate never opens
     * before they would allow the user's writes; false while nobody is signed in. Firebase calls the listener at every
     * sign-in, sign-out and new token. Offline with an expired token the claim cannot be read: then the email as last
     * read.
     */
    override fun verified(): Flow<Boolean> =
        callbackFlow {
            val listener = FirebaseAuth.IdTokenListener { trySend(Unit) }
            auth.addIdTokenListener(listener)
            awaitClose { auth.removeIdTokenListener(listener) }
        }.conflate().map { tokenVerified() }.distinctUntilChanged()

    private suspend fun tokenVerified(): Boolean {
        val user = auth.currentUser ?: return false
        return try {
            user.getIdToken(false).await().claims["email_verified"] == true
        } catch (expected: FirebaseException) {
            user.isEmailVerified
        }
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
 * Firebase's exception as a [PasswordAnswer]. Under enumeration protection a wrong password, an unknown email and an
 * email with only Google are one `ERROR_INVALID_CREDENTIAL` (`INVALID_LOGIN_CREDENTIALS`); without it, and for a
 * disabled account, Firebase names the user ([FirebaseAuthInvalidUserException]). Both are [PasswordAnswer.Refused].
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
