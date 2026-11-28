package dk.bjarkebjarke.tally.data.household

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.google.firebase.auth.FirebaseAuth
import com.google.firebase.auth.GoogleAuthProvider
import com.google.firebase.firestore.Source
import dk.bjarkebjarke.tally.data.FirebaseEmulator
import dk.bjarkebjarke.tally.data.session.FirestoreSession
import dk.bjarkebjarke.tally.domain.household.InviteLookup
import dk.bjarkebjarke.tally.domain.household.Invites
import dk.bjarkebjarke.tally.domain.household.Membership
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.tasks.await
import kotlinx.coroutines.withTimeout
import org.json.JSONObject
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import java.security.SecureRandom
import java.util.UUID

/**
 * M1-18 and M1-100 against the Auth and Firestore emulators (`ui` job) with the project's rules: create a household,
 * invite to it and join it (HH-01 to HH-03) with up to four users, each a Google-style account (a verified email) whose
 * `users/{uid}` holds no household and, unless a test says otherwise, a name (AUTH-12). A user switch starts a new
 * Firestore instance, as the app's sign-out does (M1-14), so no write goes out under the previous user.
 */
@RunWith(AndroidJUnit4::class)
class HouseholdsEmulatorTest {
    private lateinit var auth: FirebaseAuth
    private lateinit var session: FirestoreSession
    private val tokens = mutableMapOf<String, String>()
    private var now = System.currentTimeMillis()
    private val households by lazy { FirestoreHouseholds(session, auth) { now } }

    @Before
    fun setUp() {
        FirebaseEmulator.requireRunning()
        FirebaseEmulator.restoreProjectRules()
        val app = FirebaseEmulator.app(InstrumentationRegistry.getInstrumentation().targetContext)
        auth = FirebaseAuth.getInstance(app)
        session = FirestoreSession { FirebaseEmulator.firestore(app) }
    }

    @After
    fun tearDown() {
        if (::session.isInitialized) emulatorTest { session.clear() }
        if (::auth.isInitialized) auth.signOut()
    }

    @Test
    fun theCreatorIsTheOwnerAndOnlyMemberAndInvitesToTheHousehold() =
        emulatorTest {
            val ann = signIn("Ann")
            assertEquals(Membership.Failed, households.create("  ")) // the rules refuse a blank name
            val home = member(households.create(" Home "))
            val household = fields("households/$home", "name", "createdBy", "ownerUid", "deleted")
            assertEquals(listOf("Home", ann, ann, false), household)
            assertEquals(mapOf(ann to listOf("owner", "Ann")), members(home))
            assertEquals(listOf(home), fields("users/$ann", "householdId"))

            val code = checkNotNull(households.createInvite(home))
            assertTrue(code, code.startsWith("${home}_"))
            assertEquals(
                listOf(home, "Home", ann),
                fields("invites/$code", "householdId", "householdName", "createdBy"),
            )
            assertEquals(now + Invites.LIFETIME_MS, read("invites/$code").getDate("expiresAt")?.time)

            val bob = signIn("Bob")
            assertNull(households.createInvite(home)) // not a member: the household read is refused
            assertEquals(InviteLookup.Open("Home"), households.invite(code))
            assertEquals(Membership.Member(home), households.join(code))
            assertEquals(mapOf(ann to listOf("owner", "Ann"), bob to listOf("member", "Bob")), members(home))
            assertEquals(listOf(code), fields("households/$home/members/$bob", "viaInvite"))
            assertEquals(listOf(home), fields("users/$bob", "householdId"))

            val cat = signIn("Cat")
            assertEquals(InviteLookup.Unusable, households.invite(code)) // used up: the rules deny the read
            assertEquals(Membership.InviteUnusable, households.join(code))
            assertEquals(listOf(null), fields("users/$cat", "householdId"))
        }

    @Test
    fun anInviteIsUnusableExpiredRevokedNeverMadeOrUnderATombstone() =
        emulatorTest {
            signIn("Ann")
            val home = member(households.create("Home"))
            val (revoked, open) = List(2) { checkNotNull(households.createInvite(home)) }
            now -= 8 * DAY_MS
            val expired = checkNotNull(households.createInvite(home)) // the rules take any expiry up to 7 days
            now += 8 * DAY_MS
            session
                .firestore()
                .document("invites/$revoked")
                .delete()
                .await() // its creator revokes it (HH-02)
            val neverMade = Invites.newCode(home, SecureRandom())

            val bob = signIn("Bob")
            for (code in listOf(expired, revoked, neverMade, "not-an-invite", "invites/$open", "$open/x")) {
                assertEquals(code, InviteLookup.Unusable, households.invite(code))
                assertEquals(code, Membership.InviteUnusable, households.join(code))
            }
            assertEquals(listOf(null), fields("users/$bob", "householdId"))
            assertEquals(InviteLookup.Open("Home"), households.invite(open)) // no refused join used it up

            signIn("Ann")
            session
                .firestore()
                .document("households/$home")
                .update("deleted", true, "name", "")
                .await()
            signIn("Bob")
            assertEquals(InviteLookup.Unusable, households.invite(open))
            assertEquals(Membership.InviteUnusable, households.join(open))
            assertEquals(listOf(null), fields("users/$bob", "householdId"))
        }

    @Test
    fun aCallWhileASignOutTerminatesTheInstanceFailsAndThrowsNothing() =
        emulatorTest {
            signIn("Ann")
            val home = member(households.create("Home"))
            val code = checkNotNull(households.createInvite(home))
            session.firestore().terminate().await() // the first step of a sign-out's clear(), not finished yet

            assertEquals(Membership.Failed, households.create("Second"))
            assertNull(households.createInvite(home))
            assertEquals(InviteLookup.Failed, households.invite(code))
            assertEquals(Membership.Failed, households.join(code))
        }

    @Test
    fun noSecondHouseholdAndNoneWithoutASavedNameOrSignedOut() =
        emulatorTest {
            val ann = signIn("Ann")
            val home = member(households.create("Home"))
            assertEquals(Membership.AlreadyInHousehold, households.create("Second"))
            assertEquals(listOf(home), fields("users/$ann", "householdId"))
            val code = checkNotNull(households.createInvite(home))

            val bob = signIn("Bob")
            val away = member(households.create("Away"))
            assertEquals(Membership.AlreadyInHousehold, households.join(code))
            assertEquals(listOf(away), fields("users/$bob", "householdId"))

            val dan = signIn("Dan", nameSaved = false)
            assertEquals(Membership.Failed, households.create("Home"))
            assertEquals(Membership.Failed, households.join(code))
            assertEquals(listOf(null), fields("users/$dan", "householdId"))
            assertEquals(InviteLookup.Open("Home"), households.invite(code)) // nothing used it up

            auth.signOut()
            assertEquals(Membership.Failed, households.create("Home"))
            assertNull(households.createInvite(home))
            assertEquals(InviteLookup.Failed, households.invite(code))
            assertEquals(Membership.Failed, households.join(code))
        }

    /** Signs [name] in; the first time as a new account whose `users/{uid}` holds no household. */
    private suspend fun signIn(
        name: String,
        nameSaved: Boolean = true,
    ): String {
        check(session.clear())
        val first = name !in tokens
        val token = tokens.getOrPut(name) { googleIdToken("$name-${UUID.randomUUID()}@example.com") }
        auth.signInWithCredential(GoogleAuthProvider.getCredential(token, null)).await()
        val uid = checkNotNull(auth.currentUser).uid
        if (first) {
            val user = mapOf("householdId" to null) + if (nameSaved) mapOf("name" to name) else emptyMap()
            session
                .firestore()
                .document("users/$uid")
                .set(user)
                .await()
        }
        return uid
    }

    private fun member(result: Membership) = checkNotNull((result as? Membership.Member)?.householdId) { "$result" }

    private suspend fun read(path: String) =
        session
            .firestore()
            .document(path)
            .get(Source.SERVER)
            .await()

    private suspend fun fields(
        path: String,
        vararg keys: String,
    ) = read(path).let { doc -> keys.map { doc[it] } }

    /** Each member's role and name, read as the signed-in member (PLAN 3.1 Reads). */
    private suspend fun members(householdId: String) =
        session.firestore().collection("households/$householdId/members").get(Source.SERVER).await().associate {
            it.id to listOf(it["role"], it["displayName"])
        }

    /** The Auth emulator takes strict JSON claims as a fake Google ID token; `sub` is the Google account id. */
    private fun googleIdToken(email: String) =
        JSONObject()
            .put("sub", "google-$email")
            .put("email", email)
            .put("email_verified", true)
            .toString()

    /** A hung emulator call fails its test instead of the whole `ui` job. */
    private fun emulatorTest(block: suspend CoroutineScope.() -> Unit) {
        runBlocking { withTimeout(TEST_TIMEOUT_MS, block) }
    }

    private companion object {
        const val TEST_TIMEOUT_MS = 60_000L
        const val DAY_MS = 86_400_000L
    }
}
