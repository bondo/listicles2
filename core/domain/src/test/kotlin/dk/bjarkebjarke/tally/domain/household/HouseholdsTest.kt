package dk.bjarkebjarke.tally.domain.household

import io.kotest.core.spec.style.FunSpec
import io.kotest.matchers.shouldBe
import io.kotest.property.Arb
import io.kotest.property.arbitrary.long
import io.kotest.property.arbitrary.orNull
import io.kotest.property.arbitrary.string
import io.kotest.property.checkAll

/**
 * M1-18, M1-100 (PLAN 3, P2, P9): what the caller's `users/{uid}` decides before a create or join batch, and what the
 * join screen shows for an invite the rules let the caller read.
 */
class HouseholdsTest :
    FunSpec({
        test("a set householdId stops the batch whatever the name: one household per user") {
            checkAll(Arb.string(), Arb.string().orNull()) { householdId, name ->
                membership(householdId, name) { error("no batch") } shouldBe Membership.AlreadyInHousehold
            }
        }

        test("in no household, a missing name stops it and a saved one is the new member doc's displayName") {
            membership(null, null) { error("no batch") } shouldBe Membership.Failed
            checkAll(Arb.string()) { name ->
                membership(null, name) { Membership.Member(householdId = it) } shouldBe Membership.Member(name)
            }
        }

        test("an invite is open with its stored household name only while it expires after now (P2)") {
            checkAll(Arb.string(), Arb.long(0L..YEAR_2100_MS), Arb.long(1L..YEAR_2100_MS)) { name, now, by ->
                inviteLookup(name, now + by, now) shouldBe InviteLookup.Open(name)
                inviteLookup(name, now, now) shouldBe InviteLookup.Unusable
                inviteLookup(name, now - by, now) shouldBe InviteLookup.Unusable
            }
        }

        test("an invite without its household name or expiry is unusable, whatever the time") {
            checkAll(Arb.string(), Arb.long(0L..YEAR_2100_MS), Arb.long(0L..YEAR_2100_MS)) { name, expiresAt, now ->
                inviteLookup(null, expiresAt, now) shouldBe InviteLookup.Unusable
                inviteLookup(name, null, now) shouldBe InviteLookup.Unusable
            }
        }
    })

private const val YEAR_2100_MS = 4_102_444_800_000L
