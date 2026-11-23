package dk.bjarkebjarke.tally.data

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.google.android.gms.tasks.Tasks
import com.google.firebase.FirebaseApp
import com.google.firebase.auth.FirebaseAuth
import com.google.firebase.firestore.Source
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertThrows
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import java.util.UUID
import java.util.concurrent.TimeUnit

/**
 * M1-02: plumbing tests against the Auth and Firestore emulators (`ui` job, `demo-tally`): a user signs in, and a
 * document is written and read back. They fail when the emulators are not running.
 */
@RunWith(AndroidJUnit4::class)
class EmulatorSmokeTest {
    private lateinit var app: FirebaseApp
    private var rulesReplaced = false

    @Before
    fun setUp() {
        FirebaseEmulator.requireRunning()
        app = FirebaseEmulator.app(InstrumentationRegistry.getInstrumentation().targetContext)
    }

    @After
    fun tearDown() {
        if (::app.isInitialized) FirebaseAuth.getInstance(app).signOut()
        // The project's rules deny everything until M1-08, so the Firestore test loads allow-all ones; later tests need
        // the real ones.
        if (rulesReplaced) FirebaseEmulator.restoreProjectRules()
    }

    @Test
    fun signsInOnTheAuthEmulator() {
        val email = "smoke-${UUID.randomUUID()}@example.com"

        val user =
            Tasks
                .await(
                    FirebaseAuth.getInstance(app).createUserWithEmailAndPassword(email, "correct-horse-battery"),
                    TIMEOUT_S,
                    TimeUnit.SECONDS,
                ).user

        assertNotNull(user)
        assertEquals(email, FirebaseAuth.getInstance(app).currentUser?.email)
    }

    @Test
    fun writesAndReadsADocumentOnTheFirestoreEmulator() {
        rulesReplaced = true
        FirebaseEmulator.loadAllowAllRules()
        val document = FirebaseEmulator.firestore(app).collection("smoke").document(UUID.randomUUID().toString())

        Tasks.await(document.set(mapOf("greeting" to "hello")), TIMEOUT_S, TimeUnit.SECONDS)
        val snapshot = Tasks.await(document.get(Source.SERVER), TIMEOUT_S, TimeUnit.SECONDS)

        assertEquals("hello", snapshot.getString("greeting"))
    }

    @Test
    fun failsClearlyWhenNothingListens() {
        // A port nothing listens on: the negative case of requireRunning(), which every test above starts with.
        val error =
            assertThrows(AssertionError::class.java) {
                FirebaseEmulator.requireReachable(FirebaseEmulator.HOST, UNUSED_PORT, "Auth")
            }

        assertEquals(true, error.message?.contains("Auth emulator is not reachable"))
    }

    private companion object {
        const val TIMEOUT_S = 30L
        const val UNUSED_PORT = 9
    }
}
