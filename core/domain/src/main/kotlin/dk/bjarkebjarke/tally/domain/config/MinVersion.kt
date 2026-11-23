package dk.bjarkebjarke.tally.domain.config

import dk.bjarkebjarke.tally.domain.start.UpdateGate
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flow

/** START-01: the minimum version code in `config/app`, read from the server. Throws when it cannot be reached. */
interface MinVersionRemote {
    suspend fun fetch(): Long?
}

/** The last minimum read, kept on the device for an offline start. */
interface MinVersionStore {
    suspend fun last(): Long?

    suspend fun save(minVersionCode: Long?)
}

fun updateRequired(
    installed: Long,
    minVersionCode: Long?,
): Boolean = minVersionCode != null && installed > minVersionCode

class MinVersionGate(
    private val remote: MinVersionRemote,
    private val store: MinVersionStore,
    private val installedVersionCode: Long,
) : UpdateGate {
    override fun updateRequired(): Flow<Boolean> =
        flow {
            remote.fetch()
            emit(updateRequired(installedVersionCode, store.last()))
        }
}
