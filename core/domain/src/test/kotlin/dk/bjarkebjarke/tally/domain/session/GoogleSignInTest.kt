package dk.bjarkebjarke.tally.domain.session

import dk.bjarkebjarke.tally.testing.FakeAuthentication
import dk.bjarkebjarke.tally.testing.FakeConnectivity
import dk.bjarkebjarke.tally.testing.FakeGoogleCredentials
import io.kotest.core.spec.style.FunSpec
import io.kotest.matchers.shouldBe
import io.kotest.property.Arb
import io.kotest.property.arbitrary.string
import io.kotest.property.checkAll

/** M1-14 (AUTH-01): "Continue with Google" with a fake Credential Manager wrapper and a fake Firebase. */
class GoogleSignInTest :
    FunSpec({
        fun googleSignIn(
            answer: GoogleIdToken,
            authentication: FakeAuthentication = FakeAuthentication(),
            online: Boolean = true,
        ) = GoogleSignIn(FakeConnectivity(online), FakeGoogleCredentials(answer), authentication)

        test("the picked account's ID token goes to Firebase unchanged") {
            checkAll(Arb.string(1..200)) { token ->
                val authentication = FakeAuthentication()
                googleSignIn(GoogleIdToken.Picked(token), authentication)() shouldBe GoogleSignInResult.SignedIn
                authentication.googleIdTokens shouldBe listOf(token)
            }
        }

        test("Firebase refusing the token fails the sign-in") {
            val authentication = FakeAuthentication(googleResult = GoogleSignInResult.Failed)
            googleSignIn(GoogleIdToken.Picked("token"), authentication)() shouldBe GoogleSignInResult.Failed
        }

        test("cancel, no account or a failed picker: Firebase is never asked") {
            mapOf(
                GoogleIdToken.Cancelled to GoogleSignInResult.Cancelled,
                GoogleIdToken.NoAccount to GoogleSignInResult.NoAccount,
                GoogleIdToken.Failed to GoogleSignInResult.Failed,
            ).forEach { (answer, result) ->
                val authentication = FakeAuthentication()
                googleSignIn(answer, authentication)() shouldBe result
                authentication.steps shouldBe emptyList()
            }
        }

        test("offline: needs a connection and the picker is not shown") {
            val credentials = FakeGoogleCredentials()
            val authentication = FakeAuthentication()
            GoogleSignIn(FakeConnectivity(online = false), credentials, authentication)() shouldBe
                GoogleSignInResult.NeedsConnection
            credentials.steps shouldBe emptyList()
            authentication.steps shouldBe emptyList()
        }

        test("the ID token stays out of toString") {
            GoogleIdToken.Picked("secret-token").toString() shouldBe "Picked(token=***)"
        }
    })
