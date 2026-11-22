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
 * Which directories are scanned is [uiSourceDirs] (every production source set of each module) and [allSourceDirs]
 * (every source set). Assumes the data layer's package is `dk.bjarkebjarke.tally.data`; a module that picks another
 * package must extend the rule. Not covered either: `@Composable` through an import alias.
 */
object DataSourceRules {
    private val dataSource =
        Regex(
            """(?<![\w.])(?:com\.google\.firebase|androidx\.datastore|androidx\.room|dk\.bjarkebjarke\.tally\.data)""" +
                """(?!\w)""",
        )

    private val composable = Regex("""(?<!\w)@(?:\w+:)?(?:\w+\.)*Composable(?!\w)""")

    // `class A(...) : ViewModel()`, `: AndroidViewModel(app)`, `: androidx.lifecycle.ViewModel()`; the first supertype.
    private val viewModelSupertype = Regex(""":\s*(?:\w+\.)*(?:Android)?ViewModel\s*\(""")

    // The same call later in a class header's supertype list (`class A : Observer, ViewModel()`).
    private val viewModelLaterSupertype =
        Regex("""(?<![:\w.])(?:class|object)\s[^{;]*?,\s*(?:\w+\.)*(?:Android)?ViewModel\s*\(""")

    private val globalScope = Regex("""(?<![\w])GlobalScope(?!\w)""")

    // Source sets that are not production code; a UI file in one of them may use a fake or an emulator client.
    private val testSourceSets = setOf("test", "androidTest", "testFixtures")

    // Directories that hold no module: build output, dependency caches and hidden directories.
    private val skippedDirs = setOf("build", "node_modules")

    fun dataSourceInUiViolations(dir: File): List<String> =
        ArchitectureRules
            .codeFiles(dir)
            .filter { isUiFile(it) }
            .flatMap { matches(it, dataSource) }

    fun globalScopeViolations(dir: File): List<String> =
        ArchitectureRules.codeFiles(dir).flatMap { matches(it, globalScope) }

    /** `Context`, `Activity` or `AndroidViewModel` in a ViewModel file (M1-57). */
    fun platformInViewModelViolations(dir: File): List<String> =
        ArchitectureRules.codeFiles(dir).take(0).map { it.name }

    /** `Dispatchers.` in a file that is not a DI module (M1-57). */
    fun dispatchersOutsideDiViolations(dir: File): List<String> =
        ArchitectureRules.codeFiles(dir).take(0).map { it.name }

    /** Every production source set (all but test, androidTest and testFixtures) of every module. */
    fun uiSourceDirs(projectRoot: File): List<File> = sourceSets(projectRoot).filter { it.name !in testSourceSets }

    /** Every source set (`main`, `test`, `androidTest`, ...) of every module. Build output is never scanned. */
    fun allSourceDirs(projectRoot: File): List<File> = sourceSets(projectRoot)

    // A module is any directory below the project root that has a `src` directory, at any depth (`app`, `core/data`,
    // `feature/lists/ui`); the root itself is not one.
    private fun sourceSets(projectRoot: File): List<File> =
        projectRoot
            .walkTopDown()
            .onEnter { it == projectRoot || (it.name !in skippedDirs && !it.name.startsWith(".")) }
            .filter { it.isDirectory && it.name == "src" && it.parentFile != projectRoot }
            .flatMap { src -> src.listFiles { f -> f.isDirectory }.orEmpty().asSequence() }
            .sortedBy { it.path }
            .toList()

    /** Paths of the files in [dir] that count as composable or ViewModel files. */
    fun uiFileNames(dir: File): List<String> = ArchitectureRules.codeFiles(dir).filter { isUiFile(it) }.map { it.name }

    private fun isUiFile(file: ArchitectureRules.CodeFile): Boolean =
        file.name.endsWith("ViewModel.kt") ||
            composable.containsMatchIn(file.text) ||
            viewModelSupertype.containsMatchIn(file.text) ||
            viewModelLaterSupertype.containsMatchIn(file.text)

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
