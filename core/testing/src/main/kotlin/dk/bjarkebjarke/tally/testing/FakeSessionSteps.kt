package dk.bjarkebjarke.tally.testing

import dk.bjarkebjarke.tally.domain.session.Authentication
import dk.bjarkebjarke.tally.domain.session.GoogleCredentials
import dk.bjarkebjarke.tally.domain.session.GoogleIdToken
import dk.bjarkebjarke.tally.domain.session.GoogleSignInResult
import dk.bjarkebjarke.tally.domain.session.LocalUserData
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.awaitCancellation
import kotlinx.coroutines.delay

// Fakes of the M1-14 sign-in and sign-out steps. Each one appends its calls to `steps`; share one list between them to
// check the order of the steps across fakes.

/** A [GoogleCredentials] whose account picker answers [answer]. */
class FakeGoogleCredentials(
    var answer: GoogleIdToken = GoogleIdToken.Picked("fake-google-id-token"),
    val steps: MutableList<String> = mutableListOf(),
) : GoogleCredentials {
    override suspend fun idToken(): GoogleIdToken {
        steps += "idToken"
        return answer
    }

    override suspend fun clearCredentialState() {
        steps += "clearCredentialState"
    }
}

/** An [Authentication] that answers [googleResult] and records the ID tokens it got in [googleIdTokens]. */
class FakeAuthentication(
    var googleResult: GoogleSignInResult = GoogleSignInResult.SignedIn,
    val steps: MutableList<String> = mutableListOf(),
) : Authentication {
    val googleIdTokens = mutableListOf<String>()

    override suspend fun signInWithGoogle(idToken: String): GoogleSignInResult {
        steps += "signInWithGoogle"
        googleIdTokens += idToken
        return googleResult
    }

    override fun signOut() {
        steps += "signOut"
    }
}

/**
 * A [LocalUserData] whose server acknowledges the pending writes [acknowledgeAfterMs] after the wait starts (`null`:
 * never, as offline). Under `runTest` the delay is virtual time. [clearGate], when set, holds [clear] open.
 */
class FakeLocalUserData(
    var acknowledgeAfterMs: Long? = 0,
    var waitFails: Boolean = false,
    var unsentChangesSeen: Boolean = false,
    var clearFails: Boolean = false,
    val steps: MutableList<String> = mutableListOf(),
) : LocalUserData {
    var clearGate: CompletableDeferred<Unit>? = null

    override suspend fun awaitPendingWrites(): Boolean {
        steps += "awaitPendingWrites"
        delay(acknowledgeAfterMs ?: awaitCancellation())
        return !waitFails
    }

    override fun unsentChangesSeen(): Boolean = unsentChangesSeen

    override suspend fun clear(): Boolean {
        steps += "clear"
        clearGate?.await()
        steps += "cleared"
        return !clearFails
    }
}
