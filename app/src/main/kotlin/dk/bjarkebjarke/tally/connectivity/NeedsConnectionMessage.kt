package dk.bjarkebjarke.tally.connectivity

import androidx.compose.runtime.Composable
import androidx.compose.ui.res.stringResource
import dk.bjarkebjarke.tally.R
import dk.bjarkebjarke.tally.domain.connectivity.ConnectionResult

/** SYNC-03: the text a screen shows for [ConnectionResult.NeedsConnection]. */
@Composable
fun needsConnectionMessage(): String = stringResource(R.string.needs_connection)
