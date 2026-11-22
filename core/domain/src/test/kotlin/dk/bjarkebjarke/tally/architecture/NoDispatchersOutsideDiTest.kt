package dk.bjarkebjarke.tally.architecture

import io.kotest.matchers.collections.shouldBeEmpty
import io.kotest.matchers.collections.shouldNotBeEmpty
import io.kotest.matchers.shouldBe
import io.kotest.matchers.string.shouldContain
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.io.TempDir
import java.io.File

/**
 * `Dispatchers.` appears only in a DI module, a file with a Dagger or Hilt `@Module` (ANDROID-BEST-PRACTICES follow-up
 * 1, M1-57); everything else gets its dispatcher injected. The rule keys on the annotation, not a path, so it is
 * active before the first DI module exists. The fixtures are the violating and the clean files the rule is judged on.
 */
class NoDispatchersOutsideDiTest {
    @TempDir
    lateinit var dir: File

    private fun violationsOf(
        code: String,
        path: String = "data/Repo.kt",
    ): List<String> {
        val file = File(dir, path)
        file.parentFile.mkdirs()
        file.writeText("package sample\n\n$code\n")
        return DataSourceRules.dispatchersOutsideDiViolations(dir)
    }

    @Test
    fun realProductionSourcesNameNoDispatcherOutsideADiModule() {
        DataSourceRules
            .productionSourceDirs(File("../.."))
            .flatMap { DataSourceRules.dispatchersOutsideDiViolations(it) }
            .shouldBeEmpty()
    }

    @Test
    fun scansTheRealProductionSources() {
        val dirs = DataSourceRules.productionSourceDirs(File("../.."))
        val scanned = dirs.sumOf { ArchitectureRules.scannedFileCount(it) }
        check(scanned > 0) { "scanned nothing" }
    }

    // ---- violating fixtures ----

    @Test
    fun rejectsAHardCodedDispatcherInARepository() {
        violationsOf("class Repo {\n    suspend fun f() = withContext(Dispatchers.IO) { 1 }\n}")
            .single()
            .shouldContain("data/Repo.kt:4:")
    }

    @Test
    fun rejectsEveryStandardDispatcher() {
        listOf("IO", "Default", "Main", "Main.immediate", "Unconfined").forEach {
            violationsOf("val d = Dispatchers.$it").shouldNotBeEmpty()
        }
    }

    @Test
    fun rejectsTheImports() {
        violationsOf("import kotlinx.coroutines.Dispatchers").shouldNotBeEmpty()
        violationsOf("import kotlinx.coroutines.Dispatchers.IO").shouldNotBeEmpty()
        violationsOf("import kotlinx.coroutines.Dispatchers as D").shouldNotBeEmpty()
    }

    @Test
    fun rejectsAFullyQualifiedUse() {
        violationsOf("val d = kotlinx.coroutines.Dispatchers.IO").shouldNotBeEmpty()
    }

    @Test
    fun rejectsUseInAViewModelAndInAComposable() {
        violationsOf(
            "class A : ViewModel() {\n    fun f() { viewModelScope.launch(Dispatchers.Default) { } }\n}",
            "ui/AViewModel.kt",
        ).shouldNotBeEmpty()
        violationsOf("@Composable\nfun S() {\n    val d = Dispatchers.Main\n}", "ui/Screen.kt").shouldNotBeEmpty()
    }

    @Test
    fun rejectsUseInsideAStringTemplate() {
        violationsOf("val s = \"\${Dispatchers.IO}\"").shouldNotBeEmpty()
    }

    @Test
    fun rejectsAModuleThatIsNotAnnotated() {
        violationsOf("object DispatcherModule {\n    val io = Dispatchers.IO\n}", "di/DispatcherModule.kt")
            .shouldNotBeEmpty()
    }

    @Test
    fun reportsEveryUse() {
        violationsOf("import kotlinx.coroutines.Dispatchers\n\nval d = Dispatchers.IO").size shouldBe 2
    }

    // ---- clean fixtures ----

    @Test
    fun acceptsAnInjectedDispatcher() {
        violationsOf(
            "class Repo(private val io: CoroutineDispatcher) {\n    suspend fun f() = withContext(io) { 1 }\n}",
        ).shouldBeEmpty()
    }

    @Test
    fun acceptsDispatchersInADiModule() {
        violationsOf(
            "import dagger.Module\nimport kotlinx.coroutines.Dispatchers\n\n@Module\n" +
                "@InstallIn(SingletonComponent::class)\n" +
                "object DispatcherModule {\n    @Provides\n    fun io(): CoroutineDispatcher = Dispatchers.IO\n}",
            "di/DispatcherModule.kt",
        ).shouldBeEmpty()
    }

    @Test
    fun acceptsAModuleWithAWildcardDaggerImport() {
        violationsOf("import dagger.*\n\n@Module\nobject M {\n    val d = Dispatchers.IO\n}", "di/M.kt").shouldBeEmpty()
    }

    @Test
    fun acceptsAQualifiedModuleAnnotationAndAModuleAnywhere() {
        violationsOf(
            "@dagger.Module\nobject M {\n    val d = Dispatchers.Default\n}",
            "app/src/main/Wiring.kt",
        ).shouldBeEmpty()
    }

    @Test
    fun aModuleFileDoesNotExemptOtherFiles() {
        File(dir, "di").mkdirs()
        File(dir, "di/Module.kt")
            .writeText("package sample\n\nimport dagger.Module\n\n@Module\nobject M { val d = Dispatchers.IO }\n")
        violationsOf("val d = Dispatchers.IO").single().shouldContain("data/Repo.kt")
    }

    @Test
    fun acceptsNamesThatOnlyContainDispatchers() {
        violationsOf(
            "val a = AppDispatchers.IO\nval b = MyDispatchers\nval c = DispatchersProvider()\n" +
                "val d = StandardTestDispatcher()\nval e = dispatchers.io",
        ).shouldBeEmpty()
    }

    @Test
    fun acceptsDispatchersInCommentsAndStrings() {
        violationsOf(
            "// never use Dispatchers.IO here\n/* Dispatchers.Main */\nval s = \"Dispatchers.IO\"",
        ).shouldBeEmpty()
    }

    // ---- the module exemption has limits ----

    @Test
    fun rejectsAModuleAnnotationFromAnotherLibrary() {
        violationsOf("@Module\nobject M {\n    val d = Dispatchers.IO\n}", "di/M.kt").shouldNotBeEmpty()
        violationsOf("@org.koin.Module\nobject N {\n    val d = Dispatchers.IO\n}", "di/N.kt").shouldNotBeEmpty()
        violationsOf("import org.koin.core.annotation.Module\n\n@Module\nobject O { val d = Dispatchers.IO }", "O.kt")
            .shouldNotBeEmpty()
    }

    @Test
    fun rejectsAModuleThatIsOnlyMentionedInACommentOrAString() {
        violationsOf("import dagger.Module\n\n// @Module\nval d = Dispatchers.IO", "A.kt").shouldNotBeEmpty()
        violationsOf("import dagger.Module\n\nval s = \"@Module\"\nval d = Dispatchers.IO", "B.kt").shouldNotBeEmpty()
    }

    @Test
    fun rejectsAnnotationsThatOnlyStartWithModule() {
        listOf("@SubModule", "@Modules", "@ModuleX", "@dagger.Modules").forEach {
            violationsOf("import dagger.Module\n\n$it\nobject M { val d = Dispatchers.IO }", "M.kt").shouldNotBeEmpty()
        }
    }

    // ---- which directories the rule scans ----

    @Test
    fun scansProductionSourceSetsButNotTestCodeOrTheTestSupportModule() {
        listOf(
            "app/src/main",
            "app/src/debug",
            "app/src/test",
            "app/src/androidTest",
            "app/src/testFixtures",
            "app/src/testDebug",
            "app/src/androidTestRelease",
            "app/src/testFlavorDebug",
            "app/src/testing",
            "core/data/src/main",
            "core/testing/src/main",
            "core/testing/src/test",
            "feature/testing/src/main",
        ).forEach { File(dir, it).mkdirs() }
        DataSourceRules
            .productionSourceDirs(dir)
            .map { it.relativeTo(dir).path }
            .sorted() shouldBe
            listOf("app/src/debug", "app/src/main", "app/src/testing", "core/data/src/main", "feature/testing/src/main")
    }

    @Test
    fun aMissingDirectoryHasNoViolations() {
        DataSourceRules.dispatchersOutsideDiViolations(File(dir, "missing")).shouldBeEmpty()
    }
}
