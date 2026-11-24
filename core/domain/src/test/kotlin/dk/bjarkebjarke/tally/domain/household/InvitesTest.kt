package dk.bjarkebjarke.tally.domain.household

import io.kotest.core.spec.style.FunSpec
import io.kotest.matchers.shouldBe
import io.kotest.matchers.string.shouldMatch
import io.kotest.property.Arb
import io.kotest.property.arbitrary.Codepoint
import io.kotest.property.arbitrary.element
import io.kotest.property.arbitrary.long
import io.kotest.property.arbitrary.map
import io.kotest.property.arbitrary.string
import io.kotest.property.checkAll
import java.security.SecureRandom

private const val ALNUM = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
private const val HOUSEHOLD = "Kq3ZtW9xLm2RbV7nPc4D" // a Firestore auto-id: 20 of [A-Za-z0-9] (P3)
private const val HOUR_MS = 3_600_000L

/** M1-18 (PLAN 3.1 Create invite, P3, #243): invite codes and their expiry. */
class InvitesTest :
    FunSpec({
        test("a new code is its household's id, '_' and 22 characters of [A-Za-z0-9_-]: the rules' form (P3)") {
            val random = SecureRandom()
            val householdIds = Arb.string(20..20, Arb.element(ALNUM.toList()).map { Codepoint(it.code) })
            checkAll(householdIds) { householdId ->
                Invites.newCode(householdId, random) shouldMatch Regex("${householdId}_[A-Za-z0-9_-]{22}")
            }
        }

        test("the secrets come from the random source: they never repeat and use the whole alphabet") {
            val random = SecureRandom()
            val secrets = List(1_000) { Invites.newCode(HOUSEHOLD, random).drop(21) }
            secrets.toSet().size shouldBe 1_000
            secrets.joinToString("").toSet() shouldBe "$ALNUM-_".toSet()
        }

        test("an invite expires 7 days minus a 1-hour margin after it is made") {
            Invites.LIFETIME_MS shouldBe 7 * 24 * HOUR_MS - HOUR_MS
            checkAll(Arb.long(0L..4_102_444_800_000L)) { now ->
                Invites.expiresAt(now) shouldBe now + Invites.LIFETIME_MS
            }
        }
    })
