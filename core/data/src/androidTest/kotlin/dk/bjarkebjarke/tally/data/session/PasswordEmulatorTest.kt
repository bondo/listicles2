package dk.bjarkebjarke.tally.data.session

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.google.firebase.auth.FirebaseAuth
import com.google.firebase.auth.GoogleAuthProvider
import dk.bjarkebjarke.tally.data.FirebaseEmulator
import dk.bjarkebjarke.tally.domain.session.GoogleSignInResult
import dk.bjarkebjarke.tally.domain.session.PasswordAccount
import dk.bjarkebjarke.tally.domain.session.PasswordAnswer
import dk.bjarkebjarke.tally.domain.session.PasswordResetResult
import dk.bjarkebjarke.tally.domain.session.PasswordSignInResult
import dk.bjarkebjarke.tally.domain.session.SignUpResult
import dk.bjarkebjarke.tally.domain.session.VerificationResult
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.launch
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.tasks.await
import kotlinx.coroutines.withTimeout
import org.json.JSONObject
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import java.util.Locale
import java.util.UUID

/**
 * M1-121: email and password (M1.md, M1-15) against the Auth emulator with email enumeration protection on, as in the
 * real project (M1-O1). What these record about Firebase is checked once in the real project before the app relies on
 * it: M1-O19 the password cases, M3-O4 those with Google (Google sign-in is off in v1).
 */
@RunWith(AndroidJUnit4::class)
class PasswordEmulatorTest {
    private lateinit var auth: FirebaseAuth
    private lateinit var password: FirebasePasswordAuthentication
    private lateinit var account: PasswordAccount
    private var privacyBefore: Boolean? = null

    @Before
    fun setUp() {
        FirebaseEmulator.requireRunning()
        auth =
            FirebaseAuth.getInstance(FirebaseEmulator.app(InstrumentationRegistry.getInstrumentation().targetContext))
        auth.signOut()
        password = FirebasePasswordAuthentication(auth)
        account = PasswordAccount(connectivity = { true }, authentication = password, nowMs = { 0L })
        privacyBefore = FirebaseEmulator.emailPrivacy(on = true)
    }

    @After
    fun tearDown() {
        if (::auth.isInitialized) auth.signOut()
        privacyBefore?.let { FirebaseEmulator.emailPrivacy(on = it) }
    }

    @Test
    fun aNewEmailSignsUpSignedInUnverifiedWithOneVerificationEmail() =
        emulatorTest {
            val email = email("new")

            assertEquals(SignUpResult.CheckYourEmail, account.createAccount(" $email ", PASSWORD) {})

            assertEquals(email, auth.currentUser?.email)
            assertEquals(
                false,
                auth.currentUser
                    ?.getIdToken(false)
                    ?.await()
                    ?.claims
                    ?.get("email_verified"),
            )
            assertEquals(1, FirebaseEmulator.oobCodes(email, VERIFY).size)
        }

    /** R3-01, AUTH-10: the same answer as a new email, and no second account, no session and no email. */
    @Test
    fun anEmailWithAPasswordOrOnlyGoogleSignsUpNobodyAndSendsNothing() =
        emulatorTest {
            val withPassword = email("password")
            auth.createUserWithEmailAndPassword(withPassword, PASSWORD).await()
            val onlyGoogle = email("google")
            signInWithGoogle(onlyGoogle)

            for (email in listOf(withPassword, onlyGoogle)) {
                val before = FirebaseEmulator.accounts(email).getJSONObject(0).getString("localId")
                auth.signOut()

                assertEquals(PasswordAnswer.EmailInUse, password.createUser(email, OTHER_PASSWORD))
                assertEquals(SignUpResult.CheckYourEmail, account.createAccount(email, OTHER_PASSWORD) {})

                assertNull(auth.currentUser)
                val accounts = FirebaseEmulator.accounts(email)
                assertEquals(
                    listOf(before),
                    List(accounts.length()) { accounts.getJSONObject(it).getString("localId") },
                )
                assertEquals(emptyList<String>(), FirebaseEmulator.oobCodes(email, VERIFY))
            }
        }

    /** OQ-34(c), AUTH-10: one `INVALID_LOGIN_CREDENTIALS` whatever is wrong; a disabled account answers the same. */
    @Test
    fun aWrongPasswordAnUnknownEmailOnlyGoogleAndADisabledAccountAreOneRefusal() =
        emulatorTest {
            val withPassword = email("refused")
            auth.createUserWithEmailAndPassword(withPassword, PASSWORD).await()
            val onlyGoogle = email("google")
            signInWithGoogle(onlyGoogle)
            val disabled = email("disabled")
            auth.createUserWithEmailAndPassword(disabled, PASSWORD).await()
            FirebaseEmulator.disableUser(checkNotNull(auth.currentUser).uid)
            auth.signOut()
            val tries =
                listOf(
                    withPassword to OTHER_PASSWORD,
                    email("unknown") to PASSWORD,
                    onlyGoogle to PASSWORD,
                    disabled to PASSWORD,
                )

            for ((email, tried) in tries) {
                assertEquals(email, PasswordAnswer.Refused, password.signIn(email, tried))
                assertEquals(email, PasswordSignInResult.WrongEmailOrPassword, account.signIn(email, tried))
                assertNull(auth.currentUser)
            }
            assertEquals(PasswordSignInResult.SignedIn, account.signIn(withPassword, PASSWORD))
            assertEquals(withPassword, auth.currentUser?.email)
        }

    /** AUTH-08, AUTH-10: the same answer for every email; only an email with an account gets one. */
    @Test
    fun aResetAnswersTheSameAndSendsOnlyToAnAccount() =
        emulatorTest {
            val withPassword = email("reset")
            auth.createUserWithEmailAndPassword(withPassword, PASSWORD).await()
            auth.signOut()
            val unknown = email("unknown")

            for (email in listOf(withPassword, unknown)) {
                assertEquals(PasswordAnswer.Done, password.sendPasswordReset(email))
                assertEquals(PasswordResetResult.SentIfAccountExists, account.resetPassword(email))
            }

            assertEquals(2, FirebaseEmulator.oobCodes(withPassword, RESET).size)
            assertEquals(emptyList<String>(), FirebaseEmulator.oobCodes(unknown, RESET))
        }

    /**
     * OQ-34(b), the reverse case: a reset for an email with only Google. Recorded on the Auth emulator
     * (firebase-tools 15.36.0): the email goes out; its link gives the same account (same uid, no data lost) a
     * password and removes Google from it; the next Google sign-in adds Google back to that account.
     */
    @Test
    fun aResetForOnlyGoogleGivesTheSameAccountAPassword() =
        emulatorTest {
            val email = email("google")
            val uid = signInWithGoogle(email)
            auth.signOut()

            assertEquals(PasswordResetResult.SentIfAccountExists, account.resetPassword(email))
            FirebaseEmulator.resetPassword(FirebaseEmulator.oobCodes(email, RESET).single(), OTHER_PASSWORD)

            assertEquals(PasswordSignInResult.SignedIn, account.signIn(email, OTHER_PASSWORD))
            assertEquals(uid, auth.currentUser?.uid)
            assertEquals(listOf("password"), providers(email))
            auth.signOut()
            assertEquals(uid, signInWithGoogle(email))
            assertEquals(setOf("password", GoogleAuthProvider.PROVIDER_ID), providers(email).toSet())
        }

    /** AUTH-06 and the M1-62 gate: closed until the link is opened and Continue renews the token, then open. */
    @Test
    fun theGateOpensWhenContinueFindsTheLinkOpened() =
        emulatorTest {
            val email = email("verify")
            val gate = Channel<Boolean>(Channel.UNLIMITED)
            val watching = launch { password.verified().collect { gate.send(it) } }
            assertFalse(gate.receive())
            account.createAccount(email, PASSWORD) {}

            assertEquals(VerificationResult.NotVerifiedYet, account.checkVerified())
            FirebaseEmulator.openVerificationLink(FirebaseEmulator.oobCodes(email, VERIFY).single())
            assertNull(gate.tryReceive().getOrNull()) // the link alone changes nothing on the phone

            assertEquals(VerificationResult.Verified, account.checkVerified())
            assertTrue(gate.receive())
            assertEquals(
                true,
                auth.currentUser
                    ?.getIdToken(false)
                    ?.await()
                    ?.claims
                    ?.get("email_verified"),
            )
            auth.signOut()
            assertFalse(gate.receive())
            watching.cancel()
        }

    @Test
    fun aGoogleAccountPassesTheGateAndNobodySignedInDoesNot() =
        emulatorTest {
            val gate = Channel<Boolean>(Channel.UNLIMITED)
            val watching = launch { password.verified().collect { gate.send(it) } }
            assertFalse(gate.receive())

            signInWithGoogle(email("google"))
            assertTrue(gate.receive())
            assertEquals(PasswordAnswer.Done, password.reloadEmailVerified())
            watching.cancel()
            auth.signOut()
            assertEquals(PasswordAnswer.NotSignedIn, password.reloadEmailVerified())
            assertEquals(PasswordAnswer.NotSignedIn, password.sendEmailVerification())
        }

    /**
     * M1.md docs check 3, wireframe 44: a Google account whose email has a password account and that Firebase does not
     * trust for the email (any but `@gmail.com`) fails, and nobody is signed in. The emulator trusts no provider by
     * domain: a Google token with `email_verified` false stands in for it.
     */
    @Test
    fun aGoogleAccountWhoseEmailHasAPasswordAccountIsTheCollision() =
        emulatorTest {
            val email = email("collision")
            auth.createUserWithEmailAndPassword(email, PASSWORD).await()
            auth.signOut()

            val token = googleIdToken(email, verified = false)
            assertEquals(
                GoogleSignInResult.EmailHasPasswordAccount,
                FirebaseAuthentication(auth).signInWithGoogle(token),
            )

            assertNull(auth.currentUser)
            assertEquals(listOf("password"), providers(email))
        }

    /** OQ-29: Firebase writes the next email in the app's language. */
    @Test
    fun useAppLanguageSetsTheLanguageOfTheNextEmail() {
        val before = Locale.getDefault()
        try {
            Locale.setDefault(Locale.forLanguageTag("da-DK"))
            password.useAppLanguage()
            assertEquals("da", auth.languageCode?.substringBefore('-'))
        } finally {
            Locale.setDefault(before)
            auth.useAppLanguage()
        }
    }

    private suspend fun signInWithGoogle(email: String): String {
        auth.signInWithCredential(GoogleAuthProvider.getCredential(googleIdToken(email), null)).await()
        return checkNotNull(auth.currentUser).uid
    }

    private fun providers(email: String): List<String> {
        val infos = FirebaseEmulator.accounts(email).getJSONObject(0).getJSONArray("providerUserInfo")
        return List(infos.length()) { infos.getJSONObject(it).getString("providerId") }
    }

    private fun email(kind: String) = "$kind-${UUID.randomUUID()}@example.com"

    /** The Auth emulator takes strict JSON claims as a fake Google ID token; `sub` is the Google account id. */
    private fun googleIdToken(
        email: String,
        verified: Boolean = true,
    ) = JSONObject()
        .put("sub", "google-$email")
        .put("email", email)
        .put("email_verified", verified)
        .toString()

    private fun emulatorTest(block: suspend CoroutineScope.() -> Unit) {
        runBlocking { withTimeout(TEST_TIMEOUT_MS, block) }
    }

    private companion object {
        const val TEST_TIMEOUT_MS = 60_000L
        const val PASSWORD = "correct horse battery"
        const val OTHER_PASSWORD = "another horse battery"
        const val VERIFY = "VERIFY_EMAIL"
        const val RESET = "PASSWORD_RESET"
    }
}
