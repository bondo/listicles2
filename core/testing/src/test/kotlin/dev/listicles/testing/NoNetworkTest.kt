package dev.listicles.testing

import io.kotest.assertions.throwables.shouldThrowAny
import io.kotest.matchers.shouldBe
import org.junit.jupiter.api.Test
import java.net.DatagramPacket
import java.net.DatagramSocket
import java.net.InetAddress
import java.net.InetSocketAddress
import java.net.MulticastSocket
import java.net.ServerSocket
import java.net.Socket
import java.net.URI
import java.net.http.HttpClient
import java.net.http.HttpRequest
import java.net.http.HttpResponse
import java.nio.channels.DatagramChannel
import java.nio.channels.ServerSocketChannel
import java.nio.channels.SocketChannel

/** Every way a test could reach the network must fail with NetworkAccessBlockedException (PLAN 5.4, P13). */
class NoNetworkTest {
    private fun shouldBeBlocked(block: () -> Unit) {
        val failure = shouldThrowAny(block)
        generateSequence<Throwable>(failure) { it.cause }.any { it is NetworkAccessBlockedException } shouldBe true
    }

    @Test
    fun theBlockIsInstalledBeforeAnyTestRuns() {
        NoNetwork.installed shouldBe true
    }

    @Test
    fun installingTwiceIsHarmless() {
        NoNetwork.install()
        NoNetwork.installed shouldBe true
    }

    @Test
    fun blocksClientSocket() = shouldBeBlocked { Socket("127.0.0.1", DISCARD_PORT) }

    @Test
    fun blocksServerSocket() = shouldBeBlocked { ServerSocket(0) }

    @Test
    fun blocksNioClientChannel() =
        shouldBeBlocked {
            SocketChannel.open().use { it.connect(InetSocketAddress("127.0.0.1", DISCARD_PORT)) }
        }

    @Test
    fun blocksNioServerChannel() = shouldBeBlocked { ServerSocketChannel.open().use { it.bind(InetSocketAddress(0)) } }

    @Test
    fun blocksNioDatagramChannel() = shouldBeBlocked { DatagramChannel.open().close() }

    @Test
    fun blocksUdpSend() =
        shouldBeBlocked {
            DatagramSocket().use {
                it.send(DatagramPacket(ByteArray(1), 1, InetAddress.getLoopbackAddress(), DISCARD_PORT))
            }
        }

    @Test
    fun blocksMulticastSocket() = shouldBeBlocked { MulticastSocket().close() }

    @Test
    fun blocksHttpClient() =
        shouldBeBlocked {
            HttpClient
                .newHttpClient()
                .send(
                    HttpRequest.newBuilder(URI.create("http://127.0.0.1:$DISCARD_PORT/")).build(),
                    HttpResponse.BodyHandlers.discarding(),
                )
        }

    @Test
    fun blocksDnsLookupOfRemoteNames() = shouldBeBlocked { InetAddress.getByName("example.com") }

    @Test
    fun allowsLoopbackNameAndAddressLiterals() {
        // Not network traffic: documented as allowed so tests can build local addresses.
        InetAddress.getByName("localhost").isLoopbackAddress shouldBe true
        InetAddress.getByName("203.0.113.7").hostAddress shouldBe "203.0.113.7"
    }

    private companion object {
        const val DISCARD_PORT = 9
    }
}
