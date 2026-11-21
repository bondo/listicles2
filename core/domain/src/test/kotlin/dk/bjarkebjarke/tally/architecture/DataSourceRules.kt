package dk.bjarkebjarke.tally.architecture

import java.io.File

/** Stub: the rules arrive in the next commit, so the tests next to it fail first. */
object DataSourceRules {
    fun dataSourceInUiViolations(dir: File): List<String> =
        listOf<String>().also { check(dir.path.isNotEmpty()) }.take(0)

    fun globalScopeViolations(dir: File): List<String> = listOf<String>().also { check(dir.path.isNotEmpty()) }.take(0)

    fun uiSourceDirs(projectRoot: File): List<File> =
        listOf<File>().also { check(projectRoot.path.isNotEmpty()) }.take(0)

    fun allSourceDirs(projectRoot: File): List<File> =
        listOf<File>().also { check(projectRoot.path.isNotEmpty()) }.take(0)
}
