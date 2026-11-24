package dk.bjarkebjarke.tally.domain.session

import dk.bjarkebjarke.tally.testing.FakeConnectivity
import dk.bjarkebjarke.tally.testing.FakePasswordAuthentication
import io.kotest.assertions.withClue
import io.kotest.core.spec.style.FunSpec
import io.kotest.matchers.collections.shouldBeEmpty
import io.kotest.matchers.shouldBe
import io.kotest.property.Arb
import io.kotest.property.arbitrary.Codepoint
import io.kotest.property.arbitrary.bind
import io.kotest.property.arbitrary.element
import io.kotest.property.arbitrary.filter
import io.kotest.property.arbitrary.int
import io.kotest.property.arbitrary.map
import io.kotest.property.arbitrary.string
import io.kotest.property.checkAll

private const val EMAIL = "anna@example.com"
private const val PASSWORD = "correct horse battery"
private val EMAILS = setOf("sendEmailVerification", "sendPasswordReset")

// BMP and non-BMP code points, never a lone surrogate; padding that Kotlin's trim() removes (M1-13).
private val anyCodePoints = Arb.int(0x20..0x1F64F).filter { it !in 0xD800..0xDFFF }.map { Codepoint(it) }
private val padding = Arb.string(0..4, Arb.element(' ', '\t', '\n', '\u00A0', '\u3000').map { Codepoint(it.code) })
private val addresses = Arb.string(1..40, anyCodePoints).filter { it.isNotBlank() && it == it.trim() }
private val passwords = Arb.bind(padding, Arb.string(12..40, anyCodePoints), padding) { a, core, b -> a + core + b }

/** A fake Firebase that answers [answer] to every call. */
private fun firebase(answer: PasswordAnswer = PasswordAnswer.Done) =
    FakePasswordAuthentication(answer, answer, answer, answer, answer)

private fun FakePasswordAuthentication.account(online: Boolean = true) = PasswordAccount(FakeConnectivity(online), this)

/** Every action the screens start (M1-17), with valid input. */
private val actions: List<suspend PasswordAccount.() -> Enum<*>> =
    listOf(
        { createAccount(EMAIL, PASSWORD) },
        { signIn(EMAIL, PASSWORD) },
        { resetPassword(EMAIL) },
        { sendVerificationAgain() },
        { checkVerified() },
    )

/** [action] answers what [table] says to each of Firebase's answers, and [otherwise] to the rest. */
private suspend fun <R> answers(
    action: suspend PasswordAccount.() -> R,
    otherwise: R,
    vararg table: Pair<PasswordAnswer, R>,
) = PasswordAnswer.entries.forEach { answer ->
    withClue(answer) { firebase(answer).account().action() shouldBe (table.toMap()[answer] ?: otherwise) }
}

/** M1-15 (AUTH-05..08, AUTH-10) with a fake Firebase: no answer tells whether an email has an account. */
class PasswordAccountTest :
    FunSpec({
        test("AUTH-10, R3-01: sign-up for an email that has an account ends like a new one, with no email") {
            PasswordAnswer.entries.forEach { sent ->
                val firebase = FakePasswordAuthentication(verificationAnswer = sent)
                firebase.account().createAccount(EMAIL, PASSWORD) shouldBe SignUpResult.CheckYourEmail
                firebase.steps shouldBe listOf("createUser", "useAppLanguage", "sendEmailVerification")
            }
            val taken = firebase(PasswordAnswer.EmailInUse)
            taken.account().createAccount(EMAIL, PASSWORD) shouldBe SignUpResult.CheckYourEmail
            taken.steps shouldBe listOf("createUser")
        }

        test("create account: Firebase's other answers") {
            answers(
                { createAccount(EMAIL, PASSWORD) },
                SignUpResult.Failed,
                PasswordAnswer.Done to SignUpResult.CheckYourEmail,
                PasswordAnswer.EmailInUse to SignUpResult.CheckYourEmail,
                PasswordAnswer.InvalidEmail to SignUpResult.InvalidEmail,
                PasswordAnswer.WeakPassword to SignUpResult.PasswordTooShort,
                PasswordAnswer.TooManyAttempts to SignUpResult.TooManyAttempts,
                PasswordAnswer.NoConnection to SignUpResult.NeedsConnection,
            )
        }

        test("OQ-34(c), AUTH-10: every refused sign-in is one message") {
            answers(
                { signIn(EMAIL, PASSWORD) },
                PasswordSignInResult.WrongEmailOrPassword,
                PasswordAnswer.Done to PasswordSignInResult.SignedIn,
                PasswordAnswer.TooManyAttempts to PasswordSignInResult.TooManyAttempts,
                PasswordAnswer.NoConnection to PasswordSignInResult.NeedsConnection,
            )
        }

        test("AUTH-08, AUTH-10: a reset answers the same whether or not the email has an account") {
            answers(
                { resetPassword(EMAIL) },
                PasswordResetResult.Failed,
                PasswordAnswer.Done to PasswordResetResult.SentIfAccountExists,
                PasswordAnswer.Refused to PasswordResetResult.SentIfAccountExists,
                PasswordAnswer.InvalidEmail to PasswordResetResult.InvalidEmail,
                PasswordAnswer.TooManyAttempts to PasswordResetResult.TooManyAttempts,
                PasswordAnswer.NoConnection to PasswordResetResult.NeedsConnection,
            )
        }

        test("AUTH-06, AUTH-10: Send again and Continue answer with nobody signed in as for an unverified user") {
            answers(
                { sendVerificationAgain() },
                VerificationResult.Failed,
                PasswordAnswer.Done to VerificationResult.Sent,
                PasswordAnswer.NotSignedIn to VerificationResult.Sent,
                PasswordAnswer.TooManyAttempts to VerificationResult.TryAgainLater,
                PasswordAnswer.NoConnection to VerificationResult.NeedsConnection,
            )
            answers(
                { checkVerified() },
                VerificationResult.Failed,
                PasswordAnswer.Done to VerificationResult.Verified,
                PasswordAnswer.NotVerified to VerificationResult.NotVerifiedYet,
                PasswordAnswer.NotSignedIn to VerificationResult.NotVerifiedYet,
                PasswordAnswer.TooManyAttempts to VerificationResult.TryAgainLater,
                PasswordAnswer.NoConnection to VerificationResult.NeedsConnection,
            )
        }

        test("a blank email, an empty password or one under 12 code points (sign-up) never reaches Firebase") {
            checkAll(padding, Arb.string(0..11, anyCodePoints)) { blank, short ->
                val firebase = firebase()
                val account = firebase.account()
                account.createAccount(blank, PASSWORD) shouldBe SignUpResult.InvalidEmail
                account.createAccount(EMAIL, short) shouldBe SignUpResult.PasswordTooShort
                account.signIn(blank, PASSWORD) shouldBe PasswordSignInResult.WrongEmailOrPassword
                account.signIn(EMAIL, "") shouldBe PasswordSignInResult.WrongEmailOrPassword
                account.resetPassword(blank) shouldBe PasswordResetResult.InvalidEmail
                firebase.steps.shouldBeEmpty()
            }
        }

        test("the email reaches Firebase trimmed, the password exactly as typed") {
            checkAll(padding, addresses, padding, passwords) { before, address, after, password ->
                val firebase = firebase()
                val account = firebase.account()
                account.createAccount(before + address + after, password) shouldBe SignUpResult.CheckYourEmail
                account.signIn(before + address + after, password) shouldBe PasswordSignInResult.SignedIn
                account.resetPassword(before + address + after) shouldBe PasswordResetResult.SentIfAccountExists
                firebase.emails shouldBe listOf(address, address, address)
                firebase.passwords shouldBe listOf(password, password)
            }
        }

        test("OQ-29: every email goes out in the app's language, set right before it") {
            PasswordAnswer.entries.forEach { answer ->
                actions.forEach { action ->
                    val firebase = firebase(answer)
                    firebase.account().action()
                    val steps = firebase.steps
                    withClue("$answer: $steps") {
                        val emails = steps.indices.filter { steps[it] in EMAILS }
                        emails.forEach { steps.getOrNull(it - 1) shouldBe "useAppLanguage" }
                        steps.count { it == "useAppLanguage" } shouldBe emails.size
                    }
                }
            }
        }

        test("offline: every action needs a connection and asks Firebase nothing (SYNC-03)") {
            actions.forEach { action ->
                val firebase = firebase()
                firebase.account(online = false).action().name shouldBe "NeedsConnection"
                firebase.steps.shouldBeEmpty()
            }
        }
    })
