package dk.bjarkebjarke.tally.domain.session

/**
 * The phone's Credential Manager with the Google ID option (docs/milestones/M1.md, M1-14), wrapped so tests can fake
 * it. An implementation throws nothing but `CancellationException`: every failure is an answer.
 */
interface GoogleCredentials {
    /** Shows the system account picker and answers with the picked Google account's ID token (AUTH-01). */
    suspend fun idToken(): GoogleIdToken

    /** Clears the user's credential state in every credential provider, as Google asks at every sign-out. */
    suspend fun clearCredentialState()
}

/** The account picker's answer. */
sealed interface GoogleIdToken {
    data class Picked(
        val token: String,
    ) : GoogleIdToken {
        // An ID token signs in to Firebase: keep it out of logs and crash reports.
        override fun toString() = "Picked(token=***)"
    }

    /** The user closed the picker. */
    data object Cancelled : GoogleIdToken

    /** The phone has no Google account to offer. */
    data object NoAccount : GoogleIdToken

    /** Anything else: no credential provider, a provider error, a credential that is not a Google ID token. */
    data object Failed : GoogleIdToken
}

/** Firebase Authentication as sign-in and sign-out use it (M1-14). Throws nothing but `CancellationException`. */
interface Authentication {
    /** Signs in with a Google ID token: [GoogleSignInResult.SignedIn] or [GoogleSignInResult.Failed]. */
    suspend fun signInWithGoogle(idToken: String): GoogleSignInResult

    /** Ends the session on this phone; [SessionState] turns false. */
    fun signOut()
}
