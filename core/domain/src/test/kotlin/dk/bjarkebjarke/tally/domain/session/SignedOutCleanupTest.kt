package dk.bjarkebjarke.tally.domain.session

import dk.bjarkebjarke.tally.testing.FakeLocalUserData
import dk.bjarkebjarke.tally.testing.FakeSessionState
import io.kotest.core.spec.style.FunSpec
import io.kotest.matchers.shouldBe
import io.kotest.property.Arb
import io.kotest.property.arbitrary.boolean
import io.kotest.property.arbitrary.list
import io.kotest.property.checkAll
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.flow.flow
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest

private val CLEARED = listOf("clear", "cleared")

/** What the watcher owes for [states], set one after another: one clear per run of signed-out states. */
private fun clearsFor(states: List<Boolean>): List<String> =
    states.indices.filter { !states[it] && (it == 0 || states[it - 1]) }.flatMap { CLEARED }

/** One phone: the session the test sets, the copy on the phone, and its watcher, not started yet. */
private class WatchedPhone(
    scope: CoroutineScope,
) {
    val steps = mutableListOf<String>()
    val session = FakeSessionState()
    val userData = FakeLocalUserData(steps = steps)
    val cleanup = SignedOutCleanup(session, userData, scope)
}

/**
 * M1-89 (#357): the copy on the phone goes whenever nobody is signed in, whoever ended the session. The external scope
 * is `backgroundScope`; `runCurrent` lets the watcher take each state before the test sets the next one.
 */
@OptIn(ExperimentalCoroutinesApi::class)
class SignedOutCleanupTest :
    FunSpec({
        test("one clear per run of signed-out states, a signed-out start included, and nothing else") {
            checkAll(Arb.list(Arb.boolean(), 1..20)) { states ->
                runTest {
                    val phone = WatchedPhone(backgroundScope)
                    phone.cleanup.start()
                    states.forEach {
                        phone.session.signedIn = it
                        runCurrent()
                    }
                    phone.steps shouldBe clearsFor(states)
                }
            }
        }

        test("the states that come while a clear runs are all handled after it, one clear at a time") {
            // A sign-in and a sign-out during a clear (a slow one) clear again: the watcher drops no state meanwhile.
            checkAll(Arb.list(Arb.boolean(), 0..20)) { later ->
                runTest {
                    val phone = WatchedPhone(backgroundScope)
                    val clearing = CompletableDeferred<Unit>()
                    phone.userData.clearGate = clearing
                    phone.cleanup.start()
                    (listOf(false) + later).forEach {
                        phone.session.signedIn = it
                        runCurrent()
                    }
                    phone.steps shouldBe listOf("clear")
                    clearing.complete(Unit)
                    runCurrent()
                    phone.steps shouldBe clearsFor(listOf(false) + later)
                }
            }
        }

        test("only start watches, and only its first call: a recreated activity starts no second watcher") {
            runTest {
                val phone = WatchedPhone(backgroundScope)
                phone.session.signedIn = false
                runCurrent()
                phone.steps shouldBe emptyList()
                repeat(3) { phone.cleanup.start() }
                runCurrent()
                phone.steps shouldBe CLEARED
            }
        }

        test("a clear that fails stops nothing: the next signed-out state clears again") {
            runTest {
                val phone = WatchedPhone(backgroundScope)
                phone.userData.clearFails = true
                phone.cleanup.start()
                listOf(false, true, false).forEach {
                    phone.session.signedIn = it
                    runCurrent()
                }
                phone.steps shouldBe CLEARED + CLEARED
            }
        }

        test("a session that fails counts as signed out, as at the start-up root") {
            runTest {
                val steps = mutableListOf<String>()
                val failing =
                    SessionState {
                        flow {
                            emit(true)
                            error("the session failed")
                        }
                    }
                SignedOutCleanup(failing, FakeLocalUserData(steps = steps), backgroundScope).start()
                runCurrent()
                steps shouldBe CLEARED
            }
        }
    })
