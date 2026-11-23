package dk.bjarkebjarke.tally.data.session

import com.google.firebase.auth.FirebaseAuth
import dk.bjarkebjarke.tally.domain.session.Authentication
import dk.bjarkebjarke.tally.domain.session.GoogleSignInResult
import dk.bjarkebjarke.tally.domain.session.SessionState
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flowOf

/** Test-first draft (M1-67): signs nobody in and reports the state once; the next commit implements it. */
class FirebaseAuthentication(
    private val auth: FirebaseAuth,
) : SessionState,
    Authentication {
    override fun signedIn(): Flow<Boolean> = flowOf(auth.currentUser != null)

    override suspend fun signInWithGoogle(idToken: String): GoogleSignInResult = GoogleSignInResult.Failed

    override fun signOut() = auth.signOut()
}
