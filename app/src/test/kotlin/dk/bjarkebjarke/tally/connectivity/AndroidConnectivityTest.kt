package dk.bjarkebjarke.tally.connectivity

import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import android.net.NetworkCapabilities.NET_CAPABILITY_INTERNET
import android.net.NetworkCapabilities.NET_CAPABILITY_VALIDATED
import io.kotest.matchers.shouldBe
import io.kotest.matchers.shouldNotBe
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.Shadows.shadowOf
import org.robolectric.shadows.ShadowNetworkCapabilities

/** M1-30 (SYNC-03): online means the active network reaches the internet and Android has validated it. */
@RunWith(RobolectricTestRunner::class)
class AndroidConnectivityTest {
    private val app = RuntimeEnvironment.getApplication()
    private val manager = app.getSystemService(ConnectivityManager::class.java)
    private val connectivity = AndroidConnectivity(app)

    private fun activeNetworkWith(vararg capabilities: Int) {
        val network = manager.activeNetwork
        network shouldNotBe null
        val networkCapabilities: NetworkCapabilities = ShadowNetworkCapabilities.newInstance()
        capabilities.forEach { shadowOf(networkCapabilities).addCapability(it) }
        shadowOf(manager).setNetworkCapabilities(network, networkCapabilities)
    }

    @Test
    fun onlineWhenTheActiveNetworkReachesTheInternetAndIsValidated() {
        activeNetworkWith(NET_CAPABILITY_INTERNET, NET_CAPABILITY_VALIDATED)
        connectivity.isOnline() shouldBe true
    }

    @Test
    fun offlineWhenTheNetworkIsNotValidatedOrHasNoInternet() {
        activeNetworkWith(NET_CAPABILITY_INTERNET)
        connectivity.isOnline() shouldBe false
        activeNetworkWith(NET_CAPABILITY_VALIDATED)
        connectivity.isOnline() shouldBe false
    }

    @Test
    fun offlineWithoutAnActiveNetwork() {
        shadowOf(manager).setDefaultNetworkActive(false)
        shadowOf(manager).setActiveNetworkInfo(null)
        connectivity.isOnline() shouldBe false
    }
}
