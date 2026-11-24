package dk.bjarkebjarke.tally.session

import dagger.hilt.android.testing.BindValue
import dagger.hilt.android.testing.HiltAndroidRule
import dagger.hilt.android.testing.HiltAndroidTest
import dagger.hilt.android.testing.HiltTestApplication
import dagger.hilt.android.testing.UninstallModules
import dk.bjarkebjarke.tally.ApplicationScope
import dk.bjarkebjarke.tally.connectivity.ConnectivityModule
import dk.bjarkebjarke.tally.data.session.FirestoreSession
import dk.bjarkebjarke.tally.domain.connectivity.Connectivity
import dk.bjarkebjarke.tally.domain.session.Authentication
import dk.bjarkebjarke.tally.domain.session.GoogleCredentials
import dk.bjarkebjarke.tally.domain.session.GoogleIdToken
import dk.bjarkebjarke.tally.domain.session.GoogleSignIn
import dk.bjarkebjarke.tally.domain.session.GoogleSignInResult
import dk.bjarkebjarke.tally.domain.session.LocalUserData
import dk.bjarkebjarke.tally.domain.session.SessionState
import dk.bjarkebjarke.tally.domain.session.SignOut
import dk.bjarkebjarke.tally.testing.FakeAuthentication
import dk.bjarkebjarke.tally.testing.FakeConnectivity
import dk.bjarkebjarke.tally.testing.FakeGoogleCredentials
import dk.bjarkebjarke.tally.testing.FakeLocalUserData
import dk.bjarkebjarke.tally.testing.FakeSessionState
import io.kotest.matchers.shouldBe
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.CoroutineStart
import kotlinx.coroutines.cancelAndJoin
import kotlinx.coroutines.job
import kotlinx.coroutines.launch
import kotlinx.coroutines.runBlocking
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import java.util.Collections
import javax.inject.Inject

/**
 * M1-88: Google sign-in and sign-out are built from the graph's bindings, here fakes in place of Firebase and
 * Credential Manager (SessionModule) and of the network check, and sign-out's steps 2 to 5 run in the application
 * scope.
 */
@HiltAndroidTest
@UninstallModules(SessionModule::class, ConnectivityModule::class)
@RunWith(RobolectricTestRunner::class)
@Config(application = HiltTestApplication::class)
class SignInAndSignOutWiringTest {
    @get:Rule
    val hilt = HiltAndroidRule(this)

    /** The fakes' calls in order. Sign-out's steps add theirs on a thread of the application scope. */
    private val steps: MutableList<String> = Collections.synchronizedList(mutableListOf())
    private val network = FakeConnectivity(online = true)
    private val firebase = FakeAuthentication(steps = steps)
    private val localCopy = FakeLocalUserData(steps = steps)

    @BindValue
    @JvmField
    val connectivity: Connectivity = network

    @BindValue
    @JvmField
    val credentials: GoogleCredentials = FakeGoogleCredentials(GoogleIdToken.Picked(TOKEN), steps)

    @BindValue
    @JvmField
    val authentication: Authentication = firebase

    @BindValue
    @JvmField
    val userData: LocalUserData = localCopy

    /** StartViewModel routes on it in every graph. */
    @BindValue
    @JvmField
    val session: SessionState = FakeSessionState(signedIn = false)

    /** The update gate's remote reads through it; no Firebase app here, so it fails and the gate fails open. */
    @BindValue
    @JvmField
    val firestoreSession: FirestoreSession = FirestoreSession()

    @Inject
    lateinit var googleSignIn: GoogleSignIn

    @Inject
    lateinit var signOut: SignOut

    @Inject
    @ApplicationScope
    lateinit var applicationScope: CoroutineScope

    /** The picked account's ID token signs in to the graph's Authentication; offline, the picker is not asked. */
    @Test
    fun googleSignInAsksTheGraphsPickerAndSignsInToItsAuthentication() {
        hilt.inject()

        runBlocking { googleSignIn() } shouldBe GoogleSignInResult.SignedIn
        firebase.googleIdTokens shouldBe listOf(TOKEN)
        network.online = false
        runBlocking { googleSignIn() } shouldBe GoogleSignInResult.NeedsConnection

        steps shouldBe listOf("idToken", "signInWithGoogle")
    }

    /**
     * Signing out ends the screen that asked (M1-14), so steps 2 to 5 run in the application scope: they finish after
     * their caller is cancelled, in order, on the graph's local copy, Authentication and credentials.
     */
    @Test
    fun signOutFinishesInTheApplicationScopeAfterItsCallerIsCancelled() {
        hilt.inject()
        val clearing = CompletableDeferred<Unit>()
        localCopy.clearGate = clearing

        runBlocking {
            val caller = launch(start = CoroutineStart.UNDISPATCHED) { signOut.discardingUnsentChanges() }
            val stepsTwoToFive =
                applicationScope.coroutineContext.job.children
                    .single()
            caller.cancelAndJoin()
            clearing.complete(Unit)
            stepsTwoToFive.join()
        }

        steps shouldBe listOf("clear", "cleared", "signOut", "clearCredentialState")
    }
}

private const val TOKEN = "picked-account-id-token"
