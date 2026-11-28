package dk.bjarkebjarke.tally.data.session

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.google.firebase.FirebaseApp
import com.google.firebase.auth.FirebaseAuth
import com.google.firebase.auth.FirebaseAuthInvalidUserException
import com.google.firebase.auth.GoogleAuthProvider
import com.google.firebase.firestore.FirebaseFirestoreException
import com.google.firebase.firestore.Source
import dk.bjarkebjarke.tally.data.FirebaseEmulator
import dk.bjarkebjarke.tally.domain.account.AccountProfile
import dk.bjarkebjarke.tally.domain.session.GoogleCredentials
import dk.bjarkebjarke.tally.domain.session.GoogleIdToken
import dk.bjarkebjarke.tally.domain.session.GoogleSignInResult
import dk.bjarkebjarke.tally.domain.session.LocalUserData
import dk.bjarkebjarke.tally.domain.session.SignOut
import dk.bjarkebjarke.tally.domain.session.SignOutResult
import dk.bjarkebjarke.tally.domain.session.SignedOutCleanup
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.CoroutineStart
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.async
import kotlinx.coroutines.cancel
import kotlinx.coroutines.cancelAndJoin
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.tasks.await
import kotlinx.coroutines.withTimeout
import org.json.JSONObject
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNotSame
import org.junit.Assert.assertNull
import org.junit.Assert.assertSame
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import java.util.UUID

/**
 * M1-67 against the Auth and Firestore emulators (`ui` job): Google sign-in with a Google-style credential, the session
 * state, and the M1-14 sign-out (OQ-13) over the real Firestore cache and write queue; M1-89: the copy goes when
 * Firebase ends a session by itself. `runBlocking`, not `runTest`: the emulators answer in real time, and virtual time
 * would end the sign-out wait before they do.
 */
@RunWith(AndroidJUnit4::class)
class SessionEmulatorTest {
    private lateinit var app: FirebaseApp
    private lateinit var auth: FirebaseAuth
    private lateinit var authentication: FirebaseAuthentication
    private lateinit var userData: FirestoreSession
    private val credentials = FakeCredentialState()
    private val externalScope = CoroutineScope(SupervisorJob())
    private var rulesReplaced = false

    @Before
    fun setUp() {
        FirebaseEmulator.requireRunning()
        app = FirebaseEmulator.app(InstrumentationRegistry.getInstrumentation().targetContext)
        auth = FirebaseAuth.getInstance(app)
        auth.signOut() // Firebase restores a user an earlier run left signed in
        authentication = FirebaseAuthentication(auth)
        userData = FirestoreSession { FirebaseEmulator.firestore(app) }
        // The documents below are outside the project's rules: these tests are about the copy on the phone.
        rulesReplaced = true
        FirebaseEmulator.loadAllowAllRules()
    }

    @After
    fun tearDown() {
        externalScope.cancel()
        if (::app.isInitialized) {
            // Whatever a test left (or the code under test failed to clear): a new Firestore instance with the network
            // on and an empty cache, and no session.
            emulatorTest {
                val firestore = FirebaseEmulator.firestore(app)
                firestore.terminate().await()
                firestore.clearPersistence().await()
                auth.signOut()
            }
        }
        if (rulesReplaced) FirebaseEmulator.restoreProjectRules()
    }

    @Test
    fun aGoogleCredentialSignsInWithAVerifiedEmail() =
        emulatorTest {
            val email = "google-${UUID.randomUUID()}@example.com"

            assertEquals(GoogleSignInResult.SignedIn, authentication.signInWithGoogle(googleIdToken(email)))

            val user = checkNotNull(auth.currentUser)
            assertEquals(email, user.email)
            val token = user.getIdToken(false).await()
            assertEquals(GoogleAuthProvider.PROVIDER_ID, token.signInProvider)
            assertEquals(true, token.claims["email_verified"])
        }

    @Test
    fun aRefusedOrEmptyTokenSignsNobodyIn() =
        emulatorTest {
            assertEquals(GoogleSignInResult.Failed, authentication.signInWithGoogle("not-a-google-id-token"))
            // Firebase's credential throws on an empty token; Authentication throws nothing.
            assertEquals(GoogleSignInResult.Failed, authentication.signInWithGoogle(""))

            assertNull(auth.currentUser)
            assertFalse(authentication.signedIn().first())
        }

    @Test
    fun theSessionStateFollowsSignInAndSignOut() =
        emulatorTest {
            val states = Channel<Boolean>(Channel.UNLIMITED)
            val collecting = launch { authentication.signedIn().collect { states.send(it) } }

            assertFalse(states.receive())
            signIn(googleIdToken("state-${UUID.randomUUID()}@example.com"))
            assertTrue(states.receive())
            authentication.signOut()
            assertFalse(states.receive())
            collecting.cancel()
        }

    @Test
    fun signOutWithEverythingSentAsksNothingAndKeepsTheServerCopy() =
        emulatorTest {
            signIn(googleIdToken("sent-${UUID.randomUUID()}@example.com"))
            val path = "sign-out/${UUID.randomUUID()}"
            userData
                .firestore()
                .document(path)
                .set(mapOf("sent" to true))
                .await()
            assertTrue(cacheHas(path))

            assertEquals(SignOutResult.SignedOut, signOut()())

            assertNull(auth.currentUser)
            assertEquals(1, credentials.cleared)
            // The copy on the phone is gone (read before the server read caches it again); the server keeps it.
            assertFalse(cacheHas(path))
            assertTrue(serverHas(path))
        }

    @Test
    fun signOutAnywayDropsAWriteNoListenerSawThenEndsTheSession() =
        emulatorTest {
            val token = googleIdToken("unsent-${UUID.randomUUID()}@example.com")
            signIn(token)
            val before = userData.firestore()
            assertSame(before, userData.firestore())
            before.disableNetwork().await()
            val path = "sign-out/${UUID.randomUUID()}"
            // Queued and never sent: the network is off, and no listener is open on it.
            before.document(path).set(mapOf("sent" to false))
            val signOut = signOut()

            assertEquals(SignOutResult.ConfirmUnsentChanges(unsentChangesSeen = false), signOut())
            assertNotNull(auth.currentUser)
            assertEquals(SignOutResult.SignedOut, signOut.discardingUnsentChanges())
            assertNull(auth.currentUser)
            assertEquals(1, credentials.cleared)

            // The same user on a new instance, network on: a write queue that survived the sign-out is sent now.
            signIn(token)
            val after = userData.firestore()
            assertNotSame(before, after)
            after.waitForPendingWrites().await()
            assertFalse(serverHas(path))
        }

    @Test
    fun aWaitThatAUserChangeEndsIsAFailedWait() =
        emulatorTest {
            signIn(googleIdToken("change-${UUID.randomUUID()}@example.com"))
            val firestore = userData.firestore()
            firestore.disableNetwork().await()
            firestore.document("sign-out/${UUID.randomUUID()}").set(mapOf("sent" to false))
            // UNDISPATCHED: the wait is registered with Firestore before the user changes.
            val wait = async(start = CoroutineStart.UNDISPATCHED) { userData.awaitPendingWrites() }

            auth.signOut()

            assertFalse(wait.await())
        }

    @Test
    fun aWaitWhileASignOutClearsIsAFailedWait() =
        emulatorTest {
            // UNDISPATCHED: when async returns, clear() has terminated the instance and waits for Firestore.
            val clearing = async(start = CoroutineStart.UNDISPATCHED) { userData.clear() }

            // A second "Sign out" while the first still clears (its screen went away): ask first, throw nothing.
            assertFalse(userData.awaitPendingWrites())
            assertTrue(clearing.await())
        }

    @Test
    fun aCancelledWaitPassesTheCancellationOn() =
        emulatorTest {
            val firestore = userData.firestore()
            firestore.disableNetwork().await()
            firestore.document("sign-out/${UUID.randomUUID()}").set(mapOf("sent" to false))
            var answer: Boolean? = null
            // UNDISPATCHED: the wait is registered with Firestore before its caller goes away.
            val waiting = launch(start = CoroutineStart.UNDISPATCHED) { answer = userData.awaitPendingWrites() }

            waiting.cancelAndJoin()

            // LocalUserData throws CancellationException and nothing else: a cancelled caller gets no answer.
            assertNull(answer)
        }

    @Test
    fun aClearWhoseCallerIsCancelledStillDeletesTheCopy() =
        emulatorTest {
            val path = "sign-out/${UUID.randomUUID()}"
            userData
                .firestore()
                .document(path)
                .set(mapOf("sent" to true))
                .await()
            assertTrue(cacheHas(path))

            launch {
                cancel() // the caller is gone before clear() starts
                userData.clear()
            }.join()

            assertFalse(cacheHas(path))
        }

    @Test
    fun aCopyThatCannotBeDeletedFailsTheSignOutAndKeepsTheSession() =
        emulatorTest {
            signIn(googleIdToken("stuck-${UUID.randomUUID()}@example.com"))
            val before = userData.firestore()
            before
                .document("sign-out/${UUID.randomUUID()}")
                .set(mapOf("sent" to true))
                .await()
            // The first half of a clear, then a databases directory the app cannot write: clearPersistence fails.
            before.terminate().await()
            val databases = checkNotNull(app.applicationContext.getDatabasePath("firestore").parentFile)
            assertTrue(databases.setWritable(false, false))
            val result =
                try {
                    signOut().discardingUnsentChanges()
                } finally {
                    databases.setWritable(true) // owner only: the app, its owner, is the only one that writes there
                }

            assertEquals(SignOutResult.Failed, result)
            assertNotNull(auth.currentUser)
            assertEquals(0, credentials.cleared)
            assertNotSame(before, userData.firestore())
        }

    /**
     * M1-89 (#357): Firebase signs out by itself when a token refresh is refused, here because the account was
     * disabled, and the signed-out cleanup then deletes the copy on the phone. Disabled, not deleted: firebase-auth
     * 25.0.0 signs out on USER_DISABLED, USER_NOT_FOUND (Firebase's answer for a deleted account) and TOKEN_EXPIRED (a
     * changed password), but the emulator answers a deleted account's refresh with INVALID_REFRESH_TOKEN.
     */
    @Test
    fun aSessionFirebaseEndsByItselfLeavesNoCopyOnThePhone() =
        emulatorTest {
            signIn(googleIdToken("disabled-${UUID.randomUUID()}@example.com"))
            val user = checkNotNull(auth.currentUser)
            val path = "sign-out/${UUID.randomUUID()}"
            userData
                .firestore()
                .document(path)
                .set(mapOf("sent" to true))
                .await()
            assertTrue(cacheHas(path))
            val watched = ReportedClears(userData)
            SignedOutCleanup(authentication, watched, externalScope).start()

            FirebaseEmulator.disableUser(user.uid)
            val refused =
                try {
                    user.getIdToken(true).await()
                    null
                } catch (expected: FirebaseAuthInvalidUserException) {
                    expected
                }

            assertEquals("ERROR_USER_DISABLED", refused?.errorCode)
            // Nothing here signed out: Firebase did, and the watcher cleared at that change.
            assertTrue(watched.answers.receive())
            assertNull(auth.currentUser)
            assertFalse(cacheHas(path))
        }

    @Test
    fun theAuthRecordKeepsTheGoogleNameEmailAndPhotoLink() =
        emulatorTest {
            // Privacy Q5 (docs/privacy section 2): what the Firebase Auth record keeps from a Google sign-in.
            val email = "record-${UUID.randomUUID()}@example.com"

            assertEquals(
                GoogleSignInResult.SignedIn,
                authentication.signInWithGoogle(googleIdToken(email, NAME, PHOTO)),
            )

            val user = checkNotNull(auth.currentUser)
            user.reload().await() // what the server keeps, not what the sign-in answered
            assertEquals(listOf(NAME, email, PHOTO), listOf(user.displayName, user.email, user.photoUrl?.toString()))
            val google = user.providerData.single { it.providerId == GoogleAuthProvider.PROVIDER_ID }
            assertEquals(
                listOf(googleAccountId(email), NAME, email, PHOTO),
                listOf(google.uid, google.displayName, google.email, google.photoUrl?.toString()),
            )
        }

    @Test
    fun theProfileIsTheSignedInNameAndEmailAndEmptyAfterSignOut() =
        emulatorTest {
            val email = "profile-${UUID.randomUUID()}@example.com"
            assertEquals(AccountProfile(null, null), authentication.current())

            authentication.signInWithGoogle(googleIdToken(email, NAME))
            assertEquals(AccountProfile(NAME, email), authentication.current())

            signOut().discardingUnsentChanges()
            assertEquals(AccountProfile(null, null), authentication.current())
        }

    @Test
    fun aBlankGoogleNameIsNoName() =
        emulatorTest {
            val email = "blank-${UUID.randomUUID()}@example.com"
            authentication.signInWithGoogle(googleIdToken(email, "  "))
            assertEquals(AccountProfile(null, email), authentication.current())
        }

    private suspend fun signIn(token: String) {
        auth.signInWithCredential(GoogleAuthProvider.getCredential(token, null)).await()
    }

    /** Firestore fails a cache read of a document its cache does not hold. */
    private suspend fun cacheHas(path: String) =
        try {
            userData
                .firestore()
                .document(path)
                .get(Source.CACHE)
                .await()
                .exists()
        } catch (expected: FirebaseFirestoreException) {
            false
        }

    private suspend fun serverHas(path: String) =
        userData
            .firestore()
            .document(path)
            .get(Source.SERVER)
            .await()
            .exists()

    private fun signOut() =
        SignOut(
            connectivity = { true },
            userData = userData,
            authentication = authentication,
            credentials = credentials,
            externalScope = externalScope,
            pendingWritesTimeoutMs = PENDING_WRITES_TIMEOUT_MS,
        )

    /** The Auth emulator takes strict JSON claims as a fake Google ID token; `sub` is the Google account id. */
    private fun googleIdToken(
        email: String,
        name: String? = null,
        photo: String? = null,
    ) = JSONObject()
        .put("sub", googleAccountId(email))
        .put("email", email)
        .put("email_verified", true)
        .putOpt("name", name)
        .putOpt("picture", photo)
        .toString()

    private fun googleAccountId(email: String) = "google-$email"

    /** A hung emulator call fails its test instead of the whole `ui` job. */
    private fun emulatorTest(block: suspend CoroutineScope.() -> Unit) {
        runBlocking { withTimeout(TEST_TIMEOUT_MS, block) }
    }

    /** The copy on the phone, reporting each clear's answer, so a test can wait for the signed-out cleanup. */
    private class ReportedClears(
        private val userData: LocalUserData,
    ) : LocalUserData by userData {
        val answers = Channel<Boolean>(Channel.UNLIMITED)

        override suspend fun clear(): Boolean = userData.clear().also { answers.send(it) }
    }

    /** Credential Manager is M1-66's: here only that sign-out clears its state. */
    private class FakeCredentialState : GoogleCredentials {
        var cleared = 0

        override suspend fun idToken(): GoogleIdToken = GoogleIdToken.Failed

        override suspend fun clearCredentialState() {
            cleared++
        }
    }

    private companion object {
        const val TEST_TIMEOUT_MS = 60_000L
        const val PENDING_WRITES_TIMEOUT_MS = 2_000L
        const val NAME = "Test Person"
        const val PHOTO = "https://example.com/photo.png"
    }
}
