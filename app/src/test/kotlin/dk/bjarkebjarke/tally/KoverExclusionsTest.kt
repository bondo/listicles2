package dk.bjarkebjarke.tally

import io.kotest.matchers.collections.shouldBeEmpty
import org.junit.jupiter.api.Test
import org.objectweb.asm.AnnotationVisitor
import org.objectweb.asm.ClassReader
import org.objectweb.asm.ClassVisitor
import org.objectweb.asm.Opcodes

/**
 * Owner decision 7127528405 (PR 381): coverage leaves out what Dagger marks generated (its factories and members
 * injectors) and counts the hand-written classes below, so their uncovered lines still count against the 80% gate.
 * Judged on the app's compiled classes against app/build.gradle.kts's Kover exclusions; the root copy is not read.
 */
class KoverExclusionsTest {
    private val patterns = configured("tally.koverExcludedClasses").map(::globRegex)
    private val annotations = configured("tally.koverExcludedAnnotations").map { "L${it.replace('.', '/')};" }

    @Test
    fun daggersFactoriesAndMembersInjectorsAreLeftOut() {
        DAGGER_GENERATED.filterNot(::excluded).shouldBeEmpty()
    }

    @Test
    fun handWrittenClassesAreCounted() {
        HAND_WRITTEN.filter(::excluded).shouldBeEmpty()
    }

    /** By its name, or by an annotation on the class itself (one on a function leaves out only that function). */
    private fun excluded(name: String): Boolean {
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
        return patterns.any { it.matches(name) } || onClass.any { it in annotations }
    }

    private fun configured(key: String) = checkNotNull(System.getProperty(key)) { "$key is not set" }.split(',')

    /** Kover's class patterns: `*` is any run of characters, `?` one character. */
    private fun globRegex(glob: String) =
        Regex(glob.split('*').joinToString(".*") { part -> part.split('?').joinToString(".") { Regex.escape(it) } })

    private companion object {
        val DAGGER_GENERATED =
            listOf(
                "dk.bjarkebjarke.tally.MainActivity_MembersInjector",
                "dk.bjarkebjarke.tally.ApplicationScopeModule_ApplicationScopeFactory",
                "dk.bjarkebjarke.tally.session.SessionModule_GoogleCredentialsFactory",
                "dk.bjarkebjarke.tally.session.SignInAndSignOutModule_SignOutFactory",
                "dk.bjarkebjarke.tally.start.GateModule_UpdateGateFactory",
            )
        val HAND_WRITTEN =
            listOf(
                "dk.bjarkebjarke.tally.ApplicationScopeModule",
                "dk.bjarkebjarke.tally.session.SessionModule",
                "dk.bjarkebjarke.tally.session.SignInAndSignOutModule",
                "dk.bjarkebjarke.tally.session.StartedActivity",
                "dk.bjarkebjarke.tally.start.GateModule",
                "dk.bjarkebjarke.tally.start.StartViewModel",
            )
    }
}
