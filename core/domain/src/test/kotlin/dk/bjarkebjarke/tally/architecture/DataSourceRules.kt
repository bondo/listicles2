package dk.bjarkebjarke.tally.architecture

import java.io.File

/**
 * Four architecture rules (ANDROID-BEST-PRACTICES follow-up 1, M1-50 and M1-57). Like [ArchitectureRules], they run on
 * each file's text with comments and string text blanked, so prose never matches; a violation is `path:line: text`.
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
 * **No platform types in ViewModels** ([platformInViewModelViolations], M1-57). In a ViewModel file (the ViewModel
 * half of the UI-file definition above) every mention of `android.content.Context`, `android.app.Application` (a
 * `Context`), an Activity class (`android.app.Activity`, `androidx.activity.ComponentActivity`,
 * `androidx.appcompat.app.AppCompatActivity`, `androidx.fragment.app.FragmentActivity`), a wildcard import of those
 * packages, or `AndroidViewModel` is a violation: a ViewModel gets what it needs from injected domain types. Not
 * covered (review catches it): a `Context` reached through a type alias or a class from another module that wraps one.
 *
 * **No `Dispatchers.` outside a DI module** ([dispatchersOutsideDiViolations], M1-57). A DI module is a file with
 * `@dagger.Module`, or `@Module` plus an `import dagger.Module` (or `dagger.*`), wherever it lives: the rule keys on
 * the annotation, not on a path, so it is active before the first module exists and needs no path decision. The
 * exemption covers the whole file; a `@Module` from another library does not count. In any other production file
 * `Dispatchers` is a violation, import included; the dispatcher is injected. Test code is not scanned
 * ([productionSourceDirs]: no `test`, `androidTest`, `testFixtures` or variant test source set, and not the
 * `core/testing` support module), because `Dispatchers.setMain` is legitimate there.
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

    // `Context` (and `Application`, which is one), the Activity classes and the wildcard imports that bring them in.
    // `AndroidViewModel` is any mention, which covers the import and the supertype.
    private val platformInViewModel =
        Regex(
            """(?<![\w.])(?:android\.content\.(?:Context(?!\w)|\*)""" +
                """|android\.app\.(?:\w*Activity(?!\w)|Application(?!\w)|\*)""" +
                """|androidx\.(?:activity|appcompat\.app|fragment\.app)\.(?:\w*Activity(?!\w)|\*))""" +
                """|(?<!\w)AndroidViewModel(?!\w)""",
        )

    // `Dispatchers.IO`, `import kotlinx.coroutines.Dispatchers`, a qualified use; `AppDispatchers` does not match.
    private val dispatchers = Regex("""(?<!\w)Dispatchers(?!\w)""")

    // A Dagger or Hilt module: `@dagger.Module`, or `@Module` in a file that imports `dagger.Module` (or `dagger.*`).
    // A `@Module` from another library (Koin, JPMS-style) does not make a file a DI module.
    private val daggerModuleQualified = Regex("""(?<!\w)@(?:\w+:)?dagger\.Module(?!\w)""")
    private val moduleAnnotation = Regex("""(?<!\w)@(?:\w+:)?Module(?!\w)""")
    private val daggerModuleImport = Regex("""(?m)^\s*import\s+dagger\.(?:Module(?!\w)|\*)""")

    private val globalScope = Regex("""(?<![\w])GlobalScope(?!\w)""")

    // Source sets that are not production code; a UI file in one of them may use a fake or an emulator client.
    private val testSourceSets = setOf("test", "androidTest", "testFixtures")

    // `testDebug`, `testFlavorDebug`, `androidTestRelease`: variant test source sets.
    private val variantTestSourceSet = Regex("""(?:test|androidTest)[A-Z]\w*""")

    // Modules that only hold test support code; their source sets are named `main`.
    private val testSupportModules = setOf("core/testing/src/main")

    // Directories that hold no module: build output, dependency caches and hidden directories.
    private val skippedDirs = setOf("build", "node_modules")

    fun dataSourceInUiViolations(dir: File): List<String> =
        ArchitectureRules
            .codeFiles(dir)
            .filter { isUiFile(it) }
            .flatMap { matches(it, dataSource) }

    fun globalScopeViolations(dir: File): List<String> =
        ArchitectureRules.codeFiles(dir).flatMap { matches(it, globalScope) }

    /** Android `Context` or `Activity`, or `AndroidViewModel`, in a ViewModel file (M1-57). */
    fun platformInViewModelViolations(dir: File): List<String> =
        ArchitectureRules
            .codeFiles(dir)
            .filter { isViewModelFile(it) }
            .flatMap { matches(it, platformInViewModel) }

    /** `Dispatchers.` in a file that is not a Dagger or Hilt module (M1-57). */
    fun dispatchersOutsideDiViolations(dir: File): List<String> =
        ArchitectureRules
            .codeFiles(dir)
            .filterNot { isDiModule(it) }
            .flatMap { matches(it, dispatchers) }

    /** Every production source set (all but test, androidTest and testFixtures) of every module. */
    fun uiSourceDirs(projectRoot: File): List<File> = sourceSets(projectRoot).filter { it.name !in testSourceSets }

    /**
     * Production source sets for the `Dispatchers` rule: [uiSourceDirs] minus every variant test source set (a name
     * that starts with `test` or `androidTest` followed by a capital: `testDebug`, `androidTestRelease`) and minus the
     * `core/testing` module, which is test support although its source set is named `main`.
     */
    fun productionSourceDirs(projectRoot: File): List<File> =
        uiSourceDirs(projectRoot).filter { dir ->
            !variantTestSourceSet.matches(dir.name) &&
                dir.relativeTo(projectRoot).path.replace(File.separatorChar, '/') !in testSupportModules
        }

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
        composable.containsMatchIn(file.text) || isViewModelFile(file)

    private fun isDiModule(file: ArchitectureRules.CodeFile): Boolean =
        daggerModuleQualified.containsMatchIn(file.text) ||
            (moduleAnnotation.containsMatchIn(file.text) && daggerModuleImport.containsMatchIn(file.text))

    private fun isViewModelFile(file: ArchitectureRules.CodeFile): Boolean =
        file.name.endsWith("ViewModel.kt") ||
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
