package dev.listicles.architecture

class NetworkAccessBlockedException(
    message: String,
) : RuntimeException(message)

/** Stub: implemented in the next commit. */
object NoNetworkExtension {
    val installed: Boolean get() = System.getProperty("listicles.stub") != null
}
