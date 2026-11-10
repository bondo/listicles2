package dev.listicles.domain

import java.text.Normalizer
import java.util.Locale

/**
 * Key used to recognise "the same item" across lists, e.g. when packing templates
 * are combined. It is computed from the item name whenever it is needed and never
 * stored, so the rules below can evolve without migrating data.
 *
 * - Unicode NFC, so a decomposed "å" (a + U+030A) equals a composed "å".
 * - Leading/trailing and repeated whitespace of any Unicode kind (incl. NBSP) is collapsed.
 * - Case-insensitive via [Locale.ROOT].
 * - Letters such as æ, ø and å are kept, so "bær" and "baer" stay distinct.
 */
@ConsistentCopyVisibility
data class CatalogKey private constructor(
    val value: String,
) {
    companion object {
        // Any Unicode whitespace or separator, including NBSP (U+00A0) and NNBSP (U+202F).
        private val WHITESPACE = Regex("[\\p{Z}\\s]+")

        fun of(name: String): CatalogKey {
            val normalized =
                Normalizer
                    .normalize(name, Normalizer.Form.NFC)
                    .replace(WHITESPACE, " ")
                    .trim()
                    .lowercase(Locale.ROOT)
            require(normalized.isNotEmpty()) { "Item name must not be blank" }
            return CatalogKey(normalized)
        }
    }
}
