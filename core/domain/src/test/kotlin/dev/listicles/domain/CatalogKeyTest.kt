package dev.listicles.domain

import io.kotest.assertions.throwables.shouldThrow
import io.kotest.core.spec.style.FunSpec
import io.kotest.matchers.shouldBe
import io.kotest.matchers.shouldNotBe
import io.kotest.property.Arb
import io.kotest.property.arbitrary.filter
import io.kotest.property.arbitrary.string
import io.kotest.property.checkAll

class CatalogKeyTest :
    FunSpec({
        test("ignores case and surrounding whitespace") {
            CatalogKey.of("  Sun Cream ") shouldBe CatalogKey.of("sun cream")
        }

        test("collapses inner whitespace") {
            CatalogKey.of("tooth \t  brush").value shouldBe "tooth brush"
        }

        test("keeps Danish letters distinct") {
            CatalogKey.of("Bær") shouldNotBe CatalogKey.of("Baer")
            CatalogKey.of("ÆBLE").value shouldBe "æble"
        }

        test("equal keys deduplicate in collections") {
            setOf(CatalogKey.of("Sun cream"), CatalogKey.of(" sun  CREAM")).size shouldBe 1
        }

        test("rejects blank names") {
            shouldThrow<IllegalArgumentException> { CatalogKey.of(" \n ") }
        }

        test("normalising is idempotent") {
            checkAll(Arb.string(1..40).filter { it.isNotBlank() }) { name ->
                val once = CatalogKey.of(name)
                CatalogKey.of(once.value) shouldBe once
            }
        }
    })
