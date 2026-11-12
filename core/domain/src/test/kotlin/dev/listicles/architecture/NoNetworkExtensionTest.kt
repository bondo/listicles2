package dev.listicles.architecture

import io.kotest.assertions.throwables.shouldThrow
import io.kotest.matchers.string.shouldContain
import org.junit.jupiter.api.Test
import java.net.ServerSocket
import java.net.Socket

class NoNetworkExtensionTest {
    @Test
    fun opensNoClientSocket() {
        // The server socket is created before the block is verified; a real local port, so a leak would connect.
        val e = shouldThrow<NetworkAccessBlockedException> { Socket("127.0.0.1", 9) }
        e.message shouldContain "network"
    }

    @Test
    fun opensNoServerSocket() {
        shouldThrow<NetworkAccessBlockedException> { ServerSocket(0) }
    }

    @Test
    fun blockingIsInstalledByTheAutodetectedExtension() {
        check(NoNetworkExtension.installed) { "extension was not applied to this test class" }
    }
}
