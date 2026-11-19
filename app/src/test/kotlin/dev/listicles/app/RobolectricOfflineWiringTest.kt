package dev.listicles.app

import dev.listicles.testing.NetworkAccessBlockedException
import io.kotest.assertions.throwables.shouldThrow
import io.kotest.matchers.collections.shouldNotBeEmpty
import io.kotest.matchers.shouldBe
import io.kotest.matchers.string.shouldContain
import io.kotest.matchers.types.shouldNotBeInstanceOf
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.io.TempDir
import org.robolectric.internal.dependency.DependencyJar
import org.robolectric.plugins.LegacyDependencyResolver
import java.io.File
import java.util.Properties

/**
 * Issue 213: Robolectric resolves its android-all jars from a directory that Gradle fills (so the jars are covered
 * by gradle/verification-metadata.xml), and never downloads at test runtime (the test JVM blocks the network).
 * The end-to-end proof is RobolectricUnderNetworkBlockTest; these tests pin the wiring and its failure mode.
 */
class RobolectricOfflineWiringTest {
    private val prefix = "android-all-instrumented-"

    private fun offlineResolver(dir: File) =
        LegacyDependencyResolver(
            Properties().apply {
                setProperty("robolectric.offline", "true")
                setProperty("robolectric.dependency.dir", dir.path)
            },
        )

    private fun dependency(version: String) = DependencyJar("org.robolectric", "android-all-instrumented", version)

    private fun configuredDir(): File {
        System.getProperty("robolectric.offline") shouldBe "true"
        return File(
            requireNotNull(System.getProperty("robolectric.dependency.dir")) {
                "robolectric.dependency.dir is not set"
            },
        )
    }

    private fun versionsIn(dir: File) =
        dir
            .listFiles { f -> f.name.startsWith(prefix) && f.name.endsWith(".jar") }
            .orEmpty()
            .map { it.name.removePrefix(prefix).removeSuffix(".jar") }

    @Test
    fun theTestJvmRunsRobolectricOffline() {
        configuredDir().isDirectory shouldBe true
    }

    @Test
    fun everyAndroidAllJarGradleResolvedIsFoundByRobolectric() {
        val dir = configuredDir()
        val versions = versionsIn(dir)
        versions.shouldNotBeEmpty()
        versions.forEach {
            offlineResolver(
                dir,
            ).getLocalArtifactUrl(dependency(it)).path shouldContain "$prefix$it.jar"
        }
    }

    @Test
    fun aMissingJarFailsInsteadOfDownloading(
        @TempDir empty: File,
    ) {
        val failure =
            shouldThrow<IllegalArgumentException> {
                offlineResolver(
                    empty,
                ).getLocalArtifactUrl(dependency("15-robolectric-1-i7"))
            }
        failure.message shouldContain "${prefix}15-robolectric-1-i7.jar"
        failure.shouldNotBeInstanceOf<NetworkAccessBlockedException>()
    }

    @Test
    fun aMissingDirectoryFailsInsteadOfDownloading(
        @TempDir parent: File,
    ) {
        val failure =
            shouldThrow<IllegalArgumentException> {
                offlineResolver(File(parent, "absent")).getLocalArtifactUrl(dependency("15-robolectric-1-i7"))
            }
        failure.message shouldContain "${prefix}15-robolectric-1-i7.jar"
    }
}
