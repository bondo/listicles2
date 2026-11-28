package dk.bjarkebjarke.tally.data.session

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.google.firebase.auth.FirebaseAuth
import com.google.firebase.auth.GoogleAuthProvider
import dk.bjarkebjarke.tally.data.FirebaseEmulator
import dk.bjarkebjarke.tally.domain.session.PasswordAccount
import dk.bjarkebjarke.tally.domain.session.PasswordAnswer
import dk.bjarkebjarke.tally.domain.session.PasswordResetResult
import dk.bjarkebjarke.tally.domain.session.PasswordSignInResult
import dk.bjarkebjarke.tally.domain.session.SignUpResult
import dk.bjarkebjarke.tally.domain.session.VerificationResult
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.tasks.await
import kotlinx.coroutines.withTimeout
import org.json.JSONObject
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import java.util.UUID

/**
 * M1-121: email and password (M1.md, M1-15) against the Auth emulator with email enumeration protection on, as in the
 * real project (M1-O1). What these record about Firebase is checked once in the real project before the app relies on
 * it: M1-O20 the password cases, and with Google (off in v1) M1-128 adds one.
 */
@RunWith(AndroidJUnit4::class)
class PasswordEmulatorTest {
    private lateinit var auth: FirebaseAuth
    private lateinit var password: FirebasePasswordAuthentication
    private lateinit var account: PasswordAccount

    @Before
    fun setUp() {
        FirebaseEmulator.requireRunning()
        auth =
            FirebaseAuth.getInstance(FirebaseEmulator.app(InstrumentationRegistry.getInstrumentation().targetContext))
        auth.signOut()
        password = FirebasePasswordAuthentication(auth)
        account = PasswordAccount(connectivity = { true }, authentication = password, nowMs = { 0L })
        FirebaseEmulator.emailPrivacy(on = true)
    }

    @After
    fun tearDown() {
        if (::auth.isInitialized) auth.signOut()
        FirebaseEmulator.emailPrivacy(on = false) // the emulator's default, which the other tests expect
    }

    @Test
    fun aNewEmailSignsUpSignedInUnverifiedWithOneVerificationEmail() =
        emulatorTest {
            val email = email("new")

            assertEquals(SignUpResult.CheckYourEmail, account.createAccount(" $email ", PASSWORD) {})

            assertEquals(email, auth.currentUser?.email)
            assertEquals(false, emailVerifiedClaim())
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
            val onlyGoogle = email("google")
            signInWithGoogle(onlyGoogle)
            auth.signOut()
            val unknown = email("unknown")

            for (email in listOf(withPassword, onlyGoogle, unknown)) {
                assertEquals(PasswordAnswer.Done, password.sendPasswordReset(email))
                assertEquals(PasswordResetResult.SentIfAccountExists, account.resetPassword(email))
            }

            assertEquals(2, FirebaseEmulator.oobCodes(withPassword, RESET).size)
            assertEquals(2, FirebaseEmulator.oobCodes(onlyGoogle, RESET).size) // OQ-34(b): its link is M1-128's
            assertEquals(emptyList<String>(), FirebaseEmulator.oobCodes(unknown, RESET))
        }

    /**
     * AUTH-06: Continue answers not verified until the link is opened, then verified with a new ID token whose
     * `email_verified` claim is true at once: the token Firestore sends to the rules (M1-127 gates on it).
     */
    @Test
    fun continueIsVerifiedOnceTheLinkIsOpenedWithTheClaimRenewed() =
        emulatorTest {
            val email = email("verify")
            assertEquals(SignUpResult.CheckYourEmail, account.createAccount(email, PASSWORD) {})

            assertEquals(VerificationResult.NotVerifiedYet, account.checkVerified())
            FirebaseEmulator.openVerificationLink(FirebaseEmulator.oobCodes(email, VERIFY).single())
            assertEquals(false, emailVerifiedClaim()) // the link alone changes nothing on the phone

            assertEquals(VerificationResult.Verified, account.checkVerified())
            assertEquals(true, emailVerifiedClaim())
            auth.signOut() // with nobody signed in, nothing is sent or checked
            assertEquals(PasswordAnswer.NotSignedIn, password.reloadEmailVerified())
            assertEquals(PasswordAnswer.NotSignedIn, password.sendEmailVerification())
        }

    private suspend fun signInWithGoogle(email: String): String {
        auth.signInWithCredential(GoogleAuthProvider.getCredential(googleIdToken(email), null)).await()
        return checkNotNull(auth.currentUser).uid
    }

    private suspend fun emailVerifiedClaim() =
        checkNotNull(auth.currentUser)
            .getIdToken(false)
            .await()
            .claims["email_verified"]

    private fun email(kind: String) = "$kind-${UUID.randomUUID()}@example.com"

    /** The Auth emulator takes strict JSON claims as a fake Google ID token; `sub` is the Google account id. */
    private fun googleIdToken(email: String) =
        JSONObject()
            .put("sub", "google-$email")
            .put("email", email)
            .put("email_verified", true)
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
