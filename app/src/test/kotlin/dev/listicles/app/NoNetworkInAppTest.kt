package dev.listicles.app

import dev.listicles.testing.NetworkAccessBlockedException
import io.kotest.assertions.throwables.shouldThrow
import org.junit.jupiter.api.Test
import java.net.ServerSocket
import java.net.Socket

/** The :app unit tests run in their own JVM, so they need the network block as well (R1-01). */
class NoNetworkInAppTest {
    @Test
    fun appUnitTestsCannotOpenServerSockets() {
        shouldThrow<NetworkAccessBlockedException> { ServerSocket(0) }
    }

    @Test
    fun appUnitTestsCannotOpenClientSockets() {
        shouldThrow<NetworkAccessBlockedException> { Socket("127.0.0.1", 9) }
    }
}
