package dk.bjarkebjarke.tally

import io.kotest.assertions.throwables.shouldThrow
import io.kotest.matchers.collections.shouldBeEmpty
import io.kotest.matchers.shouldBe
import org.junit.jupiter.api.Test
import org.objectweb.asm.AnnotationVisitor
import org.objectweb.asm.ClassReader
import org.objectweb.asm.ClassVisitor
import org.objectweb.asm.MethodVisitor
import org.objectweb.asm.Opcodes

/**
 * Owner decisions 7127528405 and 7129260438 (PR 381): coverage leaves out what Dagger generates (factories, their
 * nested instance holders, members injectors) and counts the hand-written classes below, so their uncovered lines
 * still count against the 80% gate. Judged on the app's compiled classes against every filter of app/build.gradle.kts's
 * total report, the one koverVerify checks (the root copy is not read; follow-up #386).
 */
class KoverExclusionsTest {
    private val configured =
        KoverFilters(
            KoverFilters.SETS.associateWith { configured("tally.kover.$it").split(',').filter(String::isNotEmpty) },
        )

    @Test
    fun whatDaggerGeneratesIsLeftOut() {
        DAGGER_GENERATED.filterNot(configured::whollyLeftOut).shouldBeEmpty()
    }

    @Test
    fun handWrittenClassesAreCounted() {
        HAND_WRITTEN.filter(configured::partlyLeftOut).shouldBeEmpty()
    }

    /**
     * R1-01 and S1-01: each filter leaves out code of its hand-written class in Kover 0.9.11 (`*` and `?` in every
     * name, annotations on functions and constructors too, supertypes; its KoverReportFilter KDoc), or is a set this
     * test does not judge, so the hand-written case must count it.
     */
    @Test
    fun aFilterThatReachesHandWrittenCodeCounts() {
        REACHING
            .filterNot { (set, value, name) -> filter(set, value).partlyLeftOut(name) }
            .shouldBeEmpty()
        // An annotation on a function leaves out that function, not its class.
        filter("excludes.annotatedBy", "dagger.Provides").whollyLeftOut(GATE_MODULE) shouldBe false
        // A listed class that is gone fails, whatever the patterns.
        shouldThrow<IllegalStateException> { filter("excludes.classes", "*").whollyLeftOut(GONE) }
    }

    private fun configured(key: String) = checkNotNull(System.getProperty(key)) { "$key is not set" }

    private fun filter(
        set: String,
        value: String,
    ) = KoverFilters(mapOf(set to listOf(value)))

    private companion object {
        const val GATE_MODULE = "dk.bjarkebjarke.tally.start.GateModule"
        const val SESSION_MODULE = "dk.bjarkebjarke.tally.session.SessionModule"
        const val STARTED_ACTIVITY = "dk.bjarkebjarke.tally.session.StartedActivity"
        const val START_VIEW_MODEL = "dk.bjarkebjarke.tally.start.StartViewModel"
        const val READY = "dk.bjarkebjarke.tally.start.StartUiState\$Ready"
        const val START_FUNCTIONS = "dk.bjarkebjarke.tally.start.StartViewModelKt"
        const val GONE = "dk.bjarkebjarke.tally.start.GoneFactory\$InstanceHolder"

        val DAGGER_GENERATED =
            listOf(
                "dk.bjarkebjarke.tally.MainActivity_MembersInjector",
                "dk.bjarkebjarke.tally.ApplicationScopeModule_ApplicationScopeFactory",
                "dk.bjarkebjarke.tally.session.SessionModule_GoogleCredentialsFactory",
                "dk.bjarkebjarke.tally.session.SessionModule_FirebaseAuthenticationFactory\$InstanceHolder",
                "dk.bjarkebjarke.tally.session.SignInAndSignOutModule_SignOutFactory",
                "dk.bjarkebjarke.tally.start.GateModule_UpdateGateFactory",
            )
        val HAND_WRITTEN =
            listOf(
                "dk.bjarkebjarke.tally.ApplicationScopeModule",
                SESSION_MODULE,
                "dk.bjarkebjarke.tally.session.SignInAndSignOutModule",
                STARTED_ACTIVITY,
                GATE_MODULE,
                START_VIEW_MODEL,
                READY,
                START_FUNCTIONS,
            )
        val REACHING =
            listOf(
                Triple("excludes.annotatedBy", "dagger.hilt.*", SESSION_MODULE),
                Triple("excludes.annotatedBy", "javax.inject.*", STARTED_ACTIVITY),
                Triple("excludes.annotatedBy", "dagger.Provides", GATE_MODULE),
                Triple("excludes.annotatedBy", "javax.inject.Inj?ct", STARTED_ACTIVITY),
                Triple("excludes.inheritedFrom", "androidx.lifecycle.ViewModel", START_VIEW_MODEL),
                Triple("excludes.classes", "dk.bjarkebjarke.tally.*\$*", READY),
                // Lambdas Kotlin compiles to classes of their own: StartViewModel$uiState$1, StartViewModelKt$orElse$1.
                Triple("excludes.inheritedFrom", "kotlin.coroutines.jvm.internal.SuspendLambda", START_VIEW_MODEL),
                Triple("excludes.annotatedBy", "kotlin.coroutines.jvm.internal.DebugMetadata", START_VIEW_MODEL),
                Triple("excludes.classes", "*\$*\$*", START_FUNCTIONS),
                Triple("excludes.projects", ":app", SESSION_MODULE),
                Triple("includes.classes", "dk.bjarkebjarke.tally.start.*", SESSION_MODULE),
                Triple("includes.classes", "", SESSION_MODULE),
            )
    }
}

/**
 * Kover's report filters, as comma-separated `*` and `?` patterns per set, such as "excludes.classes". Kover 0.9.11
 * leaves out a class by its name, by an annotation on it or by a supertype at any depth (not the class itself), and a
 * function or constructor by an annotation on it (KoverReportFilter's KDoc).
 */
private class KoverFilters(
    private val sets: Map<String, List<String>>,
) {
    private fun matches(
        set: String,
        names: List<String>,
    ) = sets[set].orEmpty().any { glob -> names.any(globRegex(glob)::matches) }

    /** All of it: by its name, or by an annotation on the class itself. */
    fun whollyLeftOut(name: String) =
        matches("excludes.classes", listOf(name)) || matches("excludes.annotatedBy", annotations(name).first)

    /**
     * Any of its code, by an annotation on one of its functions or by a supertype too. Fails closed: a set this does
     * not judge (includes, which leave out what they do not name, and projects) counts as leaving out every class.
     */
    fun partlyLeftOut(name: String) =
        UNJUDGED.any { sets[it].orEmpty().isNotEmpty() } ||
            whollyLeftOut(name) ||
            matches("excludes.annotatedBy", annotations(name).second) ||
            matches("excludes.inheritedFrom", supertypes(Class.forName(name, false, javaClass.classLoader)))

    private fun supertypes(type: Class<*>): List<String> =
        (listOfNotNull(type.superclass) + type.interfaces).flatMap { listOf(it.name) + supertypes(it) }

    /** The annotations on the class and on its functions and constructors, named as Kover names them. */
    private fun annotations(className: String): Pair<List<String>, List<String>> {
        val file = checkNotNull(javaClass.getResource("/" + className.replace('.', '/') + ".class")) { "no $className" }
        val onClass = mutableListOf<String>()
        val onFunctions = mutableListOf<String>()

        fun MutableList<String>.record(descriptor: String): AnnotationVisitor? {
            add(descriptor.substring(1, descriptor.length - 1).replace('/', '.'))
            return null
        }
        val functions =
            object : MethodVisitor(Opcodes.ASM9) {
                override fun visitAnnotation(
                    descriptor: String,
                    visible: Boolean,
                ) = onFunctions.record(descriptor)
            }
        val reader =
            object : ClassVisitor(Opcodes.ASM9) {
                override fun visitAnnotation(
                    descriptor: String,
                    visible: Boolean,
                ) = onClass.record(descriptor)

                override fun visitMethod(
                    access: Int,
                    name: String?,
                    descriptor: String?,
                    signature: String?,
                    exceptions: Array<out String>?,
                ) = functions
            }
        ClassReader(file.readBytes()).accept(reader, ClassReader.SKIP_CODE)
        return onClass to onFunctions
    }

    /** `*` is any run of characters, `?` one character. */
    private fun globRegex(glob: String) =
        Regex(glob.split('*').joinToString(".*") { part -> part.split('?').joinToString(".") { Regex.escape(it) } })

    companion object {
        /** Every set of Kover's filters; app/build.gradle.kts passes each to the test. */
        val SETS =
            listOf("excludes", "includes").flatMap { kind ->
                listOf("classes", "annotatedBy", "inheritedFrom", "projects").map { "$kind.$it" }
            }
        val UNJUDGED = SETS.filter { it.startsWith("includes.") } + "excludes.projects"
    }
}
