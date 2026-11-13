package dev.listicles.testing

import java.net.ProtocolFamily
import java.nio.channels.DatagramChannel
import java.nio.channels.Pipe
import java.nio.channels.ServerSocketChannel
import java.nio.channels.SocketChannel
import java.nio.channels.spi.AbstractSelector
import java.nio.channels.spi.SelectorProvider

/**
 * NIO channels do not go through the `java.net` socket factories, so the JDK's default [SelectorProvider] is wrapped:
 * every call is delegated, but opening a socket, server socket or datagram channel fails once [NoNetwork] is
 * installed. Selectors and pipes stay allowed (they are not network traffic). Until then everything passes through,
 * so the Gradle worker can connect to the build.
 *
 * The JDK reads the provider class from a system property when it first needs one, so the Gradle test tasks set
 * `-Djava.nio.channels.spi.SelectorProvider=dev.listicles.testing.BlockingSelectorProvider`, and
 * `--add-exports java.base/sun.nio.ch=ALL-UNNAMED` so that the default provider can be found (see `build.gradle.kts`).
 */
class BlockingSelectorProvider : SelectorProvider() {
    private val delegate: SelectorProvider = defaultProvider()

    private fun check(what: String) {
        if (NoNetwork.installed) NoNetwork.blocked(what)
    }

    override fun openDatagramChannel(): DatagramChannel {
        check("datagram channel")
        return delegate.openDatagramChannel()
    }

    override fun openDatagramChannel(family: ProtocolFamily): DatagramChannel {
        check("datagram channel")
        return delegate.openDatagramChannel(family)
    }

    override fun openPipe(): Pipe = delegate.openPipe()

    override fun openSelector(): AbstractSelector = delegate.openSelector()

    override fun openServerSocketChannel(): ServerSocketChannel {
        check("server socket channel")
        return delegate.openServerSocketChannel()
    }

    override fun openSocketChannel(): SocketChannel {
        check("socket channel")
        return delegate.openSocketChannel()
    }

    private companion object {
        // JDK 21 calls the factory method `get`, JDK 17 `create`.
        fun defaultProvider(): SelectorProvider {
            val type = Class.forName("sun.nio.ch.DefaultSelectorProvider")
            val factory = type.methods.first { it.name == "get" || it.name == "create" }
            return factory.invoke(null) as SelectorProvider
        }
    }
}
