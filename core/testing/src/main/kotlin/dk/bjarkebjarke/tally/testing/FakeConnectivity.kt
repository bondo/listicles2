package dk.bjarkebjarke.tally.testing

import dk.bjarkebjarke.tally.domain.connectivity.Connectivity

/** A [Connectivity] that answers what the test set last (SYNC-03); online unless told otherwise. */
class FakeConnectivity(
    var online: Boolean = true,
) : Connectivity {
    override fun isOnline(): Boolean = online
}
