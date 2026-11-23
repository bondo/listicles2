package dk.bjarkebjarke.tally.update

import android.content.Context
import androidx.test.core.app.ApplicationProvider
import io.kotest.matchers.shouldBe
import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.test.runTest
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import kotlin.coroutines.CoroutineContext

/** M1-27: the last minimum read survives a restart, so an offline start can still use it. */
@RunWith(RobolectricTestRunner::class)
class PreferencesMinVersionStoreTest {
    private val context: Context = ApplicationProvider.getApplicationContext()

    @Test
    fun nothingRememberedAtFirst() =
        runTest {
            PreferencesMinVersionStore(context, Dispatchers.Unconfined).last() shouldBe
                null
        }

    @Test
    fun aSavedMinimumIsReadBackByANewStore() =
        runTest {
            PreferencesMinVersionStore(context, Dispatchers.Unconfined).save(42L)
            PreferencesMinVersionStore(context, Dispatchers.Unconfined).last() shouldBe 42L
        }

    @Test
    fun savingNoMinimumForgetsTheOldOne() =
        runTest {
            val store = PreferencesMinVersionStore(context, Dispatchers.Unconfined)
            store.save(42L)
            store.save(null)
            store.last() shouldBe null
        }

    @Test
    fun theZeroMinimumIsRemembered() =
        runTest {
            val store = PreferencesMinVersionStore(context, Dispatchers.Unconfined)
            store.save(0L)
            store.last() shouldBe 0L
        }

    /** R1-02: the file is read and written on the injected IO dispatcher, not on the caller (Main). */
    @Test
    fun readsAndWritesRunOnTheInjectedDispatcher() =
        runTest {
            var dispatched = 0
            val io =
                object : CoroutineDispatcher() {
                    override fun dispatch(
                        context: CoroutineContext,
                        block: Runnable,
                    ) {
                        dispatched++
                        block.run()
                    }
                }
            val store = PreferencesMinVersionStore(context, io)
            store.save(7L)
            dispatched shouldBe 1
            store.last() shouldBe 7L
            dispatched shouldBe 2
        }
}
