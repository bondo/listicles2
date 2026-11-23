package dk.bjarkebjarke.tally.update

import android.content.Context
import dk.bjarkebjarke.tally.domain.config.MinVersionStore

/** The last minimum read, in app-private preferences (START-01 offline start). Stub until the test is green. */
class PreferencesMinVersionStore(
    private val context: Context,
) : MinVersionStore {
    override suspend fun last(): Long? = context.packageName.let { null }

    override suspend fun save(minVersionCode: Long?) = Unit
}
