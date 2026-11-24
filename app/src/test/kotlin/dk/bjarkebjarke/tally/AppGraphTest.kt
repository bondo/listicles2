package dk.bjarkebjarke.tally

import com.google.firebase.FirebaseApp
import dagger.hilt.android.testing.HiltAndroidRule
import dagger.hilt.android.testing.HiltAndroidTest
import dagger.hilt.android.testing.HiltTestApplication
import dagger.hilt.internal.GeneratedComponentManager
import dagger.hilt.internal.GeneratedComponentManagerHolder
import dk.bjarkebjarke.tally.connectivity.AndroidConnectivity
import dk.bjarkebjarke.tally.data.session.CredentialManagerGoogleCredentials
import dk.bjarkebjarke.tally.data.session.FirebaseAuthentication
import dk.bjarkebjarke.tally.data.session.FirestoreSession
import dk.bjarkebjarke.tally.domain.connectivity.Connectivity
import dk.bjarkebjarke.tally.domain.session.Authentication
import dk.bjarkebjarke.tally.domain.session.GoogleCredentials
import dk.bjarkebjarke.tally.domain.session.GoogleSignIn
import dk.bjarkebjarke.tally.domain.session.LocalUserData
import dk.bjarkebjarke.tally.domain.session.SessionState
import dk.bjarkebjarke.tally.domain.session.SignOut
import dk.bjarkebjarke.tally.domain.start.EmailVerification
import dk.bjarkebjarke.tally.domain.start.HouseholdNotices
import dk.bjarkebjarke.tally.domain.start.NameState
import dk.bjarkebjarke.tally.domain.start.UpdateGate
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
import javax.inject.Inject

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
    @ApplicationScope
    lateinit var scope: CoroutineScope

    /** TallyApplication initialises Firebase in the app; the Hilt test application does not. */
    @Before
    fun firebase() {
        FirebaseApp.initializeApp(RuntimeEnvironment.getApplication())
    }

    /** M1-62: until the gate tasks bind real sources, every gate passes (M1-27, M1-15, M1-39, M1-18). */
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

    /**
     * M1-88: Google's credentials come from Credential Manager, and the app's graph builds [googleSignIn] and [signOut]
     * on these bindings. SignInAndSignOutWiringTest checks what the two are built from.
     */
    @Test
    fun theCredentialsComeFromCredentialManager() {
        hilt.inject()
        credentials.shouldBeInstanceOf<CredentialManagerGoogleCredentials>()
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
