package dev.listicles.architecture

import java.io.File

/**
 * Hardcoded user-visible text in Compose code (#214; lint `HardcodedText` covers XML only).
 *
 * A violation is a string literal that contains a letter (outside `$` templates) and is either the first positional
 * argument of `Text(`, or the value of a named argument `text`, `contentDescription`, `label`, `placeholder`, `title`,
 * `message` or `supportingText`. Test tags, routes, log tags and other literals are not matched. Not matched either:
 * a literal that sits behind an expression (`text = if (x) "A" else "B"`); review covers those.
 *
 * Allowed: code inside `@Preview` functions with a block body, and a literal whose line carries
 * `// justified: <reason>` with at least three words of letters. Comments and string text are blanked
 * ([ArchitectureRules.blankCommentsAndStrings]) to find calls, so prose and code in strings never match.
 */
object UiHardcodedStringRules {
    private val positional = Regex("""(?<!\w)(?<name>Text)\(""")
    private val named =
        Regex(
            """(?<=[(,])\s*(?<name>text|contentDescription|label|placeholder|title|message|supportingText)\s*=(?!=)""",
        )
    private val previewFunction = Regex("""@Preview\w*""")
    private val justification = Regex("""//\s*justified:(.*)$""")
    private val template = Regex("""\$\{[^}]*}|\$\w+""")
    private val word = Regex("""\p{L}+""")
    private const val MIN_JUSTIFICATION_WORDS = 3

    fun violations(dir: File): List<String> =
        dir
            .walkTopDown()
            .filter { it.isFile && it.extension == "kt" }
            .sortedBy { it.path }
            .flatMap { file -> fileViolations(file.readText()).map { "${file.relativeTo(dir).path}:$it" } }
            .toList()

    private fun fileViolations(text: String): List<String> {
        val masked = ArchitectureRules.blankCommentsAndStrings(text)
        val previews = previewRanges(masked)
        val lines = text.split('\n')
        return (positional.findAll(masked) + named.findAll(masked))
            .map { it to skipBlanks(text, it.range.last + 1) }
            .filter { (_, open) -> text.getOrNull(open) == '"' && hasWords(text, open) }
            .map { (match, _) -> match }
            .map { callStart(it) }
            .filter { start -> previews.none { start in it } }
            .map { start -> text.take(start).count { it == '\n' } }
            .distinct()
            .filterNot { justified(lines[it]) }
            .sorted()
            .map { "${it + 1}: ${lines[it].trim()}" }
            .toList()
    }

    private fun callStart(match: MatchResult): Int = match.groups["name"]!!.range.first

    // First offset at or after [from] that is not whitespace or a comment (a string literal starts with a quote).
    private fun skipBlanks(
        text: String,
        from: Int,
    ): Int {
        var i = from
        while (i < text.length) {
            val next = if (text[i].isWhitespace()) i + 1 else commentEnd(text, i)
            if (next < 0) return i
            i = next
        }
        return i
    }

    // Offset after the comment starting at [i], or -1 when [i] does not start a comment.
    private fun commentEnd(
        text: String,
        i: Int,
    ): Int =
        when {
            text.startsWith("//", i) -> text.indexOf('\n', i).let { if (it < 0) text.length else it }
            text.startsWith("/*", i) -> text.indexOf("*/", i).let { if (it < 0) text.length else it + 2 }
            else -> -1
        }

    // Whether the literal starting at [open] has a letter outside its `$name` and `${...}` templates.
    private fun hasWords(
        text: String,
        open: Int,
    ): Boolean {
        val raw = text.startsWith("\"\"\"", open)
        val close = if (raw) "\"\"\"" else "\""
        var i = open + close.length
        var depth = 0

        fun atEnd() = i >= text.length || (depth == 0 && text.startsWith(close, i)) || (!raw && text[i] == '\n')
        while (!atEnd()) {
            depth +=
                if (text.startsWith("\${", i)) {
                    1
                } else if (text[i] == '}' && depth > 0) {
                    -1
                } else {
                    0
                }
            i += if (!raw && text[i] == '\\') 2 else 1
        }
        val body = text.substring(open + close.length, minOf(i, text.length))
        return template.replace(body, "").any { it.isLetter() }
    }

    // Offset ranges of the block bodies of @Preview functions, found on the blanked text so braces balance.
    private fun previewRanges(masked: String): List<IntRange> =
        previewFunction
            .findAll(masked)
            .mapNotNull { match ->
                val fn = Regex("""\bfun\s""").find(masked, match.range.last + 1) ?: return@mapNotNull null
                val open = masked.indexOf('{', fn.range.last)
                if (open < 0) return@mapNotNull null
                var depth = 0
                var i = open
                while (i < masked.length) {
                    depth +=
                        if (masked[i] == '{') {
                            1
                        } else if (masked[i] == '}') {
                            -1
                        } else {
                            0
                        }
                    if (depth == 0) break
                    i++
                }
                open..i
            }.toList()

    private fun justified(line: String): Boolean =
        justification.find(line)?.let { word.findAll(it.groupValues[1]).count() >= MIN_JUSTIFICATION_WORDS } ?: false
}
