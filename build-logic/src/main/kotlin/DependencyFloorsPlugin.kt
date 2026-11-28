import org.gradle.api.Plugin
import org.gradle.api.Project
import java.io.StringReader
import java.util.Properties

/**
 * listicles.dependency.floors (issue 187, docs/SECURITY.md): in the project it is applied to, every configuration
 * raises a dependency that has a Dependabot advisory to the first fixed version in
 * gradle/patched-dependencies.properties. Only raises: a newer version that a plugin asks for still wins. The root
 * build applies it, and so does every convention plugin.
 */
class DependencyFloorsPlugin : Plugin<Project> {
    override fun apply(target: Project) {
        val file =
            target.isolated.rootProject.projectDirectory
                .file("gradle/patched-dependencies.properties")
        val text =
            target.providers
                .fileContents(file)
                .asText
                .get()
        val floors = Properties().apply { load(StringReader(text)) }
        target.configurations.configureEach {
            resolutionStrategy.eachDependency {
                val fixed = floors["${requested.group}:${requested.name}"] as String?
                val wanted = requested.version
                if (fixed != null && wanted != null && isOlder(wanted, fixed)) {
                    useVersion(fixed)
                    because("Dependabot alert: first fixed version is $fixed (docs/SECURITY.md)")
                }
            }
        }
    }
}

private fun versionParts(version: String): List<Int> =
    version.substringBefore('-').split('.').map { it.toIntOrNull() ?: 0 }

internal fun isOlder(
    version: String,
    fixed: String,
): Boolean {
    val a = versionParts(version)
    val b = versionParts(fixed)
    for (i in 0 until maxOf(a.size, b.size)) {
        val diff = a.getOrElse(i) { 0 } - b.getOrElse(i) { 0 }
        if (diff != 0) return diff < 0
    }
    return false
}
