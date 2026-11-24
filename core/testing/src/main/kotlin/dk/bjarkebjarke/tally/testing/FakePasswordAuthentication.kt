package dk.bjarkebjarke.tally.testing

import dk.bjarkebjarke.tally.domain.session.PasswordAnswer
import dk.bjarkebjarke.tally.domain.session.PasswordAuthentication

/**
 * A [PasswordAuthentication] (M1-15) whose calls answer what the test set last; [answerEverything] sets them all. Each
 * call appends its name to [steps] (share one list with other fakes to check the order across them), and the emails
 * and passwords it got to [emails] and [passwords].
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

    fun answerEverything(answer: PasswordAnswer) {
        createUserAnswer = answer
        signInAnswer = answer
        verificationAnswer = answer
        resetAnswer = answer
        reloadAnswer = answer
    }

    override suspend fun createUser(
        email: String,
        password: String,
    ): PasswordAnswer {
        record("createUser", email, password)
        return createUserAnswer
    }

    override suspend fun signIn(
        email: String,
        password: String,
    ): PasswordAnswer {
        record("signIn", email, password)
        return signInAnswer
    }

    override fun useAppLanguage() {
        steps += "useAppLanguage"
    }

    override suspend fun sendEmailVerification(): PasswordAnswer {
        steps += "sendEmailVerification"
        return verificationAnswer
    }

    override suspend fun sendPasswordReset(email: String): PasswordAnswer {
        steps += "sendPasswordReset"
        emails += email
        return resetAnswer
    }

    override suspend fun reloadEmailVerified(): PasswordAnswer {
        steps += "reloadEmailVerified"
        return reloadAnswer
    }

    private fun record(
        step: String,
        email: String,
        password: String,
    ) {
        steps += step
        emails += email
        passwords += password
    }
}
