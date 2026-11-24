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
import kotlinx.coroutines.job
import kotlinx.coroutines.test.TestScope
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

/** Signs out, holds that clear while the [later] states come, then lets it end: the steps while held and at the end. */
@OptIn(ExperimentalCoroutinesApi::class)
private fun TestScope.heldClear(later: List<Boolean>): Pair<List<String>, List<String>> {
    val phone = WatchedPhone(backgroundScope)
    val clearing = CompletableDeferred<Unit>()
    phone.userData.clearGate = clearing
    phone.cleanup.start()
    (listOf(false) + later).forEach {
        phone.session.signedIn = it
        runCurrent()
    }
    val held = phone.steps.toList()
    clearing.complete(Unit)
    runCurrent()
    return held to phone.steps
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

        test("one clear at a time; when it ends only the latest state counts, and only after a change") {
            // Nothing is written to the copy while a clear runs, so a session that came and went meanwhile needs one
            // more clear at most, and one that is signed in again needs none: its copy is live.
            checkAll(Arb.list(Arb.boolean(), 0..20)) { later ->
                runTest {
                    val (held, steps) = heldClear(later)
                    held shouldBe listOf("clear")
                    steps shouldBe if (true in later && !later.last()) CLEARED + CLEARED else CLEARED
                }
            }
        }

        test("a sign-out, then a sign-in again, both while a clear runs: the live session keeps its copy") {
            runTest { heldClear(listOf(true, false, true)).second shouldBe CLEARED }
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

        test("a session that fails counts as signed out, as at the start-up root, and ends the watch") {
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
                backgroundScope.coroutineContext.job.children
                    .none() shouldBe true
            }
        }
    })
