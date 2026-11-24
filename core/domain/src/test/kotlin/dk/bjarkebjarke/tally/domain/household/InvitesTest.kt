package dk.bjarkebjarke.tally.domain.household

import io.kotest.core.spec.style.FunSpec
import io.kotest.matchers.shouldBe
import io.kotest.property.Arb
import io.kotest.property.arbitrary.Codepoint
import io.kotest.property.arbitrary.element
import io.kotest.property.arbitrary.int
import io.kotest.property.arbitrary.long
import io.kotest.property.arbitrary.map
import io.kotest.property.arbitrary.string
import io.kotest.property.checkAll
import java.security.SecureRandom

private const val ALNUM = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
private const val SECRET_ALPHABET = "$ALNUM-_"
private const val HOUSEHOLD = "Kq3ZtW9xLm2RbV7nPc4D" // a Firestore auto-id: 20 of [A-Za-z0-9] (P3)
private const val HOUR_MS = 3_600_000L

private fun strings(
    length: Int,
    alphabet: String,
) = Arb.string(length..length, Arb.element(alphabet.toList()).map { Codepoint(it.code) })

private val householdIds = strings(20, ALNUM)
private val secrets = strings(22, SECRET_ALPHABET)

// Outside [A-Za-z0-9_-]: what a link could carry instead, a path separator included.
private val foreign = Arb.element("/", ".", "=", "+", "%", " ", "\n", "é", " ", "😀")

/** M1-18 (PLAN 3.1 Create invite, P3, #243): invite codes and their expiry. */
class InvitesTest :
    FunSpec({
        test("a new code is the household id, '_' and a 22-character secret, and its own household's") {
            val random = SecureRandom()
            checkAll(householdIds) { householdId ->
                val code = Invites.newCode(householdId, random)
                code.take(21) shouldBe "${householdId}_"
                Regex("[A-Za-z0-9_-]{22}").matches(code.drop(21)) shouldBe true
                Invites.isWellFormed(code) shouldBe true
                Invites.householdId(code) shouldBe householdId
            }
        }

        test("the secrets come from the random source: they never repeat and use the whole alphabet") {
            val random = SecureRandom()
            val secrets = List(1_000) { Invites.newCode(HOUSEHOLD, random).drop(21) }
            secrets.toSet().size shouldBe 1_000
            secrets.joinToString("").toSet() shouldBe SECRET_ALPHABET.toSet()
        }

        test("only the rules' form is well formed, so a link's code always names an invite document") {
            checkAll(householdIds, secrets) { id, secret -> Invites.isWellFormed("${id}_$secret") shouldBe true }
            checkAll(householdIds, secrets, Arb.int(0..21), foreign) { id, secret, at, c ->
                Invites.isWellFormed("${id}_${secret.replaceRange(at, at + 1, c)}") shouldBe false
            }
            checkAll(householdIds, secrets, Arb.int(0..19), Arb.element("_", "-", "/", " ")) { id, secret, at, c ->
                Invites.isWellFormed("${id.replaceRange(at, at + 1, c)}_$secret") shouldBe false
            }
            val secret = "a".repeat(22)
            listOf(
                "",
                "${HOUSEHOLD}_${secret.drop(1)}",
                "${HOUSEHOLD}_${secret}a",
                "${HOUSEHOLD.drop(1)}_$secret",
                "${HOUSEHOLD}a_$secret",
                "$HOUSEHOLD$secret",
                "$HOUSEHOLD-$secret",
                "${HOUSEHOLD}_$secret\n",
            ).forEach { Invites.isWellFormed(it) shouldBe false }
        }

        test("an invite expires 7 days minus a 1-hour margin after it is made") {
            Invites.LIFETIME_MS shouldBe 7 * 24 * HOUR_MS - HOUR_MS
            checkAll(Arb.long(0L..4_102_444_800_000L)) { now ->
                Invites.expiresAt(now) shouldBe now + 7 * 24 * HOUR_MS - HOUR_MS
            }
        }
    })
