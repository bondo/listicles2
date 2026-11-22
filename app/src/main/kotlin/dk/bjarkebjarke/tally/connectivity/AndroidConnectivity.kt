package dk.bjarkebjarke.tally.connectivity

import android.content.Context
import android.net.ConnectivityManager
import android.net.NetworkCapabilities.NET_CAPABILITY_INTERNET
import android.net.NetworkCapabilities.NET_CAPABILITY_VALIDATED
import dagger.hilt.android.qualifiers.ApplicationContext
import dk.bjarkebjarke.tally.domain.connectivity.Connectivity
import javax.inject.Inject

/** Online when the active network reaches the internet and Android has validated it (not a captive portal). */
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
