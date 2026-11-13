package dev.listicles.testing

import java.net.InetAddress
import java.net.UnknownHostException
import java.net.spi.InetAddressResolver
import java.net.spi.InetAddressResolver.LookupPolicy
import java.net.spi.InetAddressResolverProvider
import java.util.stream.Stream

/**
 * Blocks DNS (JDK 18+ resolver SPI, registered through `META-INF/services`): once [NoNetwork] is installed, a name
 * other than a loopback name fails with an [UnknownHostException] caused by [NetworkAccessBlockedException], and so
 * does a reverse lookup of a non-loopback address. Address literals never reach the resolver.
 */
class BlockingInetAddressResolverProvider : InetAddressResolverProvider() {
    override fun get(configuration: Configuration): InetAddressResolver {
        val builtin = configuration.builtinResolver()
        return object : InetAddressResolver {
            override fun lookupByName(
                host: String,
                policy: LookupPolicy,
            ): Stream<InetAddress> {
                if (NoNetwork.installed && host.lowercase() !in LOOPBACK_NAMES) throw blocked("DNS lookup of $host")
                return builtin.lookupByName(host, policy)
            }

            override fun lookupByAddress(addr: ByteArray): String {
                val loopback = InetAddress.getByAddress(addr).isLoopbackAddress
                if (NoNetwork.installed && !loopback) throw blocked("reverse DNS lookup")
                return builtin.lookupByAddress(addr)
            }
        }
    }

    override fun name(): String = "listicles-no-network"

    private fun blocked(what: String) =
        UnknownHostException("network blocked in tests: $what").apply {
            initCause(NetworkAccessBlockedException("network blocked in tests: $what"))
        }

    private companion object {
        val LOOPBACK_NAMES = setOf("localhost", "localhost.localdomain", "ip6-localhost", "ip6-loopback")
    }
}
