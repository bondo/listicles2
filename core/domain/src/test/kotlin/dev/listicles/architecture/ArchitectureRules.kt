package dev.listicles.architecture

import java.io.File

/** Stub: rules are implemented in the next commit, so the tests above are red for the right reason. */
object ArchitectureRules {
    fun floatingPointViolations(dir: File): List<String> = dir.list().orEmpty().filter { it.isEmpty() }

    fun rawUiValueViolations(dir: File): List<String> = dir.list().orEmpty().filter { it.isEmpty() }

    fun scannedFileCount(dir: File): Int = dir.list().orEmpty().count { it.isEmpty() }
}
