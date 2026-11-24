package dk.bjarkebjarke.tally.domain.session

import dk.bjarkebjarke.tally.testing.FakeConnectivity
import dk.bjarkebjarke.tally.testing.FakePasswordAuthentication
import io.kotest.assertions.withClue
import io.kotest.core.spec.style.FunSpec
import io.kotest.matchers.collections.shouldBeEmpty
import io.kotest.matchers.shouldBe
import io.kotest.property.Arb
import io.kotest.property.arbitrary.Codepoint
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
private val padding = Arb.string(0..4, Arb.element(' ', '\t', '\n', ' ', '　').map { Codepoint(it.code) })
private val addresses = Arb.string(1..40, anyCodePoints).filter { it.isNotBlank() && it == it.trim() }
private val passwords = Arb.string(12..40, anyCodePoints)

/** A phone whose fake Firebase answers [answer] to every call. */
private fun phone(
    answer: PasswordAnswer = PasswordAnswer.Done,
    online: Boolean = true,
): Pair<PasswordAccount, FakePasswordAuthentication> {
    val firebase = FakePasswordAuthentication().apply { answerEverything(answer) }
    return PasswordAccount(FakeConnectivity(online), firebase) to firebase
}

/** Every action the screens start (M1-17), with valid input. */
private val actions: List<suspend PasswordAccount.() -> Enum<*>> =
    listOf(
        { createAccount(EMAIL, PASSWORD) },
        { signIn(EMAIL, PASSWORD) },
        { resetPassword(EMAIL) },
        { sendVerificationAgain() },
        { checkVerified() },
    )

/** What [action] answers for each of Firebase's answers: [table], else [otherwise]. */
private suspend fun <R> answersFor(
    action: suspend PasswordAccount.() -> R,
    otherwise: R,
    vararg table: Pair<PasswordAnswer, R>,
) = PasswordAnswer.entries.forEach { answer ->
    withClue(answer) { phone(answer).first.action() shouldBe (table.toMap()[answer] ?: otherwise) }
}

/** M1-15 (AUTH-05..08, AUTH-10) with a fake Firebase: no answer tells whether an email has an account. */
class PasswordAccountTest :
    FunSpec({
        test("a new account gets its verification email; whatever that answers, the user checks their email") {
            PasswordAnswer.entries.forEach { sent ->
                val firebase = FakePasswordAuthentication(verificationAnswer = sent)
                val result = PasswordAccount(FakeConnectivity(true), firebase).createAccount(EMAIL, PASSWORD)
                result shouldBe CreateAccountResult.CheckYourEmail
                firebase.steps shouldBe listOf("createUser", "useAppLanguage", "sendEmailVerification")
            }
        }

        test("AUTH-10, R3-01: sign-up for an email that has an account ends the same, with no email") {
            val (account, firebase) = phone(PasswordAnswer.EmailInUse)
            account.createAccount(EMAIL, PASSWORD) shouldBe CreateAccountResult.CheckYourEmail
            firebase.steps shouldBe listOf("createUser")
        }

        test("create account: Firebase's other answers") {
            answersFor(
                { createAccount(EMAIL, PASSWORD) },
                CreateAccountResult.Failed,
                PasswordAnswer.Done to CreateAccountResult.CheckYourEmail,
                PasswordAnswer.EmailInUse to CreateAccountResult.CheckYourEmail,
                PasswordAnswer.InvalidEmail to CreateAccountResult.InvalidEmail,
                PasswordAnswer.WeakPassword to CreateAccountResult.PasswordTooShort,
                PasswordAnswer.TooManyAttempts to CreateAccountResult.TooManyAttempts,
                PasswordAnswer.NoConnection to CreateAccountResult.NeedsConnection,
            )
        }

        test("create account: a blank email or a password under 12 code points never reaches Firebase") {
            checkAll(padding, Arb.string(0..11, anyCodePoints)) { blank, short ->
                val (account, firebase) = phone()
                account.createAccount(blank, PASSWORD) shouldBe CreateAccountResult.InvalidEmail
                account.createAccount(EMAIL, short) shouldBe CreateAccountResult.PasswordTooShort
                firebase.steps.shouldBeEmpty()
            }
        }

        test("the email reaches Firebase trimmed, the password exactly as typed") {
            checkAll(padding, addresses, padding, passwords) { before, address, after, password ->
                val (account, firebase) = phone()
                val typed = before + address + after
                account.createAccount(typed, password) shouldBe CreateAccountResult.CheckYourEmail
                account.signIn(typed, password) shouldBe PasswordSignInResult.SignedIn
                account.resetPassword(typed) shouldBe PasswordResetResult.SentIfAccountExists
                firebase.emails shouldBe listOf(address, address, address)
                firebase.passwords shouldBe listOf(password, password)
            }
        }

        test("OQ-34(c), AUTH-10: every refused sign-in is one message") {
            answersFor(
                { signIn(EMAIL, PASSWORD) },
                PasswordSignInResult.WrongEmailOrPassword,
                PasswordAnswer.Done to PasswordSignInResult.SignedIn,
                PasswordAnswer.TooManyAttempts to PasswordSignInResult.TooManyAttempts,
                PasswordAnswer.NoConnection to PasswordSignInResult.NeedsConnection,
            )
        }

        test("a blank email or an empty password is refused without asking Firebase") {
            checkAll(padding) { blank ->
                val (account, firebase) = phone()
                account.signIn(blank, PASSWORD) shouldBe PasswordSignInResult.WrongEmailOrPassword
                account.signIn(EMAIL, "") shouldBe PasswordSignInResult.WrongEmailOrPassword
                account.resetPassword(blank) shouldBe PasswordResetResult.InvalidEmail
                firebase.steps.shouldBeEmpty()
            }
        }

        test("AUTH-08, AUTH-10: a reset answers the same whether or not the email has an account") {
            answersFor(
                { resetPassword(EMAIL) },
                PasswordResetResult.Failed,
                PasswordAnswer.Done to PasswordResetResult.SentIfAccountExists,
                PasswordAnswer.Refused to PasswordResetResult.SentIfAccountExists,
                PasswordAnswer.InvalidEmail to PasswordResetResult.InvalidEmail,
                PasswordAnswer.TooManyAttempts to PasswordResetResult.TooManyAttempts,
                PasswordAnswer.NoConnection to PasswordResetResult.NeedsConnection,
            )
        }

        test("AUTH-06, AUTH-10: Send again answers the same with nobody signed in") {
            answersFor(
                { sendVerificationAgain() },
                VerificationResult.Failed,
                PasswordAnswer.Done to VerificationResult.Sent,
                PasswordAnswer.NotSignedIn to VerificationResult.Sent,
                PasswordAnswer.TooManyAttempts to VerificationResult.TryAgainLater,
                PasswordAnswer.NoConnection to VerificationResult.NeedsConnection,
            )
        }

        test("AUTH-06, AUTH-10: Continue is not verified yet with nobody signed in, as for an unverified user") {
            answersFor(
                { checkVerified() },
                VerificationResult.Failed,
                PasswordAnswer.Done to VerificationResult.Verified,
                PasswordAnswer.NotVerified to VerificationResult.NotVerifiedYet,
                PasswordAnswer.NotSignedIn to VerificationResult.NotVerifiedYet,
                PasswordAnswer.TooManyAttempts to VerificationResult.TryAgainLater,
                PasswordAnswer.NoConnection to VerificationResult.NeedsConnection,
            )
        }

        test("OQ-29: every email goes out in the app's language, set right before it") {
            PasswordAnswer.entries.forEach { answer ->
                actions.forEach { action ->
                    val (account, firebase) = phone(answer)
                    account.action()
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
                val (account, firebase) = phone(online = false)
                account.action().name shouldBe "NeedsConnection"
                firebase.steps.shouldBeEmpty()
            }
        }
    })
