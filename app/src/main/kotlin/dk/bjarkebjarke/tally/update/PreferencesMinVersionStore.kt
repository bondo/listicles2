package dk.bjarkebjarke.tally.update

import android.content.Context
import androidx.core.content.edit
import dk.bjarkebjarke.tally.domain.config.MinVersionStore

private const val FILE = "min_version"
private const val KEY = "min_version_code"

/** The last minimum read, in app-private preferences, so an offline start can use it (START-01). */
class PreferencesMinVersionStore(
    context: Context,
) : MinVersionStore {
    private val prefs = context.getSharedPreferences(FILE, Context.MODE_PRIVATE)

    override suspend fun last(): Long? = if (prefs.contains(KEY)) prefs.getLong(KEY, 0L) else null

    override suspend fun save(minVersionCode: Long?) {
        prefs.edit {
            if (minVersionCode == null) remove(KEY) else putLong(KEY, minVersionCode)
        }
    }
}
