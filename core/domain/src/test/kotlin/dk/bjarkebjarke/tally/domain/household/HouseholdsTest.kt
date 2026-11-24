package dk.bjarkebjarke.tally.domain.household

import io.kotest.core.spec.style.FunSpec
import io.kotest.matchers.shouldBe
import io.kotest.property.Arb
import io.kotest.property.arbitrary.orNull
import io.kotest.property.arbitrary.string
import io.kotest.property.checkAll

/** M1-18 (PLAN 3, P9): what the caller's `users/{uid}` decides before a create or join batch. */
class HouseholdsTest :
    FunSpec({
        test("a set householdId stops the batch whatever the name: one household per user") {
            checkAll(Arb.string(), Arb.string().orNull()) { householdId, name ->
                membershipBlocker(householdId, name) shouldBe Membership.AlreadyInHousehold
            }
        }

        test("in no household, a missing name stops it (the member doc copies it) and any saved name lets it go") {
            membershipBlocker(null, null) shouldBe Membership.Failed
            checkAll(Arb.string()) { name -> membershipBlocker(null, name) shouldBe null }
        }
    })
