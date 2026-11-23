package dk.bjarkebjarke.tally.update

import android.content.Context
import androidx.core.content.edit
import dk.bjarkebjarke.tally.domain.config.MinVersionStore
import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.withContext

private const val FILE = "min_version"
private const val KEY = "min_version_code"

/**
 * The last minimum read, in app-private preferences, so an offline start can use it (START-01). Reads and writes run
 * on [io]: the gate is collected on Main.
 */
class PreferencesMinVersionStore(
    context: Context,
    private val io: CoroutineDispatcher,
) : MinVersionStore {
    private val prefs = context.getSharedPreferences(FILE, Context.MODE_PRIVATE)

    override suspend fun last(): Long? = withContext(io) { if (prefs.contains(KEY)) prefs.getLong(KEY, 0L) else null }

    override suspend fun save(minVersionCode: Long?) =
        withContext(io) {
            prefs.edit {
                if (minVersionCode == null) remove(KEY) else putLong(KEY, minVersionCode)
            }
        }
}
