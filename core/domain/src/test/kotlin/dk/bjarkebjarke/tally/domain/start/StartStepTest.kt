package dk.bjarkebjarke.tally.domain.start

import io.kotest.core.spec.style.FunSpec
import io.kotest.matchers.shouldBe
import io.kotest.property.Arb
import io.kotest.property.arbitrary.bind
import io.kotest.property.arbitrary.boolean
import io.kotest.property.arbitrary.enum
import io.kotest.property.arbitrary.orNull
import io.kotest.property.checkAll

private val anyFacts: Arb<StartFacts> =
    Arb.bind(
        Arb.boolean(),
        Arb.boolean(),
        Arb.boolean(),
        Arb.boolean(),
        Arb.enum<HouseholdNotice>().orNull(),
        ::StartFacts,
    )

private val allGood =
    StartFacts(updateRequired = false, signedIn = true, emailVerified = true, nameSaved = true, notice = null)

class StartStepTest :
    FunSpec({
        test("nothing in the way opens the home") {
            startStep(allGood) shouldBe StartStep.Home
        }

        test("each gate alone stops the start on its own step") {
            startStep(allGood.copy(updateRequired = true)) shouldBe StartStep.Update
            startStep(allGood.copy(signedIn = false)) shouldBe StartStep.SignIn
            startStep(allGood.copy(emailVerified = false)) shouldBe StartStep.VerifyEmail
            startStep(allGood.copy(nameSaved = false)) shouldBe StartStep.EnterName
            startStep(allGood.copy(notice = HouseholdNotice.Removed)) shouldBe StartStep.Notice(HouseholdNotice.Removed)
            startStep(allGood.copy(notice = HouseholdNotice.HouseholdDeleted)) shouldBe
                StartStep.Notice(HouseholdNotice.HouseholdDeleted)
        }

        test("the step is the first failing gate in the order update, signed in, verified, name, notice (P10)") {
            checkAll(anyFacts) { f ->
                val expected =
                    when {
                        f.updateRequired -> StartStep.Update
                        !f.signedIn -> StartStep.SignIn
                        !f.emailVerified -> StartStep.VerifyEmail
                        !f.nameSaved -> StartStep.EnterName
                        f.notice != null -> StartStep.Notice(f.notice)
                        else -> StartStep.Home
                    }
                startStep(f) shouldBe expected
            }
        }

        test("signed out ignores every later gate") {
            checkAll(anyFacts) { f ->
                val out = f.copy(updateRequired = false, signedIn = false)
                startStep(out) shouldBe StartStep.SignIn
            }
        }

        test("only home needs every gate to pass") {
            checkAll(anyFacts) { f ->
                val passes = !f.updateRequired && f.signedIn && f.emailVerified && f.nameSaved && f.notice == null
                (startStep(f) == StartStep.Home) shouldBe passes
            }
        }

        test("an update stops even a signed-out start") {
            checkAll(anyFacts) { f -> startStep(f.copy(updateRequired = true)) shouldBe StartStep.Update }
        }
    })
