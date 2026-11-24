package dk.bjarkebjarke.tally

import io.kotest.matchers.collections.shouldBeEmpty
import io.kotest.matchers.shouldBe
import org.junit.jupiter.api.Test
import org.objectweb.asm.AnnotationVisitor
import org.objectweb.asm.ClassReader
import org.objectweb.asm.ClassVisitor
import org.objectweb.asm.Opcodes

/**
 * Owner decisions 7127528405 and 7129260438 (PR 381): coverage leaves out what Dagger generates (factories, their
 * nested instance holders, members injectors) and counts the hand-written classes below, so their uncovered lines
 * still count against the 80% gate. Judged on the app's compiled classes against app/build.gradle.kts's exclusions.
 */
class KoverExclusionsTest {
    private val configured =
        KoverFilters(
            mapOf(
                "excludes.classes" to configured("tally.koverExcludedClasses"),
                "excludes.annotatedBy" to configured("tally.koverExcludedAnnotations"),
            ),
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
            .filterNot { (set, value, name) -> KoverFilters(mapOf(set to value)).partlyLeftOut(name) }
            .shouldBeEmpty()
        // An annotation on a function leaves out that function, not its class.
        KoverFilters(mapOf("excludes.annotatedBy" to "dagger.Provides")).whollyLeftOut(GATE_MODULE) shouldBe false
    }

    private fun configured(key: String) = checkNotNull(System.getProperty(key)) { "$key is not set" }

    private companion object {
        const val GATE_MODULE = "dk.bjarkebjarke.tally.start.GateModule"
        const val SESSION_MODULE = "dk.bjarkebjarke.tally.session.SessionModule"
        const val STARTED_ACTIVITY = "dk.bjarkebjarke.tally.session.StartedActivity"
        const val START_VIEW_MODEL = "dk.bjarkebjarke.tally.start.StartViewModel"
        const val READY = "dk.bjarkebjarke.tally.start.StartUiState\$Ready"

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
            )
        val REACHING =
            listOf(
                Triple("excludes.annotatedBy", "dagger.hilt.*", SESSION_MODULE),
                Triple("excludes.annotatedBy", "javax.inject.*", STARTED_ACTIVITY),
                Triple("excludes.annotatedBy", "dagger.Provides", GATE_MODULE),
                Triple("excludes.annotatedBy", "javax.inject.Inj?ct", STARTED_ACTIVITY),
                Triple("excludes.inheritedFrom", "androidx.lifecycle.ViewModel", START_VIEW_MODEL),
                Triple("excludes.classes", "dk.bjarkebjarke.tally.*\$*", READY),
                Triple("excludes.projects", ":app", SESSION_MODULE),
                Triple("includes.classes", "dk.bjarkebjarke.tally.start.*", SESSION_MODULE),
            )
    }
}

/** Kover's report filters, as comma-separated patterns per set, such as "excludes.classes". */
private class KoverFilters(
    private val sets: Map<String, String>,
) {
    private fun values(set: String) = sets[set].orEmpty().split(',').filter(String::isNotEmpty)

    /** By its name, or by an annotation on the class itself (one on a function leaves out only that function). */
    fun whollyLeftOut(name: String): Boolean {
        val annotations = values("excludes.annotatedBy").map { "L${it.replace('.', '/')};" }
        return values("excludes.classes").map(::globRegex).any { it.matches(name) } ||
            classAnnotations(name).any { it in annotations }
    }

    fun partlyLeftOut(name: String) = whollyLeftOut(name)

    private fun classAnnotations(name: String): List<String> {
        val file = checkNotNull(javaClass.getResource("/" + name.replace('.', '/') + ".class")) { "no $name" }
        val onClass = mutableListOf<String>()
        val reader =
            object : ClassVisitor(Opcodes.ASM9) {
                override fun visitAnnotation(
                    descriptor: String,
                    visible: Boolean,
                ): AnnotationVisitor? {
                    onClass += descriptor
                    return null
                }
            }
        ClassReader(file.readBytes()).accept(reader, ClassReader.SKIP_CODE)
        return onClass
    }

    /** Kover's class patterns: `*` is any run of characters, `?` one character. */
    private fun globRegex(glob: String) =
        Regex(glob.split('*').joinToString(".*") { part -> part.split('?').joinToString(".") { Regex.escape(it) } })
}
