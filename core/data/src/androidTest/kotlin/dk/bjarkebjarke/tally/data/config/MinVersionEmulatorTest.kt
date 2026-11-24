package dk.bjarkebjarke.tally.data.config

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.google.firebase.FirebaseApp
import com.google.firebase.auth.FirebaseAuth
import dk.bjarkebjarke.tally.data.FirebaseEmulator
import dk.bjarkebjarke.tally.data.session.FirestoreSession
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.tasks.await
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith

/**
 * M1-82 against the Firestore emulator (`ui` job) with the project's own rules: `config/app` is readable signed out
 * (START-01). Documents are written with the allow-all rules, then read back under the project's rules.
 */
@RunWith(AndroidJUnit4::class)
class MinVersionEmulatorTest {
    private lateinit var app: FirebaseApp
    private lateinit var remote: FirestoreMinVersionRemote

    @Before
    fun setUp() {
        FirebaseEmulator.requireRunning()
        app = FirebaseEmulator.app(InstrumentationRegistry.getInstrumentation().targetContext)
        FirebaseAuth.getInstance(app).signOut()
        remote = FirestoreMinVersionRemote(FirestoreSession { FirebaseEmulator.firestore(app) })
        FirebaseEmulator.restoreProjectRules()
        setConfig(null)
    }

    @After
    fun tearDown() {
        if (::app.isInitialized) setConfig(null)
        FirebaseEmulator.restoreProjectRules()
    }

    /** Writes (or, with null, deletes) `config/app` under allow-all rules, then puts the project's rules back. */
    private fun setConfig(fields: Map<String, Any>?) =
        runBlocking {
            FirebaseEmulator.loadAllowAllRules()
            val doc = FirebaseEmulator.firestore(app).document("config/app")
            if (fields == null) doc.delete().await() else doc.set(fields).await()
            FirebaseEmulator.restoreProjectRules()
        }

    private fun fetch() = runBlocking { remote.fetch() }

    @Test
    fun theMinimumIsReadSignedOutUnderTheProjectRules() {
        setConfig(mapOf("minVersionCode" to 42L))

        assertEquals(Result.success(42L), fetch())
    }

    @Test
    fun aMissingDocumentIsSuccessOfNull() {
        val result = fetch()

        assertTrue(result.isSuccess)
        assertNull(result.getOrNull())
    }

    @Test
    fun aMissingFieldIsSuccessOfNull() {
        setConfig(mapOf("schemaVersion" to 1L))

        val result = fetch()

        assertTrue(result.isSuccess)
        assertNull(result.getOrNull())
    }

    @Test
    fun aFieldThatIsNotANumberIsAFailureNotAThrow() {
        setConfig(mapOf("minVersionCode" to "high"))

        assertTrue(fetch().isFailure)
    }

    @Test
    fun aTerminatedInstanceIsAFailureNotAThrow() {
        runBlocking { FirebaseEmulator.firestore(app).terminate().await() }

        assertTrue(fetch().isFailure)
    }
}
