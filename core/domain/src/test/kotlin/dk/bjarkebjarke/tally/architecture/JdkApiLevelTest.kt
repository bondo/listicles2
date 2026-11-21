package dk.bjarkebjarke.tally.architecture

import io.kotest.matchers.shouldBe
import io.kotest.matchers.string.shouldContain
import io.kotest.matchers.string.shouldNotContain
import org.junit.jupiter.api.Test
import java.io.ByteArrayOutputStream
import java.io.PrintWriter
import java.util.spi.ToolProvider

/**
 * Issue 211: JVM modules must compile against the JDK 17 API, not the JDK 21 one the build runs on. Android has
 * `java.util.List.removeFirst()` and friends only from API 35, while minSdk is 26, so a call that compiles to the
 * JDK 21 member crashes with NoSuchMethodError on Android 8 to 14. This test compiles (as part of the test source
 * set, so with the same compiler options as the module) a probe that makes those calls, then reads the bytecode:
 * with `-Xjdk-release=17` Kotlin resolves `removeFirst()` and `removeLast()` to its own stdlib extensions. The
 * `reversed()` probe is a positive control only: Kotlin resolves it to the stdlib with or without the setting.
 */
class JdkApiLevelTest {
    private fun bytecodeOf(type: Class<*>): String {
        val path =
            type.protectionDomain.codeSource.location
                .toURI()
                .let { java.io.File(it) }
        val javap = ToolProvider.findFirst("javap").orElseThrow { IllegalStateException("javap is not available") }
        val out = ByteArrayOutputStream()
        val writer = PrintWriter(out, true)
        val code = javap.run(writer, writer, "-c", "-p", "-cp", path.path, type.name)
        writer.flush()
        code shouldBe 0
        return out.toString()
    }

    private val jdk21OnlyMembers =
        listOf(
            "java/util/List.removeFirst",
            "java/util/List.removeLast",
            "java/util/List.reversed",
        )

    @Test
    fun theProbeCallsTheKotlinStdlibNotTheJdk21ListMembers() {
        val code = bytecodeOf(JdkApiProbe::class.java)
        // Not vacuous: the probe really makes the calls, and they resolve to the stdlib extensions.
        code shouldContain "kotlin/collections/CollectionsKt.removeFirst"
        code shouldContain "kotlin/collections/CollectionsKt.removeLast"
        code shouldContain "kotlin/collections/CollectionsKt.reversed"
        jdk21OnlyMembers.forEach { code shouldNotContain it }
    }

    @Test
    fun theProbeKeepsItsBehaviour() {
        val items = mutableListOf(1, 2, 3)
        JdkApiProbe.takeFirst(items) shouldBe 1
        JdkApiProbe.takeLast(items) shouldBe 3
        items shouldBe listOf(2)
        JdkApiProbe.backwards(listOf(1, 2, 3)) shouldBe listOf(3, 2, 1)
    }
}

/** Idiomatic Kotlin that resolves to JDK 21 members when the module compiles against the JDK 21 class library. */
object JdkApiProbe {
    fun takeFirst(items: MutableList<Int>): Int = items.removeFirst()

    fun takeLast(items: MutableList<Int>): Int = items.removeLast()

    fun backwards(items: List<Int>): List<Int> = items.toMutableList().reversed()
}
