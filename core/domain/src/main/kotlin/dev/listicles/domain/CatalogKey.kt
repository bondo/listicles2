package dev.listicles.domain

import java.text.Normalizer
import java.util.Locale

/**
 * Key used to recognise "the same item" across lists, e.g. when packing templates
 * are combined. It is computed from the item name whenever it is needed and never
 * stored, so the rules below can evolve without migrating data.
 *
 * - Unicode NFC, so a decomposed "å" (a + U+030A) equals a composed "å".
 * - Invisible format/control characters (e.g. zero-width space U+200B) are removed.
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
        private val WHITESPACE = Regex("[\\p{Z}\\s\\u0085]+")

        // Format characters (zero-width space, joiners, BOM) and other non-whitespace controls.
        private val INVISIBLE = Regex("[\\p{Cf}&&[^\\s]]|[\\p{Cc}&&[^\\s\\u0085]]")

        fun of(name: String): CatalogKey {
            val folded =
                Normalizer
                    .normalize(name, Normalizer.Form.NFC)
                    .replace(INVISIBLE, "")
                    .replace(WHITESPACE, " ")
                    .trim()
                    .lowercase(Locale.ROOT)
            // Lowercasing can produce sequences that are no longer NFC, so normalise again.
            val normalized = Normalizer.normalize(folded, Normalizer.Form.NFC)
            require(normalized.isNotEmpty()) { "Item name must not be blank" }
            return CatalogKey(normalized)
        }
    }
}
