package dk.bjarkebjarke.tally.domain.session

import dk.bjarkebjarke.tally.domain.connectivity.Connectivity

/**
 * "Continue with Google" (AUTH-01): the system account picker through [GoogleCredentials], then Firebase sign-in with
 * the picked account's ID token. Offline the picker is not shown, because the first sign-in needs a connection; a
 * closed picker is no error.
 */
class GoogleSignIn(
    private val connectivity: Connectivity,
    private val credentials: GoogleCredentials,
    private val authentication: Authentication,
) {
    suspend operator fun invoke(): GoogleSignInResult {
        if (!connectivity.isOnline()) return GoogleSignInResult.NeedsConnection
        return when (val answer = credentials.idToken()) {
            is GoogleIdToken.Picked -> authentication.signInWithGoogle(answer.token)
            GoogleIdToken.Cancelled -> GoogleSignInResult.Cancelled
            GoogleIdToken.NoAccount -> GoogleSignInResult.NoAccount
            GoogleIdToken.Failed -> GoogleSignInResult.Failed
        }
    }
}

/**
 * How "Continue with Google" ended: one flat type, so the screen handles every outcome in one `when`. [NeedsConnection]
 * shows the SYNC-03 message of `ConnectionResult.NeedsConnection`.
 */
sealed interface GoogleSignInResult {
    /** Signed in: [SessionState] turns true and the root leaves sign-in. */
    data object SignedIn : GoogleSignInResult

    /** The user closed the account picker: stay on sign-in and show no error (AUTH-01). */
    data object Cancelled : GoogleSignInResult

    /** The phone has no Google account to pick. */
    data object NoAccount : GoogleSignInResult

    /** Offline: the first sign-in needs a connection (AUTH-01, SYNC-03); the picker is not shown. */
    data object NeedsConnection : GoogleSignInResult

    /**
     * The picked Google account's email has a password account, and Firebase trusts Google for it only for `@gmail.com`
     * (M1.md docs check 3, wireframe 44): nobody is signed in, and the screen says to use email and password.
     */
    data object EmailHasPasswordAccount : GoogleSignInResult

    /** The picker or Firebase failed. */
    data object Failed : GoogleSignInResult
}
