package dk.bjarkebjarke.tally.architecture

import io.kotest.matchers.collections.shouldBeEmpty
import io.kotest.matchers.collections.shouldNotBeEmpty
import io.kotest.matchers.shouldBe
import io.kotest.matchers.string.shouldContain
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.io.TempDir
import java.io.File

/**
 * Composables and ViewModels never touch a data source (Firebase SDK, DataStore, Room, the data layer's own
 * implementations); only repositories do (ANDROID-BEST-PRACTICES follow-up 1, M1-50). The fixtures are the violating
 * and the clean files the rule is judged on.
 */
class NoDataSourceInUiTest {
    @TempDir
    lateinit var dir: File

    private fun violationsOf(
        code: String,
        path: String = "ui/Screen.kt",
    ): List<String> {
        val file = File(dir, path)
        file.parentFile.mkdirs()
        file.writeText("package sample\n\n$code\n")
        return DataSourceRules.dataSourceInUiViolations(dir)
    }

    private val composableWithFirestore =
        """
        import androidx.compose.runtime.Composable
        import com.google.firebase.firestore.FirebaseFirestore

        @Composable
        fun ListsScreen(db: FirebaseFirestore) {
            db.collection("lists")
        }
        """.trimIndent()

    private val viewModelWithFirestore =
        """
        import androidx.lifecycle.ViewModel
        import com.google.firebase.firestore.FirebaseFirestore

        class ListsViewModel(private val db: FirebaseFirestore) : ViewModel()
        """.trimIndent()

    // ---- the real sources ----

    @Test
    fun realUiSourcesTouchNoDataSource() {
        DataSourceRules
            .uiSourceDirs(File("../.."))
            .flatMap { DataSourceRules.dataSourceInUiViolations(it) }
            .shouldBeEmpty()
    }

    @Test
    fun scansTheRealUiSources() {
        check(DataSourceRules.uiSourceDirs(File("../..")).sumOf { ArchitectureRules.scannedFileCount(it) } > 0) {
            "scanned nothing"
        }
    }

    // ---- violating fixtures: composables ----

    @Test
    fun rejectsComposableThatImportsFirestore() {
        violationsOf(composableWithFirestore).single().shouldContain("ui/Screen.kt:4:")
    }

    @Test
    fun rejectsComposableThatImportsFirebaseAuth() {
        violationsOf(
            "import com.google.firebase.auth.FirebaseAuth\n\n@Composable\nfun Gate(auth: FirebaseAuth) {}",
        ).shouldNotBeEmpty()
    }

    @Test
    fun rejectsComposableThatUsesTheFirebaseEntryPoint() {
        violationsOf(
            "import com.google.firebase.Firebase\nimport com.google.firebase.firestore.firestore\n\n" +
                "@Composable\nfun Screen() {\n    Firebase.firestore\n}",
        ).shouldNotBeEmpty()
    }

    @Test
    fun rejectsComposableThatUsesAFullyQualifiedSdkName() {
        violationsOf("@Composable\nfun Screen() {\n    com.google.firebase.auth.FirebaseAuth.getInstance()\n}")
            .single()
            .shouldContain(":5:")
    }

    @Test
    fun rejectsWildcardAndAliasImports() {
        violationsOf("import com.google.firebase.firestore.*\n\n@Composable\nfun A() {}").shouldNotBeEmpty()
        violationsOf(
            "import com.google.firebase.auth.FirebaseAuth as Auth\n\n@Composable\nfun B() {}",
        ).shouldNotBeEmpty()
    }

    @Test
    fun rejectsComposableThatImportsDataStoreOrRoom() {
        violationsOf("import androidx.datastore.core.DataStore\n\n@Composable\nfun A() {}").shouldNotBeEmpty()
        violationsOf("import androidx.room.RoomDatabase\n\n@Composable\nfun B() {}").shouldNotBeEmpty()
    }

    @Test
    fun rejectsComposableThatImportsADataLayerImplementation() {
        violationsOf(
            "import dk.bjarkebjarke.tally.data.FirestoreListRepository\n\n" +
                "@Composable\nfun A(r: FirestoreListRepository) {}",
        ).shouldNotBeEmpty()
    }

    @Test
    fun rejectsComposableWithAQualifiedAnnotationOrModifiers() {
        violationsOf(
            "import com.google.firebase.firestore.FirebaseFirestore\n\n@androidx.compose.runtime.Composable\n" +
                "internal fun A(db: FirebaseFirestore) {}",
        ).shouldNotBeEmpty()
    }

    @Test
    fun rejectsComposableInTheSameFileAsPlainCode() {
        violationsOf(
            "import com.google.firebase.firestore.FirebaseFirestore\n\nclass Helper(val db: FirebaseFirestore)\n\n" +
                "@Composable\nfun Screen() {}",
        ).shouldNotBeEmpty()
    }

    // ---- violating fixtures: ViewModels ----

    @Test
    fun rejectsViewModelThatImportsFirestore() {
        violationsOf(viewModelWithFirestore, "ui/ListsViewModel.kt").single().shouldContain("ui/ListsViewModel.kt:4:")
    }

    @Test
    fun rejectsViewModelByItsSupertypeWhateverTheFileName() {
        violationsOf(viewModelWithFirestore, "ui/Anything.kt").shouldNotBeEmpty()
    }

    @Test
    fun rejectsViewModelByItsFileNameWhateverItsSupertype() {
        violationsOf(
            "import com.google.firebase.auth.FirebaseAuth\n\nclass AuthViewModel(val auth: FirebaseAuth)",
            "ui/AuthViewModel.kt",
        ).shouldNotBeEmpty()
    }

    @Test
    fun rejectsAndroidViewModelAndQualifiedSupertype() {
        violationsOf(
            "import com.google.firebase.firestore.FirebaseFirestore\n\n" +
                "class A(app: Application, val db: FirebaseFirestore) : AndroidViewModel(app)",
        ).shouldNotBeEmpty()
        violationsOf(
            "import com.google.firebase.firestore.FirebaseFirestore\n\n" +
                "class B(val db: FirebaseFirestore) : androidx.lifecycle.ViewModel()",
        ).shouldNotBeEmpty()
    }

    @Test
    fun rejectsViewModelWhoseSupertypeIsOnTheNextLine() {
        violationsOf(
            "import com.google.firebase.firestore.FirebaseFirestore\n\n" +
                "class A(\n    val db: FirebaseFirestore,\n) :\n    ViewModel()",
        ).shouldNotBeEmpty()
    }

    @Test
    fun rejectsViewModelThatImportsADataLayerImplementation() {
        violationsOf(
            "import dk.bjarkebjarke.tally.data.FirestoreListRepository\n\n" +
                "class A(val r: FirestoreListRepository) : ViewModel()",
        ).shouldNotBeEmpty()
    }

    @Test
    fun reportsEveryOffendingLine() {
        violationsOf(
            "import com.google.firebase.auth.FirebaseAuth\nimport com.google.firebase.firestore.FirebaseFirestore\n\n" +
                "class A : ViewModel()",
        ).size shouldBe 2
    }

    @Test
    fun scansNestedDirectories() {
        violationsOf(
            composableWithFirestore,
            "feature/lists/ui/Screen.kt",
        ).single().shouldContain("feature/lists/ui/Screen.kt")
    }

    // ---- clean fixtures ----

    @Test
    fun acceptsComposableAndViewModelThatUseADomainRepository() {
        violationsOf(
            "import dk.bjarkebjarke.tally.domain.ListRepository\n\n@Composable\nfun Screen(r: ListRepository) {}",
        ).shouldBeEmpty()
        violationsOf(
            "import dk.bjarkebjarke.tally.domain.ListRepository\n\n" +
                "class ListsViewModel(val r: ListRepository) : ViewModel()",
            "ui/ListsViewModel.kt",
        ).shouldBeEmpty()
    }

    @Test
    fun acceptsTheDataLayerImportingTheSdk() {
        violationsOf(
            "import com.google.firebase.firestore.FirebaseFirestore\n\n" +
                "class FirestoreListRepository(private val db: FirebaseFirestore)",
            "data/FirestoreListRepository.kt",
        ).shouldBeEmpty()
    }

    @Test
    fun acceptsPlainCodeThatIsNeitherComposableNorViewModel() {
        violationsOf(
            "import com.google.firebase.auth.FirebaseAuth\n\nobject Wiring { val a: Any = FirebaseAuth::class }",
        ).shouldBeEmpty()
    }

    @Test
    fun acceptsTypesThatOnlyLookLikeAViewModel() {
        violationsOf(
            "import com.google.firebase.auth.FirebaseAuth\n\nclass Owner(val a: FirebaseAuth) : ViewModelStoreOwner\n" +
                "class MyViewModelFactory(val a: FirebaseAuth)",
        ).shouldBeEmpty()
    }

    @Test
    fun acceptsSdkNamesInCommentsAndStrings() {
        violationsOf(
            "// never import com.google.firebase.auth.FirebaseAuth here\n" +
                "@Composable\nfun Screen() {\n    val s = \"androidx.room.Room and dk.bjarkebjarke.tally.data.X\"\n}",
        ).shouldBeEmpty()
    }

    @Test
    fun acceptsPackagesThatOnlyStartWithADataSourceName() {
        violationsOf(
            "import com.google.firebaseish.Thing\nimport androidx.roomy.Thing2\nimport androidx.datastorey.Thing3\n" +
                "import dk.bjarkebjarke.tally.database.Thing4\nimport dk.bjarkebjarke.tally.dataset.Thing5\n\n" +
                "@Composable\nfun Screen() {}",
        ).shouldBeEmpty()
    }

    @Test
    fun onlyTheOffendingUiFileIsReportedNextToACleanDataFile() {
        File(dir, "data").mkdirs()
        File(
            dir,
            "data/Repo.kt",
        ).writeText("package sample\n\nimport com.google.firebase.firestore.FirebaseFirestore\n")
        violationsOf(composableWithFirestore).single().shouldContain("ui/Screen.kt")
    }

    @Test
    fun aMissingDirectoryHasNoViolations() {
        DataSourceRules.dataSourceInUiViolations(File(dir, "missing")).shouldBeEmpty()
    }

    // ---- which directories the rule scans ----

    @Test
    fun scansTheMainSourcesOfEveryModuleButNotTestsOrBuildOutput() {
        listOf(
            "app/src/main",
            "app/src/test",
            "app/src/androidTest",
            "app/build/generated",
            "core/data/src/main",
            "core/data/src/test",
            "feature/lists/src/main",
            "src/main",
        ).forEach { File(dir, it).mkdirs() }
        DataSourceRules
            .uiSourceDirs(dir)
            .map { it.relativeTo(dir).path }
            .sorted() shouldBe listOf("app/src/main", "core/data/src/main", "feature/lists/src/main")
    }
}
