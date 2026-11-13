package dev.listicles.testing

import java.net.DatagramSocket
import java.net.ServerSocket
import java.net.Socket
import java.util.concurrent.atomic.AtomicBoolean

class NetworkAccessBlockedException(
    message: String,
) : RuntimeException(message)

/**
 * Makes a test open no network connection (P13, PLAN 5.4): any attempt fails with [NetworkAccessBlockedException].
 *
 * It is installed once per test JVM by [NoNetworkSessionListener], a JUnit Platform launcher-session listener that
 * runs before any engine, so Jupiter tests, Kotest specs and any other engine are all covered, in `:core:domain`,
 * `:app` and every module that has `testImplementation(project(":core:testing"))`.
 * The JDK allows one socket factory per JVM and no way back, so the block holds for the rest of the JVM.
 *
 * Covered: `java.net.Socket` and `ServerSocket` (so `HttpURLConnection` too), `DatagramSocket` and
 * `MulticastSocket`, NIO `SocketChannel`, `ServerSocketChannel` and `DatagramChannel`
 * ([BlockingSelectorProvider], needs the JVM arguments set in the root `build.gradle.kts`), and DNS lookups of
 * anything but loopback names ([BlockingInetAddressResolverProvider]).
 *
 * Not covered, by design of the JDK or because it is not JVM code: processes a test starts (`ProcessBuilder`),
 * native libraries, and connections opened before the block was installed (the Gradle worker's own).
 * Loopback names and address literals resolve, because they are not network traffic.
 */
object NoNetwork {
    private val done = AtomicBoolean(false)

    val installed: Boolean get() = done.get()

    @Synchronized
    fun install() {
        if (done.get()) return
        @Suppress("DEPRECATION") // justified: the only JDK hook for every java.net socket
        Socket.setSocketImplFactory { blocked("socket opened") }
        @Suppress("DEPRECATION") // justified: the only JDK hook for server sockets
        ServerSocket.setSocketFactory { blocked("server socket opened") }
        @Suppress("DEPRECATION") // justified: the only JDK hook for UDP and multicast sockets
        DatagramSocket.setDatagramSocketImplFactory { blocked("UDP socket opened") }
        done.set(true)
    }

    internal fun blocked(what: String): Nothing = throw NetworkAccessBlockedException("network blocked in tests: $what")
}
