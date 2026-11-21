package dk.bjarkebjarke.tally.architecture

import java.io.File

/**
 * Two architecture rules (ANDROID-BEST-PRACTICES follow-up 1, M1-50). Like [ArchitectureRules], they run on each file's
 * text with comments and string text blanked, so prose never matches; a violation is `path:line: text`.
 *
 * **No data source in composables or ViewModels** ([dataSourceInUiViolations]). A UI file is a file that contains a
 * `@Composable` annotation, declares a class that extends `ViewModel` or `AndroidViewModel` (also by qualified name or
 * with the supertype on the next line), or is named `*ViewModel.kt`. In such a file every mention of a data source is a
 * violation: the Firebase SDK (`com.google.firebase`: Firestore, Auth and the rest), DataStore (`androidx.datastore`),
 * Room (`androidx.room`) and the data layer's own implementations (`dk.bjarkebjarke.tally.data`). Imports (also
 * wildcard and aliased ones) and fully qualified uses both count. Repository interfaces live in the domain, so a
 * composable or ViewModel that takes one passes; only the data layer touches a data source. Not covered (review
 * catches it): a ViewModel that extends another class which extends `ViewModel`, in a file not named `*ViewModel.kt`,
 * and a data source reached through a type alias declared elsewhere.
 *
 * **No `GlobalScope`** ([globalScopeViolations]), in every source set: work that must outlive a screen uses an
 * injected external scope.
 *
 * Which directories are scanned is [uiSourceDirs] (`src/main` of each module) and [allSourceDirs] (every source set).
 */
object DataSourceRules {
    private val dataSource =
        Regex(
            """(?<![\w.])(?:com\.google\.firebase|androidx\.datastore|androidx\.room|dk\.bjarkebjarke\.tally\.data)""" +
                """(?!\w)""",
        )

    private val composable = Regex("""(?<!\w)@(?:\w+\.)*Composable(?!\w)""")

    // `class A(...) : ViewModel()`, `: AndroidViewModel(app)`, `: androidx.lifecycle.ViewModel()`; a supertype call.
    private val viewModelSupertype = Regex(""":\s*(?:\w+\.)*(?:Android)?ViewModel\s*\(""")

    private val globalScope = Regex("""(?<![\w])GlobalScope(?!\w)""")

    // Module directories (`app`, `core/*`, `feature/*`) that can hold source sets.
    private val moduleParents = listOf("core", "feature")

    fun dataSourceInUiViolations(dir: File): List<String> =
        ArchitectureRules
            .codeFiles(dir)
            .filter { isUiFile(it) }
            .flatMap { matches(it, dataSource) }

    fun globalScopeViolations(dir: File): List<String> =
        ArchitectureRules.codeFiles(dir).flatMap { matches(it, globalScope) }

    /** `src/main` of the app and of every module under `core` and `feature`: where composables and ViewModels live. */
    fun uiSourceDirs(projectRoot: File): List<File> = sourceSets(projectRoot).filter { it.name == "main" }

    /** Every source set (`main`, `test`, `androidTest`, ...) of those modules. Build output is never scanned. */
    fun allSourceDirs(projectRoot: File): List<File> = sourceSets(projectRoot)

    private fun sourceSets(projectRoot: File): List<File> =
        modules(projectRoot).flatMap { module ->
            File(module, "src").listFiles { f -> f.isDirectory }.orEmpty().sortedBy { it.name }
        }

    private fun modules(projectRoot: File): List<File> =
        listOf(File(projectRoot, "app")) +
            moduleParents.flatMap { parent ->
                File(projectRoot, parent).listFiles { f -> f.isDirectory }.orEmpty().sortedBy { it.name }
            }

    private fun isUiFile(file: ArchitectureRules.CodeFile): Boolean =
        file.name.endsWith("ViewModel.kt") ||
            composable.containsMatchIn(file.text) ||
            viewModelSupertype.containsMatchIn(file.text)

    private fun matches(
        file: ArchitectureRules.CodeFile,
        pattern: Regex,
    ): List<String> {
        val lines = file.text.split('\n')
        return pattern
            .findAll(file.text)
            .map { ArchitectureRules.lineIndex(file.text, it.range.first) }
            .distinct()
            .sorted()
            .map { "${file.name}:${it + 1}: ${lines[it].trim()}" }
            .toList()
    }
}
