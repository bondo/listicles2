package dk.bjarkebjarke.tally.data.session

import com.google.firebase.FirebaseException
import com.google.firebase.auth.FirebaseAuth
import com.google.firebase.auth.GoogleAuthProvider
import dk.bjarkebjarke.tally.domain.account.AccountProfile
import dk.bjarkebjarke.tally.domain.account.AccountProfiles
import dk.bjarkebjarke.tally.domain.session.Authentication
import dk.bjarkebjarke.tally.domain.session.GoogleSignInResult
import dk.bjarkebjarke.tally.domain.session.SessionState
import kotlinx.coroutines.channels.awaitClose
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.callbackFlow
import kotlinx.coroutines.flow.conflate
import kotlinx.coroutines.flow.distinctUntilChanged
import kotlinx.coroutines.tasks.await

/**
 * The session on this phone, from Firebase Authentication (M1-14). Firebase keeps the signed-in user on the phone, so
 * signed in stays signed in across restarts and offline (AUTH-02).
 */
class FirebaseAuthentication(
    private val auth: FirebaseAuth,
) : SessionState,
    Authentication,
    AccountProfiles {
    /** The app's session (M1-88): the default Firebase app's Auth. */
    constructor() : this(FirebaseAuth.getInstance())

    /** Firebase reports the state as soon as the flow is collected, then every sign-in and sign-out. */
    override fun signedIn(): Flow<Boolean> =
        callbackFlow {
            val listener = FirebaseAuth.AuthStateListener { trySend(it.currentUser != null) }
            auth.addAuthStateListener(listener)
            awaitClose { auth.removeAuthStateListener(listener) }
        }.conflate().distinctUntilChanged()

    override suspend fun signInWithGoogle(idToken: String): GoogleSignInResult {
        // Firebase's credential throws on an empty token, and Authentication throws nothing.
        if (idToken.isEmpty()) return GoogleSignInResult.Failed
        return try {
            auth.signInWithCredential(GoogleAuthProvider.getCredential(idToken, null)).await()
            GoogleSignInResult.SignedIn
        } catch (expected: FirebaseException) {
            // A refused token, no network, too many attempts or a disabled account. M1-128 tells the email collision
            // (AUTH-10) apart.
            GoogleSignInResult.Failed
        }
    }

    override fun signOut() = auth.signOut()

    override fun current(): AccountProfile =
        auth.currentUser.let { AccountProfile(name = it?.displayName?.ifBlank { null }, email = it?.email) }
}
