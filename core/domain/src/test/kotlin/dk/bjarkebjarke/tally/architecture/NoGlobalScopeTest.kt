package dk.bjarkebjarke.tally.architecture

import io.kotest.matchers.collections.shouldBeEmpty
import io.kotest.matchers.collections.shouldNotBeEmpty
import io.kotest.matchers.shouldBe
import io.kotest.matchers.string.shouldContain
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.io.TempDir
import java.io.File

/** No `GlobalScope` anywhere: work that must outlive a screen uses an injected external scope (checklist, M1-50). */
class NoGlobalScopeTest {
    @TempDir
    lateinit var dir: File

    private fun violationsOf(
        code: String,
        path: String = "data/Repo.kt",
    ): List<String> {
        val file = File(dir, path)
        file.parentFile.mkdirs()
        file.writeText("package sample\n\n$code\n")
        return DataSourceRules.globalScopeViolations(dir)
    }

    @Test
    fun realSourcesNeverUseGlobalScope() {
        DataSourceRules
            .allSourceDirs(File("../.."))
            .flatMap { DataSourceRules.globalScopeViolations(it) }
            .shouldBeEmpty()
    }

    @Test
    fun scansTheRealSources() {
        check(DataSourceRules.allSourceDirs(File("../..")).sumOf { ArchitectureRules.scannedFileCount(it) } > 0) {
            "scanned nothing"
        }
    }

    @Test
    fun rejectsALaunchOnGlobalScope() {
        violationsOf("fun f() {\n    GlobalScope.launch { }\n}").single().shouldContain("data/Repo.kt:4:")
    }

    @Test
    fun rejectsTheImport() {
        violationsOf("import kotlinx.coroutines.GlobalScope").single().shouldContain(":3:")
    }

    @Test
    fun rejectsAnAliasedAndAWildcardlessQualifiedUse() {
        violationsOf("import kotlinx.coroutines.GlobalScope as Forever").shouldNotBeEmpty()
        violationsOf("fun f() = kotlinx.coroutines.GlobalScope.launch { }").shouldNotBeEmpty()
    }

    @Test
    fun rejectsUseInAViewModelAndInAComposable() {
        violationsOf(
            "class A : ViewModel() {\n    fun f() { GlobalScope.launch { } }\n}",
            "ui/AViewModel.kt",
        ).shouldNotBeEmpty()
        violationsOf("@Composable\nfun S() {\n    GlobalScope.async { 1 }\n}", "ui/Screen.kt").shouldNotBeEmpty()
    }

    @Test
    fun rejectsUseInsideAStringTemplate() {
        violationsOf("val s = \"\${GlobalScope.launch { }}\"").shouldNotBeEmpty()
    }

    @Test
    fun rejectsUseAsAValue() {
        violationsOf("val scope: CoroutineScope = GlobalScope").shouldNotBeEmpty()
    }

    @Test
    fun reportsEveryUse() {
        violationsOf("import kotlinx.coroutines.GlobalScope\n\nfun f() { GlobalScope.launch { } }").size shouldBe 2
    }

    @Test
    fun acceptsAnInjectedScope() {
        violationsOf(
            "class Repo(private val appScope: CoroutineScope) {\n    fun f() { appScope.launch { } }\n}",
        ).shouldBeEmpty()
    }

    @Test
    fun acceptsNamesThatOnlyContainGlobalScope() {
        violationsOf(
            "val a = MyGlobalScope\nval b = GlobalScopeLike()\nval c = globalScope\nval d = GlobalScope2",
        ).shouldBeEmpty()
    }

    @Test
    fun acceptsCommentsAndStrings() {
        violationsOf(
            "// never use GlobalScope.launch\n/* GlobalScope */\nval s = \"GlobalScope.launch\"",
        ).shouldBeEmpty()
    }

    @Test
    fun aMissingDirectoryHasNoViolations() {
        DataSourceRules.globalScopeViolations(File(dir, "missing")).shouldBeEmpty()
    }

    @Test
    fun scansEverySourceSetOfEveryModuleButNotBuildOutput() {
        listOf(
            "app/src/main",
            "app/src/test",
            "app/src/androidTest",
            "app/build/generated/src/main",
            "core/data/src/main",
            "core/data/src/test",
            "feature/lists/ui/src/main",
            "node_modules/x/src/main",
            "src/main",
        ).forEach { File(dir, it).mkdirs() }
        DataSourceRules
            .allSourceDirs(dir)
            .map { it.relativeTo(dir).path }
            .sorted() shouldBe
            listOf(
                "app/src/androidTest",
                "app/src/main",
                "app/src/test",
                "core/data/src/main",
                "core/data/src/test",
                "feature/lists/ui/src/main",
            )
    }
}
