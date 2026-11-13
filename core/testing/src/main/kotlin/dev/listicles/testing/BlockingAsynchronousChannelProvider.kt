package dev.listicles.testing

import java.nio.channels.AsynchronousChannelGroup
import java.nio.channels.AsynchronousServerSocketChannel
import java.nio.channels.AsynchronousSocketChannel
import java.nio.channels.spi.AsynchronousChannelProvider
import java.util.concurrent.ExecutorService
import java.util.concurrent.ThreadFactory

/**
 * `AsynchronousSocketChannel` and `AsynchronousServerSocketChannel` use their own provider, not the
 * `SelectorProvider`, so this wraps the JDK's default one the same way [BlockingSelectorProvider] does: everything
 * is delegated, but opening a socket or server socket channel fails once [NoNetwork] is installed.
 * Set with `-Djava.nio.channels.spi.AsynchronousChannelProvider` (the class name of this provider)
 * and `--add-exports java.base/sun.nio.ch=ALL-UNNAMED` (see `build.gradle.kts`).
 */
class BlockingAsynchronousChannelProvider : AsynchronousChannelProvider() {
    private val delegate: AsynchronousChannelProvider = defaultProvider()

    override fun openAsynchronousChannelGroup(
        nThreads: Int,
        threadFactory: ThreadFactory,
    ): AsynchronousChannelGroup = delegate.openAsynchronousChannelGroup(nThreads, threadFactory)

    override fun openAsynchronousChannelGroup(
        executor: ExecutorService,
        initialSize: Int,
    ): AsynchronousChannelGroup = delegate.openAsynchronousChannelGroup(executor, initialSize)

    override fun openAsynchronousServerSocketChannel(
        group: AsynchronousChannelGroup?,
    ): AsynchronousServerSocketChannel {
        if (NoNetwork.installed) NoNetwork.blocked("asynchronous server socket channel")
        return delegate.openAsynchronousServerSocketChannel(group)
    }

    override fun openAsynchronousSocketChannel(group: AsynchronousChannelGroup?): AsynchronousSocketChannel {
        if (NoNetwork.installed) NoNetwork.blocked("asynchronous socket channel")
        return delegate.openAsynchronousSocketChannel(group)
    }

    private companion object {
        fun defaultProvider(): AsynchronousChannelProvider {
            val type = Class.forName("sun.nio.ch.DefaultAsynchronousChannelProvider")
            val factory = type.methods.first { it.name == "create" || it.name == "get" }
            return factory.invoke(null) as AsynchronousChannelProvider
        }
    }
}
