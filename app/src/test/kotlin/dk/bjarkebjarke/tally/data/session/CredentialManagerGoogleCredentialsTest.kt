package dk.bjarkebjarke.tally.data.session

import android.app.Activity
import android.app.Application
import android.content.Context
import android.os.Bundle
import androidx.credentials.ClearCredentialStateRequest
import androidx.credentials.Credential
import androidx.credentials.CredentialManager
import androidx.credentials.CredentialOption
import androidx.credentials.CustomCredential
import androidx.credentials.GetCredentialRequest
import androidx.credentials.GetCredentialResponse
import androidx.credentials.exceptions.ClearCredentialException
import androidx.credentials.exceptions.ClearCredentialUnknownException
import androidx.credentials.exceptions.GetCredentialCancellationException
import androidx.credentials.exceptions.GetCredentialProviderConfigurationException
import androidx.credentials.exceptions.GetCredentialUnknownException
import androidx.credentials.exceptions.NoCredentialException
import com.google.android.libraries.identity.googleid.GetSignInWithGoogleOption
import com.google.android.libraries.identity.googleid.GoogleIdTokenCredential
import dk.bjarkebjarke.tally.domain.session.GoogleIdToken
import io.kotest.matchers.collections.shouldBeEmpty
import io.kotest.matchers.shouldBe
import io.kotest.matchers.types.shouldBeInstanceOf
import io.kotest.matchers.types.shouldBeSameInstanceAs
import kotlinx.coroutines.CoroutineStart
import kotlinx.coroutines.awaitCancellation
import kotlinx.coroutines.launch
import kotlinx.coroutines.runBlocking
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.Robolectric
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config
import java.util.Base64

/**
 * M1-66: Credential Manager with the Sign in with Google button flow, against a fake Credential Manager (Google sign-in
 * is not enabled in Firebase yet, and unit tests have no network). Here in `:app`, the only module with the offline
 * Robolectric setup.
 */
@RunWith(RobolectricTestRunner::class)
@Config(application = Application::class)
class CredentialManagerGoogleCredentialsTest {
    private val activity = Robolectric.buildActivity(Activity::class.java).get()
    private val none: suspend () -> Credential = { throw NoCredentialException() }
    private val closed: suspend () -> Credential = { throw GetCredentialCancellationException() }

    private fun credentials(
        manager: FakeCredentialManager,
        foreground: Activity? = activity,
        webClientId: String = WEB_CLIENT_ID,
    ) = CredentialManagerGoogleCredentials(manager, { foreground }, webClientId)

    private fun idToken(manager: FakeCredentialManager) = runBlocking { credentials(manager).idToken() }

    @Test
    fun theButtonShowsEveryGoogleAccountAndAnswersThePickedIdToken() {
        val manager = FakeCredentialManager({ googleIdToken("someone") })

        idToken(manager) shouldBe GoogleIdToken.Picked(jwt("someone"))

        // Google's flow for a button: every account on the phone, not only those that signed in to the app before.
        manager.requests
            .single()
            .shouldBeInstanceOf<GetSignInWithGoogleOption>()
            .serverClientId shouldBe WEB_CLIENT_ID
        manager.contexts.single() shouldBeSameInstanceAs activity
    }

    /** A sign-out keeps an account's permission for the app: a picker of only such accounts would lock others out. */
    @Test
    fun afterAClosedPickerTheNextTapShowsEveryAccountAgain() {
        val manager = FakeCredentialManager(closed, { googleIdToken("other") })
        val credentials = credentials(manager)

        runBlocking { credentials.idToken() } shouldBe GoogleIdToken.Cancelled
        runBlocking { credentials.idToken() } shouldBe GoogleIdToken.Picked(jwt("other"))
        manager.requests.forEach { it.shouldBeInstanceOf<GetSignInWithGoogleOption>() }
    }

    /** The fake fails a request it has no answer for: each tap asks once. */
    @Test
    fun noAccountAClosedPickerAProviderErrorOrAnotherCredentialAreAnswers() {
        idToken(FakeCredentialManager(none)) shouldBe GoogleIdToken.NoAccount
        idToken(FakeCredentialManager(closed)) shouldBe GoogleIdToken.Cancelled
        idToken(FakeCredentialManager({ throw GetCredentialUnknownException() })) shouldBe GoogleIdToken.Failed
        idToken(FakeCredentialManager({ throw GetCredentialProviderConfigurationException() })) shouldBe
            GoogleIdToken.Failed
        // Another type with a Google ID token's data, and the right type with unreadable data.
        idToken(FakeCredentialManager({ CustomCredential("x", googleIdToken("x").data) })) shouldBe GoogleIdToken.Failed
        idToken(FakeCredentialManager({ CustomCredential(GOOGLE_ID_TOKEN, Bundle()) })) shouldBe GoogleIdToken.Failed
    }

    /** The Google ID library names a Sign in with Google subtype too; its data is a Google ID token all the same. */
    @Test
    fun theSignInWithGoogleSubtypeIsAGoogleIdTokenToo() {
        val siwg = GoogleIdTokenCredential.TYPE_GOOGLE_ID_TOKEN_SIWG_CREDENTIAL

        idToken(FakeCredentialManager({ CustomCredential(siwg, googleIdToken("subtype").data) })) shouldBe
            GoogleIdToken.Picked(jwt("subtype"))
    }

    @Test
    fun withoutAStartedActivityOrAWebClientIdNothingIsAsked() {
        val manager = FakeCredentialManager()

        runBlocking { credentials(manager, foreground = null).idToken() } shouldBe GoogleIdToken.Failed
        runBlocking { credentials(manager, webClientId = "").idToken() } shouldBe GoogleIdToken.Failed
        manager.requests.shouldBeEmpty()
    }

    @Test
    fun aCancelledCallerGetsNoAnswer() {
        val manager = FakeCredentialManager({ awaitCancellation() }) // the picker is still open
        var answer: GoogleIdToken? = null

        runBlocking {
            val picking = launch(start = CoroutineStart.UNDISPATCHED) { answer = credentials(manager).idToken() }
            picking.cancel()
            picking.join()
        }

        manager.requests.size shouldBe 1
        answer shouldBe null
    }

    @Test
    fun signOutClearsTheCredentialStateAndAFailedClearIsNoError() {
        val manager = FakeCredentialManager()
        val credentials = credentials(manager)

        runBlocking { credentials.clearCredentialState() }
        manager.clearError = ClearCredentialUnknownException()
        runBlocking { credentials.clearCredentialState() }

        manager.cleared shouldBe 2
    }

    /** What the Google ID provider answers: a custom credential that carries the [jwt] of [account]. */
    private fun googleIdToken(account: String) =
        CustomCredential(
            GOOGLE_ID_TOKEN,
            GoogleIdTokenCredential
                .Builder()
                .setId("someone@example.com")
                .setIdToken(jwt(account))
                .build()
                .data,
        )

    /** An unsigned ID token: the Google ID library reads its claims, so it has the form of a JWT. */
    private fun jwt(account: String): String {
        fun part(json: String) = Base64.getUrlEncoder().withoutPadding().encodeToString(json.toByteArray())
        return part("""{"alg":"RS256"}""") + "." + part("""{"sub":"$account"}""") + ".signature"
    }

    /**
     * Answers each request with the next of [answers], a credential or a thrown exception, and fails a request it has
     * no answer for. The members it does not override go to a real Credential Manager; the wrapper uses none of them.
     */
    private class FakeCredentialManager(
        vararg answers: suspend () -> Credential,
    ) : CredentialManager by CredentialManager.create(RuntimeEnvironment.getApplication()) {
        private val answers = ArrayDeque(answers.toList())
        val requests = mutableListOf<CredentialOption>()
        val contexts = mutableListOf<Context>()
        var clearError: ClearCredentialException? = null
        var cleared = 0

        override suspend fun getCredential(
            context: Context,
            request: GetCredentialRequest,
        ): GetCredentialResponse {
            contexts += context
            requests += request.credentialOptions.single()
            val answer = checkNotNull(answers.removeFirstOrNull()) { "asked once more than expected" }
            return GetCredentialResponse(answer())
        }

        override suspend fun clearCredentialState(request: ClearCredentialStateRequest) {
            cleared++
            clearError?.let { throw it }
        }
    }

    private companion object {
        const val WEB_CLIENT_ID = "123-web.apps.googleusercontent.com"
        const val GOOGLE_ID_TOKEN = GoogleIdTokenCredential.TYPE_GOOGLE_ID_TOKEN_CREDENTIAL
    }
}
