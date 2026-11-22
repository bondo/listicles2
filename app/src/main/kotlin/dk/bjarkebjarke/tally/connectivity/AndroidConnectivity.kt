package dk.bjarkebjarke.tally.connectivity

import android.content.Context
import android.net.ConnectivityManager
import android.net.NetworkCapabilities.NET_CAPABILITY_INTERNET
import android.net.NetworkCapabilities.NET_CAPABILITY_VALIDATED
import dagger.hilt.android.qualifiers.ApplicationContext
import dk.bjarkebjarke.tally.domain.connectivity.Connectivity
import javax.inject.Inject

/**
 * Online when the active network reaches the internet and Android has validated it. Unvalidated networks (a captive
 * portal, the seconds before Wi-Fi validation ends) count as offline: a server call there would hang, not fail.
 */
class AndroidConnectivity
    @Inject
    constructor(
        @ApplicationContext context: Context,
    ) : Connectivity {
        private val manager = context.getSystemService(ConnectivityManager::class.java)

        override fun isOnline(): Boolean {
            val capabilities = manager.getNetworkCapabilities(manager.activeNetwork) ?: return false
            return capabilities.hasCapability(NET_CAPABILITY_INTERNET) &&
                capabilities.hasCapability(NET_CAPABILITY_VALIDATED)
        }
    }
