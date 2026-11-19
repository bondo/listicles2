package dev.listicles.architecture

import java.io.File

/** Flags user-visible string literals in Compose code (#214). See [violations]. */
object UiHardcodedStringRules {
    fun violations(dir: File): List<String> = emptyList<String>().filter { dir.exists() } // red stub
}
