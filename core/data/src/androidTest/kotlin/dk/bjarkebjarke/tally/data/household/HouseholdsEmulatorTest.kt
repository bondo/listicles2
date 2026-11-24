package dk.bjarkebjarke.tally.data.household

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.google.firebase.auth.FirebaseAuth
import com.google.firebase.auth.GoogleAuthProvider
import com.google.firebase.firestore.Source
import dk.bjarkebjarke.tally.data.FirebaseEmulator
import dk.bjarkebjarke.tally.data.session.FirestoreSession
import dk.bjarkebjarke.tally.domain.household.Invites
import dk.bjarkebjarke.tally.domain.household.Membership
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.tasks.await
import kotlinx.coroutines.withTimeout
import org.json.JSONObject
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import java.util.UUID

/**
 * M1-18 against the Auth and Firestore emulators (`ui` job) with the project's rules: create, invite and join (HH-01
 * to HH-03) with up to five users. Each signs in with a Google-style account (a verified email) whose `users/{uid}`
 * holds no household and, unless a test says otherwise, a name (AUTH-12). A user switch starts a new Firestore
 * instance, as the app's sign-out does (M1-14), so no write goes out under the previous user.
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
    fun theCreatorOwnsTheHouseholdAndItsInviteLetsOneOtherUserJoin() =
        emulatorTest {
            val ann = signIn("Ann")
            assertEquals(Membership.Failed, households.create("  ")) // the rules refuse a blank name
            val home = member(households.create(" Home "))

            val household = read("households/$home")
            assertEquals(
                listOf("Home", ann, ann, false),
                listOf(household["name"], household["createdBy"], household["ownerUid"], household["deleted"]),
            )
            assertEquals(mapOf(ann to listOf("owner", "Ann", null)), members(home))
            assertEquals(home, read("users/$ann")["householdId"])

            val code = checkNotNull(households.createInvite(home))
            assertEquals(home, Invites.householdId(code))
            val invite = read("invites/$code")
            assertEquals(
                listOf(home, "Home", ann, now + Invites.LIFETIME_MS),
                listOf(
                    invite["householdId"],
                    invite["householdName"],
                    invite["createdBy"],
                    invite.getDate("expiresAt")?.time,
                ),
            )

            val bob = signIn("Bob")
            assertEquals(Membership.Member(home), households.join(code))
            assertEquals(
                mapOf(ann to listOf("owner", "Ann", null), bob to listOf("member", "Bob", code)),
                members(home),
            )
            assertEquals(home, read("users/$bob")["householdId"])

            val cat = signIn("Cat")
            assertEquals(Membership.InviteUnusable, households.join(code)) // used up
            assertNull(read("users/$cat")["householdId"])
        }

    @Test
    fun noJoinWithAnExpiredInviteNorForAUserInAHouseholdOrWithoutAName() =
        emulatorTest {
            signIn("Ann")
            val home = member(households.create("Home"))
            now -= 8 * DAY_MS
            val expired = checkNotNull(households.createInvite(home)) // the rules take any expiry up to 7 days
            now += 8 * DAY_MS
            val code = checkNotNull(households.createInvite(home))

            val bob = signIn("Bob")
            assertEquals(Membership.InviteUnusable, households.join(expired))
            assertEquals(Membership.InviteUnusable, households.join("not-an-invite"))
            val away = member(households.create("Away"))
            assertEquals(Membership.AlreadyInHousehold, households.create("Second"))
            assertEquals(Membership.AlreadyInHousehold, households.join(code))
            assertEquals(away, read("users/$bob")["householdId"])
            assertFalse(read("households/$home/members/$bob").exists())

            signIn("Dan", nameSaved = false)
            assertEquals(Membership.Failed, households.create("Home"))
            assertEquals(Membership.Failed, households.join(code))

            signIn("Eve")
            assertEquals(Membership.Member(home), households.join(code)) // no refused attempt used it up

            auth.signOut()
            assertEquals(Membership.Failed, households.create("Home"))
            assertNull(households.createInvite(home))
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

    /** Each member's role, name and invite, read as the signed-in member (PLAN 3.1 Reads). */
    private suspend fun members(householdId: String) =
        session
            .firestore()
            .collection("households/$householdId/members")
            .get(Source.SERVER)
            .await()
            .associate { it.id to listOf(it["role"], it["displayName"], it["viaInvite"]) }

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
