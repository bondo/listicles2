package dk.bjarkebjarke.tally

import android.os.SystemClock
import com.google.firebase.FirebaseApp
import dagger.hilt.android.testing.HiltAndroidRule
import dagger.hilt.android.testing.HiltAndroidTest
import dagger.hilt.android.testing.HiltTestApplication
import dagger.hilt.internal.GeneratedComponentManager
import dagger.hilt.internal.GeneratedComponentManagerHolder
import dk.bjarkebjarke.tally.connectivity.AndroidConnectivity
import dk.bjarkebjarke.tally.data.session.CredentialManagerGoogleCredentials
import dk.bjarkebjarke.tally.data.session.FirebaseAuthentication
import dk.bjarkebjarke.tally.data.session.FirebasePasswordAuthentication
import dk.bjarkebjarke.tally.data.session.FirestoreSession
import dk.bjarkebjarke.tally.domain.connectivity.Connectivity
import dk.bjarkebjarke.tally.domain.session.Authentication
import dk.bjarkebjarke.tally.domain.session.GoogleCredentials
import dk.bjarkebjarke.tally.domain.session.GoogleSignIn
import dk.bjarkebjarke.tally.domain.session.LocalUserData
import dk.bjarkebjarke.tally.domain.session.PasswordAccount
import dk.bjarkebjarke.tally.domain.session.PasswordAuthentication
import dk.bjarkebjarke.tally.domain.session.SessionState
import dk.bjarkebjarke.tally.domain.session.SignOut
import dk.bjarkebjarke.tally.domain.start.EmailVerification
import dk.bjarkebjarke.tally.domain.start.HouseholdNotices
import dk.bjarkebjarke.tally.domain.start.NameState
import dk.bjarkebjarke.tally.domain.start.UpdateGate
import dk.bjarkebjarke.tally.session.StartedActivity
import io.kotest.matchers.booleans.shouldBeTrue
import io.kotest.matchers.shouldBe
import io.kotest.matchers.types.shouldBeInstanceOf
import io.kotest.matchers.types.shouldBeSameInstanceAs
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.async
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.isActive
import kotlinx.coroutines.runBlocking
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config
import org.robolectric.shadows.ShadowSystemClock
import java.time.Duration
import javax.inject.Inject
import javax.inject.Provider

/** M1-30: the app is a Hilt app, its activity is an entry point, and the graph binds the app's own implementations. */
@HiltAndroidTest
@RunWith(RobolectricTestRunner::class)
@Config(application = HiltTestApplication::class)
class AppGraphTest {
    @get:Rule
    val hilt = HiltAndroidRule(this)

    @Inject
    lateinit var connectivity: Connectivity

    @Inject
    lateinit var session: SessionState

    @Inject
    lateinit var update: UpdateGate

    @Inject
    lateinit var email: EmailVerification

    @Inject
    lateinit var name: NameState

    @Inject
    lateinit var notices: HouseholdNotices

    @Inject
    lateinit var authentication: Authentication

    @Inject
    lateinit var passwordAuthentication: PasswordAuthentication

    @Inject
    lateinit var passwordAccounts: Provider<PasswordAccount>

    @Inject
    lateinit var userData: LocalUserData

    @Inject
    lateinit var firestoreSession: FirestoreSession

    @Inject
    lateinit var credentials: GoogleCredentials

    @Inject
    lateinit var googleSignIn: GoogleSignIn

    @Inject
    lateinit var signOut: SignOut

    @Inject
    lateinit var startedActivity: StartedActivity

    @Inject
    @ApplicationScope
    lateinit var scope: CoroutineScope

    /** TallyApplication initialises Firebase in the app; the Hilt test application does not. */
    @Before
    fun firebase() {
        FirebaseApp.initializeApp(RuntimeEnvironment.getApplication())
    }

    /** M1-62: until the gate tasks bind real sources, every gate passes (M1-27, M1-127, M1-39, M1-102). */
    @Test
    fun gateStandInsAllPass() {
        hilt.inject()
        runBlocking {
            update.updateRequired().first() shouldBe false
            email.verified().first() shouldBe true
            name.saved().first() shouldBe true
            notices.pending().first() shouldBe null
        }
    }

    /**
     * M1-121: the password calls are Firebase's, and the app has one [PasswordAccount] with the phone's monotonic
     * clock, so the Send again limits span the sign-up and the "check your email" screens.
     */
    @Test
    fun thePasswordCallsAreFirebasesWithOnePasswordAccount() {
        hilt.inject()
        passwordAuthentication.shouldBeInstanceOf<FirebasePasswordAuthentication>()
        val passwordAccount = passwordAccounts.get()
        passwordAccount shouldBeSameInstanceAs passwordAccounts.get()
        val clock =
            PasswordAccount::class.java
                .getDeclaredField("nowMs")
                .apply { isAccessible = true }
                .get(passwordAccount) as Function0<*>
        ShadowSystemClock.advanceBy(Duration.ofMinutes(1))
        clock() shouldBe SystemClock.elapsedRealtime()
    }

    @Test
    fun connectivityIsTheAndroidImplementation() {
        hilt.inject()
        connectivity.shouldBeInstanceOf<AndroidConnectivity>()
    }

    /**
     * M1-88: one Firebase Auth session is both the session state the start routes on and the sign-in, and one Firestore
     * holder is both the copy sign-out deletes and every repository's Firestore (M1-67). Separate instances would
     * route on a session the sign-in never changes, or delete a copy no repository writes to.
     */
    @Test
    fun oneFirebaseSessionIsTheStateTheSignInAndTheLocalCopy() {
        hilt.inject()
        session.shouldBeInstanceOf<FirebaseAuthentication>()
        authentication shouldBeSameInstanceAs session
        userData shouldBeSameInstanceAs firestoreSession
    }

    /** M1-88: the graph builds [googleSignIn] and [signOut] too; SignInAndSignOutWiringTest checks what they use. */
    @Test
    fun theCredentialsComeFromCredentialManager() {
        hilt.inject()
        credentials.shouldBeInstanceOf<CredentialManagerGoogleCredentials>()
    }

    /**
     * M1-88 (R1-02, S1-02): the picker opens in the activity MainActivity reports (SignedOutStartTest checks that part)
     * and asks for the configured web client. Another activity source or an empty id would answer Failed to every
     * Google sign-in.
     */
    @Test
    fun theCredentialsAskInTheStartedActivityForTheConfiguredWebClient() {
        hilt.inject()

        fun field(name: String) =
            CredentialManagerGoogleCredentials::class.java
                .getDeclaredField(name)
                .apply { isAccessible = true }
                .get(credentials)
        field("foreground") shouldBeSameInstanceAs startedActivity
        field("webClientId") shouldBe
            CredentialManagerGoogleCredentials.webClientId(RuntimeEnvironment.getApplication())
    }

    /**
     * Sign-out's steps 2 to 5 run in the application scope, with a SupervisorJob (checklist section 5): one failed
     * sign-out ends nothing, so the next one still runs.
     */
    @Test
    fun theApplicationScopeOutlivesAFailedChild() {
        hilt.inject()
        val failed = scope.async { error("a failed sign-out step") }
        runBlocking { failed.join() }
        scope.isActive shouldBe true
    }
}

/** Without the test application: the manifest's application and MainActivity are the app's own Hilt entry points. */
@RunWith(RobolectricTestRunner::class)
class TallyApplicationTest {
    @Test
    fun manifestApplicationAndMainActivityAreHiltEntryPoints() {
        val app = RuntimeEnvironment.getApplication()
        app.shouldBeInstanceOf<TallyApplication>()
        app.shouldBeInstanceOf<GeneratedComponentManager<*>>()
        GeneratedComponentManagerHolder::class.java.isAssignableFrom(MainActivity::class.java).shouldBeTrue()
    }
}
