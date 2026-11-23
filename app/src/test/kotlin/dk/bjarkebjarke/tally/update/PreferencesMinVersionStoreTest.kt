package dk.bjarkebjarke.tally.update

import android.content.Context
import androidx.test.core.app.ApplicationProvider
import io.kotest.matchers.shouldBe
import kotlinx.coroutines.test.runTest
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

/** M1-27: the last minimum read survives a restart, so an offline start can still use it. */
@RunWith(RobolectricTestRunner::class)
class PreferencesMinVersionStoreTest {
    private val context: Context = ApplicationProvider.getApplicationContext()

    @Test
    fun nothingRememberedAtFirst() = runTest { PreferencesMinVersionStore(context).last() shouldBe null }

    @Test
    fun aSavedMinimumIsReadBackByANewStore() =
        runTest {
            PreferencesMinVersionStore(context).save(42L)
            PreferencesMinVersionStore(context).last() shouldBe 42L
        }

    @Test
    fun savingNoMinimumForgetsTheOldOne() =
        runTest {
            val store = PreferencesMinVersionStore(context)
            store.save(42L)
            store.save(null)
            store.last() shouldBe null
        }

    @Test
    fun theZeroMinimumIsRemembered() =
        runTest {
            val store = PreferencesMinVersionStore(context)
            store.save(0L)
            store.last() shouldBe 0L
        }
}
