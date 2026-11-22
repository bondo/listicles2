package dk.bjarkebjarke.tally.domain.session

import dk.bjarkebjarke.tally.testing.FakeAuthentication
import dk.bjarkebjarke.tally.testing.FakeConnectivity
import dk.bjarkebjarke.tally.testing.FakeGoogleCredentials
import dk.bjarkebjarke.tally.testing.FakeLocalUserData
import io.kotest.core.spec.style.FunSpec
import io.kotest.matchers.shouldBe
import io.kotest.property.Arb
import io.kotest.property.arbitrary.boolean
import io.kotest.property.arbitrary.long
import io.kotest.property.arbitrary.orNull
import io.kotest.property.checkAll
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.launch
import kotlinx.coroutines.test.advanceTimeBy
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest

private const val WAIT = "awaitPendingWrites"
private val SIGNED_OUT = listOf("clear", "cleared", "signOut", "clearCredentialState")

/** One phone with fakes; [steps] is every fake's calls, in order. */
private class Phone(
    scope: CoroutineScope,
    online: Boolean = true,
    acknowledgeAfterMs: Long? = 0,
    timeoutMs: Long = SignOut.PENDING_WRITES_TIMEOUT_MS,
) {
    val steps = mutableListOf<String>()
    val userData = FakeLocalUserData(acknowledgeAfterMs = acknowledgeAfterMs, steps = steps)
    val signOut =
        SignOut(
            FakeConnectivity(online),
            userData,
            FakeAuthentication(steps = steps),
            FakeGoogleCredentials(steps = steps),
            scope,
            timeoutMs,
        )
}

/**
 * M1-14: sign out in the order of OQ-13 (docs/milestones/M1.md), with fakes for every step. `advanceTimeBy` and
 * `runCurrent` drive the virtual clock and also run `backgroundScope` work (the external scope), which
 * `advanceUntilIdle` would leave waiting.
 */
@OptIn(ExperimentalCoroutinesApi::class)
class SignOutTest :
    FunSpec({
        test("online: signed out in the decided order exactly when acknowledged before the timeout (whole ms)") {
            checkAll(Arb.long(1L..60_000L), Arb.long(0L..120_000L)) { timeoutMs, acknowledgeAfterMs ->
                runTest {
                    val phone = Phone(backgroundScope, acknowledgeAfterMs = acknowledgeAfterMs, timeoutMs = timeoutMs)
                    val sent = acknowledgeAfterMs < timeoutMs
                    phone.signOut() shouldBe
                        if (sent) SignOutResult.SignedOut else SignOutResult.ConfirmUnsentChanges(false)
                    phone.steps shouldBe if (sent) listOf(WAIT) + SIGNED_OUT else listOf(WAIT)
                }
            }
        }

        test("the timeout boundary: one millisecond less signs out, the timeout itself asks") {
            // The tie asks because kotlinx-coroutines-test runs the timeout, registered first, before the
            // acknowledgement due at the same virtual instant: a scheduler detail, not a product rule.
            runTest {
                val timeoutMs = SignOut.PENDING_WRITES_TIMEOUT_MS
                Phone(backgroundScope, acknowledgeAfterMs = timeoutMs - 1).signOut() shouldBe SignOutResult.SignedOut
                Phone(backgroundScope, acknowledgeAfterMs = timeoutMs).signOut() shouldBe
                    SignOutResult.ConfirmUnsentChanges(false)
            }
        }

        test("offline: always asks, never waits, clears nothing, whatever the queue holds") {
            checkAll(Arb.long(0L..120_000L).orNull(), Arb.boolean()) { acknowledgeAfterMs, seen ->
                runTest {
                    val phone = Phone(backgroundScope, online = false, acknowledgeAfterMs = acknowledgeAfterMs)
                    phone.userData.unsentChangesSeen = seen
                    phone.signOut() shouldBe SignOutResult.ConfirmUnsentChanges(seen)
                    phone.steps shouldBe emptyList()
                }
            }
        }

        test("a write no listener has seen still asks (wireframe 45); one a listener saw picks wireframe 39") {
            runTest {
                listOf(false, true).forEach { seen ->
                    val phone = Phone(backgroundScope, acknowledgeAfterMs = null)
                    phone.userData.unsentChangesSeen = seen
                    val question = phone.signOut()
                    question shouldBe SignOutResult.ConfirmUnsentChanges(seen)
                    // Reads the field too: equals() alone leaves its getter unexercised (PIT NO_COVERAGE mutant).
                    (question as SignOutResult.ConfirmUnsentChanges).unsentChangesSeen shouldBe seen
                    phone.steps shouldBe listOf(WAIT)
                }
            }
        }

        test("a failed wait (Firestore cancels it at a user change) asks too") {
            runTest {
                val phone = Phone(backgroundScope)
                phone.userData.waitFails = true
                phone.signOut() shouldBe SignOutResult.ConfirmUnsentChanges(false)
                phone.steps shouldBe listOf(WAIT)
            }
        }

        test("Sign out anyway after the question: signed out in the decided order") {
            runTest {
                val phone = Phone(backgroundScope, online = false)
                phone.signOut() shouldBe SignOutResult.ConfirmUnsentChanges(false)
                phone.signOut.discardingUnsentChanges() shouldBe SignOutResult.SignedOut
                phone.steps shouldBe SIGNED_OUT
            }
        }

        test("cancel: leaving during the wait keeps the session and the copy on the phone") {
            runTest {
                // Acknowledged after the caller left: a wait that outlived its caller would go on to steps 2 to 5.
                val phone = Phone(backgroundScope, acknowledgeAfterMs = 2_000)
                val caller = launch { phone.signOut() }
                advanceTimeBy(1_000)
                caller.cancel()
                advanceTimeBy(2 * SignOut.PENDING_WRITES_TIMEOUT_MS)
                runCurrent()
                phone.steps shouldBe listOf(WAIT)
            }
        }

        test("Firebase sign-out never starts before the copy on the phone is cleared") {
            runTest {
                val phone = Phone(backgroundScope)
                val clearing = CompletableDeferred<Unit>()
                phone.userData.clearGate = clearing
                launch { phone.signOut.discardingUnsentChanges() }
                runCurrent()
                phone.steps shouldBe listOf("clear")
                clearing.complete(Unit)
                runCurrent()
                phone.steps shouldBe SIGNED_OUT
            }
        }

        test("a copy that cannot be cleared keeps the session and the credential state") {
            runTest {
                val phone = Phone(backgroundScope)
                phone.userData.clearFails = true
                phone.signOut() shouldBe SignOutResult.Failed
                phone.steps shouldBe listOf(WAIT, "clear", "cleared")
            }
        }

        test("once started, the steps finish even when the asking screen goes away") {
            runTest {
                val phone = Phone(backgroundScope)
                val clearing = CompletableDeferred<Unit>()
                phone.userData.clearGate = clearing
                val caller = launch { phone.signOut.discardingUnsentChanges() }
                runCurrent()
                caller.cancel()
                clearing.complete(Unit)
                runCurrent()
                caller.isCancelled shouldBe true
                phone.steps shouldBe SIGNED_OUT
            }
        }
    })
