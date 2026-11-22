package dk.bjarkebjarke.tally.architecture

import io.kotest.matchers.collections.shouldBeEmpty
import io.kotest.matchers.collections.shouldNotBeEmpty
import io.kotest.matchers.shouldBe
import io.kotest.matchers.string.shouldContain
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.io.TempDir
import java.io.File

/**
 * ViewModels never hold an Android `Context` or `Activity` and never extend `AndroidViewModel` (ANDROID-BEST-PRACTICES
 * follow-up 1, M1-57). The fixtures are the violating and the clean files the rule is judged on.
 */
class NoPlatformInViewModelTest {
    @TempDir
    lateinit var dir: File

    private fun violationsOf(
        code: String,
        path: String = "ui/ListsViewModel.kt",
    ): List<String> {
        val file = File(dir, path)
        file.parentFile.mkdirs()
        file.writeText("package sample\n\n$code\n")
        return DataSourceRules.platformInViewModelViolations(dir)
    }

    @Test
    fun realViewModelsHoldNoContextOrActivity() {
        DataSourceRules
            .uiSourceDirs(File("../.."))
            .flatMap { DataSourceRules.platformInViewModelViolations(it) }
            .shouldBeEmpty()
    }

    @Test
    fun scansTheRealUiSources() {
        check(DataSourceRules.uiSourceDirs(File("../..")).sumOf { ArchitectureRules.scannedFileCount(it) } > 0) {
            "scanned nothing"
        }
    }

    // ---- violating fixtures ----

    @Test
    fun rejectsViewModelThatImportsContext() {
        violationsOf(
            "import android.content.Context\n\nclass ListsViewModel(private val context: Context) : ViewModel()",
        ).single().shouldContain("ui/ListsViewModel.kt:3:")
    }

    @Test
    fun rejectsViewModelThatImportsAnActivity() {
        violationsOf(
            "import android.app.Activity\n\nclass ListsViewModel(val activity: Activity) : ViewModel()",
        ).shouldNotBeEmpty()
        violationsOf(
            "import androidx.activity.ComponentActivity\n\nclass A(val a: ComponentActivity) : ViewModel()",
            "ui/A.kt",
        ).shouldNotBeEmpty()
        violationsOf(
            "import androidx.appcompat.app.AppCompatActivity\n\nclass B(val a: AppCompatActivity) : ViewModel()",
            "ui/B.kt",
        ).shouldNotBeEmpty()
        violationsOf(
            "import androidx.fragment.app.FragmentActivity\n\nclass C(val a: FragmentActivity) : ViewModel()",
            "ui/C.kt",
        ).shouldNotBeEmpty()
    }

    @Test
    fun rejectsWildcardImportsOfTheActivityPackagesAndOtherActivityClasses() {
        violationsOf("import androidx.activity.*\n\nclass A : ViewModel()", "ui/A.kt").shouldNotBeEmpty()
        violationsOf("import androidx.appcompat.app.*\n\nclass B : ViewModel()", "ui/B.kt").shouldNotBeEmpty()
        violationsOf("import androidx.fragment.app.*\n\nclass C : ViewModel()", "ui/C.kt").shouldNotBeEmpty()
        violationsOf("import android.app.ListActivity\n\nclass D : ViewModel()", "ui/D.kt").shouldNotBeEmpty()
    }

    @Test
    fun rejectsViewModelThatImportsApplication() {
        violationsOf(
            "import android.app.Application\n\nclass ListsViewModel(val app: Application) : ViewModel()",
        ).shouldNotBeEmpty()
    }

    @Test
    fun rejectsViewModelThatExtendsAndroidViewModel() {
        violationsOf(
            "import androidx.lifecycle.AndroidViewModel\n\nclass A(app: Foo) : AndroidViewModel(app)",
            "ui/Anything.kt",
        ).shouldNotBeEmpty()
        violationsOf("class B(app: Foo) : androidx.lifecycle.AndroidViewModel(app)", "ui/BViewModel.kt")
            .shouldNotBeEmpty()
    }

    @Test
    fun rejectsWildcardAndAliasImports() {
        violationsOf("import android.content.*\n\nclass A : ViewModel()").shouldNotBeEmpty()
        violationsOf("import android.app.*\n\nclass B : ViewModel()").shouldNotBeEmpty()
        violationsOf("import android.content.Context as Ctx\n\nclass C(val c: Ctx) : ViewModel()").shouldNotBeEmpty()
    }

    @Test
    fun rejectsAFullyQualifiedUse() {
        violationsOf("class A(val c: android.content.Context) : ViewModel()").single().shouldContain(":3:")
    }

    @Test
    fun rejectsByTheFileNameWhateverTheSupertype() {
        violationsOf("import android.content.Context\n\nclass Holder(val c: Context)", "ui/HolderViewModel.kt")
            .shouldNotBeEmpty()
    }

    @Test
    fun rejectsBySupertypeWhateverTheFileName() {
        violationsOf("import android.content.Context\n\nclass Holder(val c: Context) : ViewModel()", "ui/Holder.kt")
            .shouldNotBeEmpty()
    }

    @Test
    fun reportsEveryOffendingLine() {
        violationsOf(
            "import android.content.Context\nimport android.app.Activity\n\nclass A : ViewModel()",
        ).size shouldBe 2
    }

    // ---- clean fixtures ----

    @Test
    fun acceptsAViewModelThatUsesADomainRepository() {
        violationsOf(
            "import dk.bjarkebjarke.tally.domain.ListRepository\n\n" +
                "class ListsViewModel(val r: ListRepository) : ViewModel()",
        ).shouldBeEmpty()
    }

    @Test
    fun acceptsContextAndActivityOutsideViewModels() {
        violationsOf(
            "import android.content.Context\nimport android.app.Activity\n\n" +
                "class AndroidConnectivity(val c: Context)\n@Composable\nfun Screen(a: Activity) {}",
            "ui/Screen.kt",
        ).shouldBeEmpty()
    }

    @Test
    fun acceptsNamesThatOnlyLookLikeThem() {
        violationsOf(
            "import kotlin.coroutines.CoroutineContext\nimport android.content.ContextParams\n" +
                "import dk.bjarkebjarke.tally.domain.ActivityEntry\n" +
                "import androidx.lifecycle.AndroidViewModelFactory\n\n" +
                "class ListsViewModel(val c: CoroutineContext, val e: ActivityEntry) : ViewModel()",
        ).shouldBeEmpty()
    }

    @Test
    fun acceptsActivityLikeNamesInThePlatformPackages() {
        violationsOf("import android.app.ActivityManager\nimport android.app.Applications\n\nclass A : ViewModel()")
            .shouldBeEmpty()
    }

    @Test
    fun acceptsPackagesThatOnlyStartWithAPlatformName() {
        violationsOf("import android.contentish.Context\nimport android.apps.Activity\n\nclass A : ViewModel()")
            .shouldBeEmpty()
    }

    @Test
    fun acceptsPlatformNamesInCommentsAndStrings() {
        violationsOf(
            "// never import android.content.Context or AndroidViewModel here\n" +
                "class A : ViewModel() {\n    val s = \"android.app.Activity\"\n}",
        ).shouldBeEmpty()
    }

    @Test
    fun aMissingDirectoryHasNoViolations() {
        DataSourceRules.platformInViewModelViolations(File(dir, "missing")).shouldBeEmpty()
    }
}
