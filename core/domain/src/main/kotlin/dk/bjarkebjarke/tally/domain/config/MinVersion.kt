package dk.bjarkebjarke.tally.domain.config

import dk.bjarkebjarke.tally.domain.start.UpdateGate
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flow
import kotlinx.coroutines.withTimeoutOrNull

/**
 * START-01: the minimum version code in `config/app`, read from the server. A failure (offline, denied) is a failed
 * [Result], never a throw.
 */
interface MinVersionRemote {
    /** The minimum, or a success of `null` when the document or the field is missing. */
    suspend fun fetch(): Result<Long?>
}

/** The last minimum read, kept on the device for an offline start. */
interface MinVersionStore {
    suspend fun last(): Long?

    suspend fun save(minVersionCode: Long?)
}

/** An app below the minimum must update; no minimum means no update. Whole numbers only. */
fun updateRequired(
    installed: Long,
    minVersionCode: Long?,
): Boolean = minVersionCode != null && installed < minVersionCode

private const val FETCH_TIMEOUT_MS = 5_000L

/**
 * START-01 as the [UpdateGate]: reads the minimum before sign-in, remembers it, offline uses the last one read. With
 * nothing remembered it fails open (the app starts), so a first offline start is never blocked.
 */
class MinVersionGate(
    private val remote: MinVersionRemote,
    private val store: MinVersionStore,
    private val installedVersionCode: Long,
) : UpdateGate {
    override fun updateRequired(): Flow<Boolean> =
        flow {
            val fetched = withTimeoutOrNull(FETCH_TIMEOUT_MS) { remote.fetch() }
            val min =
                if (fetched != null && fetched.isSuccess) {
                    fetched.getOrNull().also { store.save(it) }
                } else {
                    store.last()
                }
            emit(updateRequired(installedVersionCode, min))
        }
}
