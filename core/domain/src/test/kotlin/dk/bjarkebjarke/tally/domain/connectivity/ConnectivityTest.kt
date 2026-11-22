package dk.bjarkebjarke.tally.domain.connectivity

import dk.bjarkebjarke.tally.testing.FakeConnectivity
import io.kotest.core.spec.style.FunSpec
import io.kotest.matchers.shouldBe
import io.kotest.property.Arb
import io.kotest.property.arbitrary.boolean
import io.kotest.property.arbitrary.list
import io.kotest.property.checkAll

/** M1-30 (SYNC-03): an action that needs the server runs only online; offline it says "needs a connection" instead. */
class ConnectivityTest :
    FunSpec({
        test("online, the action runs once and its value is returned") {
            var runs = 0
            val result = FakeConnectivity(online = true).whenOnline { runs++ }
            result shouldBe ConnectionResult.Done(0)
            (result as ConnectionResult.Done).value shouldBe 0
            runs shouldBe 1
        }

        test("offline, the action does not run and the result is NeedsConnection") {
            var runs = 0
            val result = FakeConnectivity(online = false).whenOnline { runs++ }
            result shouldBe ConnectionResult.NeedsConnection
            runs shouldBe 0
        }

        test("the connection is checked at every call, never remembered") {
            checkAll(Arb.list(Arb.boolean(), 0..20)) { states ->
                val fake = FakeConnectivity()
                val results =
                    states.map { online ->
                        fake.online = online
                        fake.whenOnline { "ran" }
                    }
                results shouldBe
                    states.map { if (it) ConnectionResult.Done("ran") else ConnectionResult.NeedsConnection }
            }
        }

        test("the fake is online unless the test says otherwise") {
            FakeConnectivity().isOnline() shouldBe true
        }
    })
