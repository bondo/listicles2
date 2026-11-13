package dev.listicles.testing

class NetworkAccessBlockedException(
    message: String,
) : RuntimeException(message)

/** Stub: the real block comes in the next commit. */
object NoNetwork {
    val installed: Boolean get() = false

    fun install() = Unit
}
