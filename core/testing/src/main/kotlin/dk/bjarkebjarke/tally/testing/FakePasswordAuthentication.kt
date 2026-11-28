package dk.bjarkebjarke.tally.testing

import dk.bjarkebjarke.tally.domain.session.PasswordAnswer
import dk.bjarkebjarke.tally.domain.session.PasswordAuthentication

/**
 * A [PasswordAuthentication] (M1-15) whose calls answer what the test set last. Each call appends its name to [steps]
 * (share one list to check the order across fakes), and its email and password to [emails] and [passwords].
 */
class FakePasswordAuthentication(
    var createUserAnswer: PasswordAnswer = PasswordAnswer.Done,
    var signInAnswer: PasswordAnswer = PasswordAnswer.Done,
    var verificationAnswer: PasswordAnswer = PasswordAnswer.Done,
    var resetAnswer: PasswordAnswer = PasswordAnswer.Done,
    var reloadAnswer: PasswordAnswer = PasswordAnswer.Done,
    val steps: MutableList<String> = mutableListOf(),
) : PasswordAuthentication {
    val emails = mutableListOf<String>()
    val passwords = mutableListOf<String>()

    override suspend fun createUser(
        email: String,
        password: String,
    ) = call("createUser", createUserAnswer, email, password)

    override suspend fun signIn(
        email: String,
        password: String,
    ) = call("signIn", signInAnswer, email, password)

    override fun useAppLanguage() {
        steps += "useAppLanguage"
    }

    override suspend fun sendEmailVerification() = call("sendEmailVerification", verificationAnswer)

    override suspend fun sendPasswordReset(email: String) = call("sendPasswordReset", resetAnswer, email)

    override suspend fun reloadEmailVerified() = call("reloadEmailVerified", reloadAnswer)

    private fun call(
        step: String,
        answer: PasswordAnswer,
        email: String? = null,
        password: String? = null,
    ): PasswordAnswer {
        steps += step
        email?.let { emails += it }
        password?.let { passwords += it }
        return answer
    }
}
