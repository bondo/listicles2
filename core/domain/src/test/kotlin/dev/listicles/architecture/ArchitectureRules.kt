package dev.listicles.architecture

import com.lemonappdev.konsist.api.Konsist
import com.lemonappdev.konsist.api.declaration.KoFileDeclaration
import java.io.File

/**
 * Architecture rules (P7, P25). Konsist lists the Kotlin files of a directory; the checks run on their text with
 * comments and string literals blanked, so a rule never fires on prose. Line numbers are preserved.
 */
object ArchitectureRules {
    private val floatingPatterns =
        listOf(
            Regex("""\b(Float|Double)\b"""),
            Regex("""\.to(Float|Double)\b"""),
            Regex("""(?<![\w.])\d+\.\d+(?:[eE][+-]?\d+)?[fF]?\b"""),
            Regex("""\b\d+[fF]\b"""),
            Regex("""\b\d+[eE][+-]?\d+\b"""),
            // Only whole-number helpers of kotlin.math are allowed.
            Regex("""\bkotlin\.math\.(?!(?:abs|min|max|sign|absoluteValue)\b)(?:\w+|\*)"""),
        )

    private val rawUiPatterns =
        listOf(
            Regex("""\bColor\(\s*0[xX]"""),
            Regex("""\d\.(?:dp|sp)\b"""),
        )

    fun scannedFileCount(dir: File): Int = files(dir).size

    fun floatingPointViolations(dir: File): List<String> = violations(dir, floatingPatterns) { true }

    /** Raw colors and dp/sp literals are allowed only in the theme: a `theme` directory or a `Theme.kt` file. */
    fun rawUiValueViolations(dir: File): List<String> = violations(dir, rawUiPatterns) { !isThemeFile(it) }

    private fun isThemeFile(file: KoFileDeclaration): Boolean =
        file.path.split('/', '\\').let { parts -> "theme" in parts.dropLast(1) || parts.last() == "Theme.kt" }

    private fun files(dir: File): List<KoFileDeclaration> =
        if (dir.exists()) Konsist.scopeFromDirectory(relativeToProjectRoot(dir)).files else emptyList()

    // Konsist resolves directories against the project root (has settings.gradle.kts), not the working dir.
    private fun relativeToProjectRoot(dir: File): String {
        val root =
            generateSequence(
                File("").canonicalFile,
            ) { it.parentFile }.first { File(it, "settings.gradle.kts").exists() }
        return dir.canonicalFile.relativeTo(root).path
    }

    private fun violations(
        dir: File,
        patterns: List<Regex>,
        applies: (KoFileDeclaration) -> Boolean,
    ): List<String> =
        files(dir).filter(applies).flatMap { file ->
            blankCommentsAndStrings(file.text).lines().flatMapIndexed { index, line ->
                patterns.filter { it.containsMatchIn(line) }.map { "${file.path}:${index + 1}: ${line.trim()}" }
            }
        }

    private val blanking = Regex("""/\*[\s\S]*?\*/|//[^\n]*|"(?:\\.|[^"\\\n])*"|'(?:\\.|[^'\\\n])*'""")

    internal fun blankCommentsAndStrings(text: String): String =
        blanking.replace(text) { match -> match.value.map { if (it == '\n') '\n' else ' ' }.joinToString("") }
}
