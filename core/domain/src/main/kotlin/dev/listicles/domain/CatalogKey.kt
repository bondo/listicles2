package dev.listicles.domain

import java.util.Locale

/**
 * Stable key used to recognise "the same item" across lists, e.g. when packing
 * templates are combined. Case and surrounding/duplicate whitespace are ignored;
 * letters such as æ, ø and å are kept as-is so Danish words stay distinct.
 */
@ConsistentCopyVisibility
data class CatalogKey private constructor(
    val value: String,
) {
    companion object {
        private val WHITESPACE = Regex("\\s+")

        fun of(name: String): CatalogKey {
            val normalized = name.trim().replace(WHITESPACE, " ").lowercase(Locale.ROOT)
            require(normalized.isNotEmpty()) { "Item name must not be blank" }
            return CatalogKey(normalized)
        }
    }
}
