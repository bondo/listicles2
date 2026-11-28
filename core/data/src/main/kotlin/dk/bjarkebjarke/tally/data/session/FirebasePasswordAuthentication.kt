package dk.bjarkebjarke.tally.data.session

import com.google.firebase.FirebaseException
import com.google.firebase.auth.FirebaseAuth
import dk.bjarkebjarke.tally.domain.session.PasswordAnswer
import dk.bjarkebjarke.tally.domain.session.PasswordAuthentication
import dk.bjarkebjarke.tally.domain.start.EmailVerification
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flowOf

/** M1-121, test first: a naive draft that answers Failed to everything. */
class FirebasePasswordAuthentication(
    private val auth: FirebaseAuth,
) : PasswordAuthentication,
    EmailVerification {
    constructor() : this(FirebaseAuth.getInstance())

    override suspend fun createUser(
        email: String,
        password: String,
    ) = PasswordAnswer.Failed

    override suspend fun signIn(
        email: String,
        password: String,
    ) = PasswordAnswer.Failed

    override fun useAppLanguage() = auth.useAppLanguage()

    override suspend fun sendEmailVerification() = PasswordAnswer.Failed

    override suspend fun sendPasswordReset(email: String) = PasswordAnswer.Failed

    override suspend fun reloadEmailVerified() = PasswordAnswer.Failed

    override fun verified(): Flow<Boolean> = flowOf(false)
}

internal fun passwordAnswer(failure: FirebaseException): PasswordAnswer = failure.let { PasswordAnswer.Failed }
