package dev.listicles.architecture

import com.lemonappdev.konsist.api.Konsist
import com.lemonappdev.konsist.api.declaration.KoFileDeclaration
import java.io.File

/**
 * Architecture rules (P7, P25). Konsist scopes a directory to its Kotlin files; the checks run on each file's text
 * with comments and string literal text blanked (code inside `${...}` templates is kept), so a rule never fires on
 * prose but does fire on code hidden in a template. Line numbers are preserved.
 *
 * The UI rule is: outside the theme, no `Color(` call that starts with a number or a named `red`, `green`, `blue`,
 * `alpha`, `color` or `value` argument (also when the arguments start on the next line), no named hue constant
 * (`Color.Red`, `Color.Black`, `Color.Gray` and so on; `Color.Transparent` and `Color.Unspecified` are not a colour
 * choice and stay allowed), no `Dp(` or `TextUnit(`, and no `.dp`, `.sp` or `.em` at all (so `16.dp`, `0.5.dp`, `n.dp`
 * and `2.em` all fail); import lines are not code. Matches are found in the whole file text, so a call split over
 * several lines is reported at the line where it starts.
 */
object ArchitectureRules {
    private val floatingPatterns =
        listOf(
            Regex("""\b(Float|Double)\b"""),
            Regex("""\.to(Float|Double)(OrNull)?\b"""),
            // BigDecimal is exact but not whole-number; BigInteger stays allowed.
            Regex("""\b(?:BigDecimal|toBigDecimal(?:OrNull)?)\b"""),
            Regex("""\bnext(Float|Double)\b"""),
            Regex("""(?<![\w.])\d[\d_]*\.\d[\d_]*(?:[eE][+-]?\d+)?[fF]?\b"""),
            Regex("""(?<![\w.])\.\d"""),
            Regex("""\b\d[\d_]*(?:\.\d+)?[eE][+-]?\d+[fF]?\b"""),
            Regex("""\b\d[\d_]*[fF]\b"""),
            Regex("""\b(?:Strict)?Math\."""),
            Regex("""\baverage\("""),
            // Only whole-number helpers of kotlin.math are allowed.
            Regex("""\bkotlin\.math\.(?!(?:abs|min|max|sign|absoluteValue)\b)(?:\w+|\*)"""),
        )

    private val rawUiPatterns =
        listOf(
            Regex("""\bColor\(\s*(?:\d|(?:red|green|blue|alpha|color|value)\s*=)"""),
            Regex("""\bColor\.(?:Black|DarkGray|Gray|LightGray|White|Red|Green|Blue|Yellow|Cyan|Magenta)\b"""),
            Regex("""\b(?:Dp|TextUnit)\("""),
            Regex("""\.(?:dp|sp|em)\b"""),
        )

    private val importLine = Regex("""^\s*import\s""")

    fun scannedFileCount(dir: File): Int = files(dir).size

    fun floatingPointViolations(dir: File): List<String> =
        violations(dir, floatingPatterns, skipImports = false) { true }

    /** Raw colors and dp/sp values are allowed only in the theme: a `theme` directory or `Theme.kt` under [dir]. */
    fun rawUiValueViolations(dir: File): List<String> =
        violations(dir, rawUiPatterns, skipImports = true) { relativeParts(dir, it).let { parts -> !isTheme(parts) } }

    // Judged on the path below the scanned directory only, so where the repository is checked out does not matter.
    private fun relativeParts(
        dir: File,
        file: KoFileDeclaration,
    ): List<String> =
        File(file.path)
            .canonicalFile
            .relativeTo(dir.canonicalFile)
            .path
            .split('/', '\\')

    private fun isTheme(parts: List<String>): Boolean = "theme" in parts.dropLast(1) || parts.last() == "Theme.kt"

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
        skipImports: Boolean,
        applies: (KoFileDeclaration) -> Boolean,
    ): List<String> =
        files(dir).filter(applies).flatMap { file ->
            val name = File(file.path).canonicalFile.relativeTo(dir.canonicalFile).path
            val text = blankCommentsAndStrings(file.text)
            val lines = text.split('\n')
            patterns
                .flatMap { pattern ->
                    pattern
                        .findAll(text)
                        .map { lineIndex(text, it.range.first) }
                        .distinct()
                        .toList()
                }.filterNot { skipImports && importLine.containsMatchIn(lines[it]) }
                .sorted()
                .map { "$name:${it + 1}: ${lines[it].trim()}" }
        }

    // Zero-based line of a character offset; matches run over the whole text so a call may span several lines.
    private fun lineIndex(
        text: String,
        offset: Int,
    ): Int = text.take(offset).count { it == '\n' }

    internal fun blankCommentsAndStrings(text: String): String = Blanker(text).run()

    /** Replaces comments (nested block comments too) and string text by spaces; keeps newlines and template code. */
    private class Blanker(
        private val src: String,
    ) {
        private val out = StringBuilder(src.length)
        private var i = 0

        fun run(): String {
            code(inTemplate = false)
            return out.toString()
        }

        private fun keep() {
            out.append(src[i++])
        }

        private fun blank() {
            out.append(if (src[i] == '\n') '\n' else ' ')
            i++
        }

        private fun code(inTemplate: Boolean) {
            var depth = 0
            while (i < src.length) {
                val c = src[i]
                if (inTemplate && c == '}' && depth == 0) return
                if (inTemplate) depth += braceDelta(c)
                if (!skipCommentOrLiteral()) keep()
            }
        }

        private fun braceDelta(c: Char): Int =
            when (c) {
                '{' -> 1
                '}' -> -1
                else -> 0
            }

        /** Consumes a comment or a literal starting at the cursor; false when the cursor is on plain code. */
        private fun skipCommentOrLiteral(): Boolean =
            when {
                src.startsWith("//", i) -> {
                    while (i < src.length && src[i] != '\n') blank()
                    true
                }

                src.startsWith("/*", i) -> {
                    blockComment()
                    true
                }

                src.startsWith("\"\"\"", i) -> {
                    string(raw = true)
                    true
                }

                src[i] == '"' -> {
                    string(raw = false)
                    true
                }

                src[i] == '\'' -> {
                    charLiteral()
                    true
                }

                else -> {
                    false
                }
            }

        private fun blockComment() {
            var depth = 0
            do {
                when {
                    src.startsWith("/*", i) -> {
                        depth++
                        blank()
                        blank()
                    }

                    src.startsWith("*/", i) -> {
                        depth--
                        blank()
                        blank()
                    }

                    else -> {
                        blank()
                    }
                }
            } while (depth > 0 && i < src.length)
        }

        private fun charLiteral() {
            blank()
            while (i < src.length && src[i] != '\'' && src[i] != '\n') {
                if (src[i] == '\\' && i + 1 < src.length) blank()
                blank()
            }
            if (i < src.length && src[i] == '\'') blank()
        }

        private fun string(raw: Boolean) {
            repeat(if (raw) 3 else 1) { blank() }
            while (i < src.length && !atStringEnd(raw)) stringPart(raw)
            endString(raw)
        }

        // A plain string also ends at a line break (unterminated), which is left for the code scanner.
        private fun atStringEnd(raw: Boolean): Boolean =
            if (raw) src.startsWith("\"\"\"", i) else src[i] == '"' || src[i] == '\n'

        private fun endString(raw: Boolean) {
            if (i >= src.length) return
            if (raw) {
                while (i < src.length && src[i] == '"') blank()
            } else if (src[i] == '"') {
                blank()
            }
        }

        private fun stringPart(raw: Boolean) {
            when {
                !raw && src[i] == '\\' && i + 1 < src.length -> {
                    blank()
                    blank()
                }

                src.startsWith("\${", i) -> {
                    template()
                }

                else -> {
                    blank()
                }
            }
        }

        private fun template() {
            blank()
            blank()
            code(inTemplate = true)
            if (i < src.length) blank()
        }
    }
}
