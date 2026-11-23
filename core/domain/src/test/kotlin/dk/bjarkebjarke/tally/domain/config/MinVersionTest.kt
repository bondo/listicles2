package dk.bjarkebjarke.tally.domain.config

import dk.bjarkebjarke.tally.testing.FakeMinVersionRemote
import dk.bjarkebjarke.tally.testing.FakeMinVersionStore
import io.kotest.core.spec.style.FunSpec
import io.kotest.matchers.shouldBe
import io.kotest.property.Arb
import io.kotest.property.arbitrary.long
import io.kotest.property.checkAll
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.test.runTest

private const val INSTALLED = 27L

class MinVersionTest :
    FunSpec({
        test("an app below the minimum must update, equal or above must not (START-01)") {
            checkAll(Arb.long(0L..1_000_000L), Arb.long(0L..1_000_000L)) { installed, min ->
                updateRequired(installed, min) shouldBe (installed < min)
            }
        }

        test("no minimum never requires an update") {
            checkAll(Arb.long(0L..1_000_000L)) { installed -> updateRequired(installed, null) shouldBe false }
        }

        test("below, equal and above the fetched minimum") {
            val store = FakeMinVersionStore()
            MinVersionGate(FakeMinVersionRemote(INSTALLED + 1), store, INSTALLED).updateRequired().first() shouldBe true
            MinVersionGate(FakeMinVersionRemote(INSTALLED), store, INSTALLED).updateRequired().first() shouldBe false
            MinVersionGate(FakeMinVersionRemote(INSTALLED - 1), store, INSTALLED).updateRequired().first() shouldBe
                false
        }

        test("a fetched minimum is remembered for the next offline start") {
            runTest {
                val store = FakeMinVersionStore()
                MinVersionGate(FakeMinVersionRemote(INSTALLED + 1), store, INSTALLED).updateRequired().first()
                store.last() shouldBe INSTALLED + 1
            }
        }

        test("a document without a minimum clears the gate and the remembered value") {
            val store = FakeMinVersionStore(INSTALLED + 1)
            MinVersionGate(FakeMinVersionRemote(null), store, INSTALLED).updateRequired().first() shouldBe false
            store.value shouldBe null
        }

        test("offline with a remembered minimum uses it") {
            MinVersionGate(FakeMinVersionRemote.offline(), FakeMinVersionStore(INSTALLED + 1), INSTALLED)
                .updateRequired()
                .first() shouldBe true
            MinVersionGate(FakeMinVersionRemote.offline(), FakeMinVersionStore(INSTALLED), INSTALLED)
                .updateRequired()
                .first() shouldBe false
        }

        test("offline without a remembered minimum starts normally: the gate fails open") {
            MinVersionGate(FakeMinVersionRemote.offline(), FakeMinVersionStore(), INSTALLED)
                .updateRequired()
                .first() shouldBe false
        }

        test("a fetch that never answers falls back to the remembered value after the timeout") {
            runTest {
                MinVersionGate(FakeMinVersionRemote.hanging(), FakeMinVersionStore(INSTALLED + 1), INSTALLED)
                    .updateRequired()
                    .first() shouldBe true
                MinVersionGate(FakeMinVersionRemote.hanging(), FakeMinVersionStore(), INSTALLED)
                    .updateRequired()
                    .first() shouldBe false
            }
        }
    })
