package dev.listicles.architecture

import java.io.File

/**
 * Hardcoded user-visible text in Compose code (#214; lint `HardcodedText` covers XML only).
 *
 * A violation is a string literal that contains a letter (outside `$` templates and escapes such as `\n`) and is
 * - the first positional argument of `Text(` or `showSnackbar(`,
 * - the second positional argument of `Icon(` or `Image(` (the content description),
 * - the value of a named argument `text`, `contentDescription`, `label`, `placeholder`, `title`, `message`,
 *   `supportingText`, `actionLabel`, `onClickLabel` or `stateDescription`, or
 * - assigned to `contentDescription` or `stateDescription` in a `semantics { }` block.
 *
 * Exempt: `label` of an animation API (`animate*AsState`, `animateFloat` and its siblings, `updateTransition`,
 * `rememberInfiniteTransition`, `AnimatedVisibility`, `AnimatedContent`, `Crossfade`), which names the animation for
 * tooling and is never shown. Test tags, routes, log tags and other literals are not matched.
 *
 * **Not covered (review catches these):** a literal behind an expression (`text = if (x) "A" else "B"`, `when`),
 * text built with `buildAnnotatedString { append("...") }`, `Toast.makeText`, and any other function that takes a
 * user-visible string.
 *
 * Allowed: code inside the block body of a `@Preview` function (also `@PreviewLightDark` and the other built-in
 * multipreviews), and a literal whose call line carries `// justified: <reason>` with at least three words of
 * letters. Comments and string text are blanked ([ArchitectureRules.blankCommentsAndStrings]) to find calls, so prose
 * and code in strings never match.
 */
object UiHardcodedStringRules {
    private val positional = Regex("""(?<!\w)(?<name>Text|showSnackbar)\(""")
    private val iconOrImage = Regex("""(?<!\w)(?<name>Icon|Image)\(""")
    private val named =
        Regex(
            """[(,]\s*(?<name>text|contentDescription|label|placeholder|title|message|supportingText|""" +
                """actionLabel|onClickLabel|stateDescription)\s*=(?!=)""",
        )
    private val semantics = Regex("""(?m)(?:^|[{;])\s*(?<name>contentDescription|stateDescription)\s*=(?!=)""")
    private val animationCall =
        Regex(
            """animate\w*AsState|animate(?:Float|Color|Dp|Int|Value|Size|Offset|IntSize|IntOffset|Rect)|""" +
                """updateTransition|rememberInfiniteTransition|AnimatedVisibility|AnimatedContent|Crossfade""",
        )
    private val previewAnnotation = Regex("""@Preview(?:LightDark|ScreenSizes|FontScale|DynamicColors)?(?!\w)""")
    private val modifiers =
        setOf(
            "private",
            "internal",
            "public",
            "inline",
            "suspend",
            "actual",
            "expect",
            "tailrec",
            "operator",
            "infix",
            "external",
            "override",
            "open",
            "final",
        )
    private val justification = Regex("""//\s*justified:(.*)$""")
    private val template = Regex("""\$\{[^}]*}|\$\w+|\\u[0-9a-fA-F]{4}|\\.""")
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
        return literalStarts(text, masked)
            .filter { (_, open) -> text.getOrNull(open) == '"' && hasWords(text, open) }
            .map { (start, _) -> start }
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

    // Pairs of (offset where the call or assignment starts, offset of the first non-blank character of the value).
    private fun literalStarts(
        text: String,
        masked: String,
    ): List<Pair<Int, Int>> {
        val direct =
            positional.findAll(masked) +
                named.findAll(masked).filterNot { isAnimationLabel(masked, it) } +
                semantics.findAll(masked)
        val second =
            iconOrImage.findAll(masked).mapNotNull { match ->
                secondArgument(masked, match.range.last)?.let { callStart(match) to skipBlanks(text, it) }
            }
        return (direct.map { callStart(it) to skipBlanks(text, it.range.last + 1) } + second).toList()
    }

    // `label` of an animation API names the animation for tooling and is never shown to the user.
    private fun isAnimationLabel(
        masked: String,
        match: MatchResult,
    ): Boolean =
        match.groups["name"]?.value == "label" && animationCall.matches(enclosingCallName(masked, match.range.first))

    // Name of the call whose argument list contains [at] (a `(` or `,` of that list), or "" when there is none.
    private fun enclosingCallName(
        masked: String,
        at: Int,
    ): String {
        var depth = 0
        var i = at
        while (i >= 0 && !(masked[i] == '(' && depth == 0)) {
            if (masked[i] == ')') depth++
            if (masked[i] == '(') depth--
            i--
        }
        var end = i
        while (end > 0 && masked[end - 1].isWhitespace()) end--
        if (end > 0 && masked[end - 1] == '>') end = masked.lastIndexOf('<', end - 1).coerceAtLeast(0)
        return masked.substring(0, end).takeLastWhile { it.isLetterOrDigit() || it == '_' }
    }

    // Offset just after the first top-level comma of the call whose `(` is at [open]; null when there is none.
    private fun secondArgument(
        masked: String,
        open: Int,
    ): Int? {
        var depth = 0
        var result: Int? = null
        var i = open + 1
        while (result == null && i < masked.length && depth >= 0) {
            val c = masked[i]
            if (c in "([{") depth++
            if (c in ")]}") depth--
            if (c == ',' && depth == 0) result = i + 1
            i++
        }
        return result
    }

    // Offset ranges of the block bodies of @Preview functions, found on the blanked text so braces balance.
    private fun previewRanges(masked: String): List<IntRange> =
        previewAnnotation.findAll(masked).mapNotNull { previewBody(masked, it.range.last + 1) }.toList()

    // The block body of the function that the annotation ending at [from] belongs to. Null when the annotation
    // belongs to something else (an annotation class) or the function has an expression body.
    private fun previewBody(
        masked: String,
        from: Int,
    ): IntRange? {
        val params = funKeywordEnd(masked, from)?.let { masked.indexOf('(', it) } ?: -1
        val body = if (params < 0) null else bodyStart(masked, closing(masked, params) + 1)
        return if (body != null && masked[body] == '{') body..closing(masked, body) else null
    }

    // Offset of the `{` or `=` that ends the signature after the parameter list; null when anything but an optional
    // return type comes first (a bodyless declaration), so the search never reaches the next declaration.
    private fun bodyStart(
        masked: String,
        from: Int,
    ): Int? {
        val end = (from until masked.length).firstOrNull { masked[it] in "{=};" }
        val gap = end?.let { masked.substring(from, it).trim() }
        val signatureOnly = gap != null && (gap.isEmpty() || (gap.startsWith(":") && '\n' !in gap))
        return if (signatureOnly) end else null
    }

    // Offset after the `fun` keyword that follows only annotations and modifiers from [from]; null otherwise.
    private fun funKeywordEnd(
        masked: String,
        from: Int,
    ): Int? {
        var i = from
        var result: Int? = null
        while (result == null && i >= 0 && i < masked.length) {
            while (i < masked.length && masked[i].isWhitespace()) i++
            val word = masked.drop(i).takeWhile { it.isLetterOrDigit() || it == '_' }
            i =
                when {
                    masked.startsWith("(", i) -> closing(masked, i) + 1
                    masked.startsWith("@", i) -> i + 1 + masked.drop(i + 1).takeWhile { it.isLetterOrDigit() }.length
                    word == "fun" -> (i + word.length).also { result = it }
                    word in modifiers -> i + word.length
                    else -> -1
                }
        }
        return result
    }

    // Index of the bracket that closes the `(` or `{` at [open]; the last index when it is never closed.
    private fun closing(
        masked: String,
        open: Int,
    ): Int {
        val up = masked[open]
        val down = if (up == '(') ')' else '}'
        var depth = 0
        for (i in open until masked.length) {
            if (masked[i] == up) depth++
            if (masked[i] == down && --depth == 0) return i
        }
        return masked.length - 1
    }

    private fun justified(line: String): Boolean =
        justification.find(line)?.let { word.findAll(it.groupValues[1]).count() >= MIN_JUSTIFICATION_WORDS } ?: false
}
