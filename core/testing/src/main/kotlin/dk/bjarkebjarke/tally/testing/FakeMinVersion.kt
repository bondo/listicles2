package dk.bjarkebjarke.tally.testing

import dk.bjarkebjarke.tally.domain.config.MinVersionRemote
import dk.bjarkebjarke.tally.domain.config.MinVersionStore
import kotlinx.coroutines.awaitCancellation
import java.io.IOException

/** A [MinVersionRemote] the test sets up: it answers with [minVersionCode], fails (offline) or never answers. */
class FakeMinVersionRemote private constructor(
    private val answer: suspend () -> Result<Long?>,
) : MinVersionRemote {
    constructor(minVersionCode: Long?) : this({ Result.success(minVersionCode) })

    override suspend fun fetch(): Result<Long?> = answer()

    companion object {
        fun offline() = FakeMinVersionRemote { Result.failure(IOException("offline")) }

        fun hanging() = FakeMinVersionRemote { awaitCancellation() }
    }
}

/** A [MinVersionStore] in memory; empty (no cache) unless given a first value. */
class FakeMinVersionStore(
    var value: Long? = null,
) : MinVersionStore {
    override suspend fun last(): Long? = value

    override suspend fun save(minVersionCode: Long?) {
        value = minVersionCode
    }
}
