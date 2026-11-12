package dev.listicles.architecture

import org.junit.jupiter.api.extension.BeforeAllCallback
import org.junit.jupiter.api.extension.ExtensionContext
import java.io.IOException
import java.net.ServerSocket
import java.net.Socket
import java.util.concurrent.atomic.AtomicBoolean

class NetworkAccessBlockedException(
    message: String,
) : RuntimeException(message)

/**
 * Fails any test that opens a socket (P13, PLAN 5.4), so unit tests cannot silently depend on the internet.
 * Registered globally by `META-INF/services` plus `junit.jupiter.extensions.autodetection.enabled`.
 * The JDK allows one socket factory per JVM and no way back, so the block holds for the rest of the test JVM.
 * Covers `java.net.Socket` and `ServerSocket` (so HttpURLConnection too); NIO channels are not covered.
 */
class NoNetworkExtension : BeforeAllCallback {
    override fun beforeAll(context: ExtensionContext) = install()

    companion object {
        private val done = AtomicBoolean(false)

        val installed: Boolean get() = done.get()

        @Synchronized
        fun install() {
            if (done.get()) return
            @Suppress("DEPRECATION") // justified: only JDK hook for every java.net socket
            Socket.setSocketImplFactory {
                throw NetworkAccessBlockedException("network access is blocked in unit tests (socket opened)")
            }
            @Suppress("DEPRECATION") // justified: only JDK hook for server sockets
            ServerSocket.setSocketFactory {
                throw NetworkAccessBlockedException("network access is blocked in unit tests (server socket opened)")
            }
            done.set(true)
        }
    }
}
