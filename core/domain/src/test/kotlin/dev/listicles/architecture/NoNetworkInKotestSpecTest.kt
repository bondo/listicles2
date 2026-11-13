package dev.listicles.architecture

import dev.listicles.testing.NetworkAccessBlockedException
import io.kotest.assertions.throwables.shouldThrow
import io.kotest.core.spec.style.FunSpec
import java.net.ServerSocket
import java.net.Socket

/** Most domain tests are Kotest specs, so the network block must hold for them too (R1-01). */
class NoNetworkInKotestSpecTest :
    FunSpec({
        test("a Kotest spec cannot open a server socket") {
            shouldThrow<NetworkAccessBlockedException> { ServerSocket(0) }
        }

        test("a Kotest spec cannot open a client socket") {
            shouldThrow<NetworkAccessBlockedException> { Socket("127.0.0.1", 9) }
        }
    })
