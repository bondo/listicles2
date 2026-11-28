package dk.bjarkebjarke.tally.session

import android.content.Context
import android.os.SystemClock
import androidx.credentials.CredentialManager
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.android.qualifiers.ApplicationContext
import dagger.hilt.components.SingletonComponent
import dk.bjarkebjarke.tally.ApplicationScope
import dk.bjarkebjarke.tally.data.session.CredentialManagerGoogleCredentials
import dk.bjarkebjarke.tally.data.session.FirebaseAuthentication
import dk.bjarkebjarke.tally.data.session.FirebasePasswordAuthentication
import dk.bjarkebjarke.tally.data.session.FirestoreSession
import dk.bjarkebjarke.tally.domain.account.AccountProfiles
import dk.bjarkebjarke.tally.domain.connectivity.Connectivity
import dk.bjarkebjarke.tally.domain.session.Authentication
import dk.bjarkebjarke.tally.domain.session.GoogleCredentials
import dk.bjarkebjarke.tally.domain.session.GoogleSignIn
import dk.bjarkebjarke.tally.domain.session.LocalUserData
import dk.bjarkebjarke.tally.domain.session.PasswordAccount
import dk.bjarkebjarke.tally.domain.session.PasswordAuthentication
import dk.bjarkebjarke.tally.domain.session.SessionState
import dk.bjarkebjarke.tally.domain.session.SignOut
import dk.bjarkebjarke.tally.domain.session.SignedOutCleanup
import kotlinx.coroutines.CoroutineScope
import javax.inject.Singleton

/**
 * The session (AUTH-02) and what Google sign-in (AUTH-01) and sign-out (AUTH-03) are built from: Firebase Auth,
 * Firestore and Credential Manager from `:core:data` (M1-88), in place of the M1-60 stand-in. One
 * [FirebaseAuthentication] is both the session state the start routes on and the sign-in; one [FirestoreSession] is
 * both the copy sign-out deletes and every repository's Firestore, so its no-argument constructor holds the app's only
 * `FirebaseFirestore.getInstance` (M1-67). Firebase is first called when the first of them is injected, after
 * TallyApplication installed App Check (M1-26). A test replaces this module with fakes and keeps
 * [SignInAndSignOutModule].
 */
@Module
@InstallIn(SingletonComponent::class)
object SessionModule {
    @Provides
    @Singleton
    fun firebaseAuthentication(): FirebaseAuthentication = FirebaseAuthentication()

    @Provides
    fun sessionState(authentication: FirebaseAuthentication): SessionState = authentication

    /** The Account screen's profile (M1-25). */
    @Provides
    fun accountProfiles(authentication: FirebaseAuthentication): AccountProfiles = authentication

    @Provides
    fun authentication(authentication: FirebaseAuthentication): Authentication = authentication

    /** Email and password (M1-121), on the same default Firebase app's Auth. */
    @Provides
    @Singleton
    fun passwordAuthentication(): PasswordAuthentication = FirebasePasswordAuthentication()

    @Provides
    @Singleton
    fun firestoreSession(): FirestoreSession = FirestoreSession()

    @Provides
    fun localUserData(session: FirestoreSession): LocalUserData = session

    /** The account picker opens in MainActivity while it is started ([StartedActivity]). */
    @Provides
    @Singleton
    fun googleCredentials(
        @ApplicationContext context: Context,
        started: StartedActivity,
    ): GoogleCredentials =
        CredentialManagerGoogleCredentials(
            CredentialManager.create(context),
            started,
            CredentialManagerGoogleCredentials.webClientId(context),
        )
}

/**
 * Google sign-in, sign-out, the signed-out cleanup and the password account over the graph's session bindings:
 * [SessionModule]'s, or a test's fakes.
 */
@Module
@InstallIn(SingletonComponent::class)
object SignInAndSignOutModule {
    /**
     * One for the app, on the phone's monotonic clock (not the wall clock, which the user can set): its Send again
     * limits span the sign-up and the "check your email" screens (M1-15).
     */
    @Provides
    @Singleton
    fun passwordAccount(
        connectivity: Connectivity,
        authentication: PasswordAuthentication,
    ): PasswordAccount = PasswordAccount(connectivity, authentication, SystemClock::elapsedRealtime)

    @Provides
    fun googleSignIn(
        connectivity: Connectivity,
        credentials: GoogleCredentials,
        authentication: Authentication,
    ): GoogleSignIn = GoogleSignIn(connectivity, credentials, authentication)

    /** Steps 2 to 5 run in the application scope: signing out ends the screen that asked (M1-14). */
    @Provides
    fun signOut(
        connectivity: Connectivity,
        userData: LocalUserData,
        authentication: Authentication,
        credentials: GoogleCredentials,
        @ApplicationScope scope: CoroutineScope,
    ): SignOut = SignOut(connectivity, userData, authentication, credentials, scope)

    /**
     * One per process, in the application scope: MainActivity starts it once its start-up root is ready (after the
     * update gate's read), and only the first start watches (M1-89). Whatever comes to use Firestore without
     * MainActivity (a worker, say) starts it too.
     */
    @Provides
    @Singleton
    fun signedOutCleanup(
        session: SessionState,
        userData: LocalUserData,
        @ApplicationScope scope: CoroutineScope,
    ): SignedOutCleanup = SignedOutCleanup(session, userData, scope)
}
