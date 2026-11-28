package dk.bjarkebjarke.tally.data.session

import androidx.test.ext.junit.runners.AndroidJUnit4
import com.google.firebase.FirebaseException
import com.google.firebase.FirebaseNetworkException
import com.google.firebase.FirebaseTooManyRequestsException
import com.google.firebase.auth.FirebaseAuthException
import com.google.firebase.auth.FirebaseAuthInvalidCredentialsException
import com.google.firebase.auth.FirebaseAuthInvalidUserException
import com.google.firebase.auth.FirebaseAuthUserCollisionException
import com.google.firebase.auth.FirebaseAuthWeakPasswordException
import dk.bjarkebjarke.tally.domain.session.PasswordAnswer
import org.junit.Assert.assertEquals
import org.junit.Test
import org.junit.runner.RunWith

/**
 * M1-121: Firebase's exceptions as answers, for the ones the Auth emulator does not raise (no connection, too many
 * attempts, the project's password policy). On the phone, not the JVM: the exceptions need Android to be made.
 */
@RunWith(AndroidJUnit4::class)
class PasswordAnswerTest {
    @Test
    fun eachFailureHasItsAnswer() {
        val answers =
            mapOf(
                FirebaseNetworkException("offline") to PasswordAnswer.NoConnection,
                FirebaseTooManyRequestsException("slow down") to PasswordAnswer.TooManyAttempts,
                FirebaseAuthUserCollisionException("ERROR_EMAIL_ALREADY_IN_USE", "taken") to PasswordAnswer.EmailInUse,
                FirebaseAuthWeakPasswordException("ERROR_WEAK_PASSWORD", "weak", "") to PasswordAnswer.WeakPassword,
                auth("ERROR_PASSWORD_DOES_NOT_MEET_REQUIREMENTS") to PasswordAnswer.WeakPassword,
                invalid("ERROR_INVALID_EMAIL") to PasswordAnswer.InvalidEmail,
                invalid("ERROR_INVALID_CREDENTIAL") to PasswordAnswer.Refused,
                invalid("ERROR_WRONG_PASSWORD") to PasswordAnswer.Refused,
                FirebaseAuthInvalidUserException("ERROR_USER_DISABLED", "disabled") to PasswordAnswer.Refused,
                auth("ERROR_OPERATION_NOT_ALLOWED") to PasswordAnswer.Failed,
                FirebaseException("internal") to PasswordAnswer.Failed,
            )

        for ((failure, answer) in answers) assertEquals(failure.toString(), answer, passwordAnswer(failure))
    }

    private fun invalid(code: String) = FirebaseAuthInvalidCredentialsException(code, "invalid")

    private fun auth(code: String) = FirebaseAuthException(code, "failed")
}
