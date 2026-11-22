package dk.bjarkebjarke.tally.domain.session

import dk.bjarkebjarke.tally.domain.connectivity.Connectivity

/** "Continue with Google" (AUTH-01). Naive first draft so the tests compile and fail; the real steps follow. */
class GoogleSignIn(
    private val connectivity: Connectivity,
    private val credentials: GoogleCredentials,
    private val authentication: Authentication,
) {
    suspend operator fun invoke(): GoogleSignInResult =
        (credentials.idToken() as? GoogleIdToken.Picked)?.let { authentication.signInWithGoogle(it.token) }
            ?: GoogleSignInResult.Failed.also { connectivity.isOnline() }
}

/** How "Continue with Google" ended. */
sealed interface GoogleSignInResult {
    /** Signed in: [SessionState] turns true and the root leaves sign-in. */
    data object SignedIn : GoogleSignInResult

    /** The user closed the account picker: stay on sign-in and show no error (AUTH-01). */
    data object Cancelled : GoogleSignInResult

    /** The phone has no Google account to pick. */
    data object NoAccount : GoogleSignInResult

    /** Offline: the first sign-in needs a connection (AUTH-01, SYNC-03); the picker is not shown. */
    data object NeedsConnection : GoogleSignInResult

    /** The picker or Firebase failed. */
    data object Failed : GoogleSignInResult
}
