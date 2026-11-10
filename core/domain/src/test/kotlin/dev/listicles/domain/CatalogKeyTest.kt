package dev.listicles.domain

import io.kotest.assertions.throwables.shouldThrow
import io.kotest.core.spec.style.FunSpec
import io.kotest.matchers.shouldBe
import io.kotest.matchers.shouldNotBe
import io.kotest.matchers.string.shouldNotContain
import io.kotest.property.Arb
import io.kotest.property.arbitrary.Codepoint
import io.kotest.property.arbitrary.ascii
import io.kotest.property.arbitrary.choice
import io.kotest.property.arbitrary.element
import io.kotest.property.arbitrary.filter
import io.kotest.property.arbitrary.int
import io.kotest.property.arbitrary.list
import io.kotest.property.arbitrary.map
import io.kotest.property.arbitrary.string
import io.kotest.property.arbitrary.whitespace
import io.kotest.property.checkAll

// Fragments mixing ASCII, Danish letters, combining marks and exotic whitespace.
private val fragments =
    listOf(
        "a",
        "B",
        "z",
        "æ",
        "Ø",
        "å",
        "Å",
        "a\u030A",
        "e\u0301",
        "é",
        " ",
        "\t",
        "\u00A0",
        "\u202F",
        "\u2003",
        "\u200B",
        "\uFEFF",
        "\u0085",
        "\u00DF",
        "\u0130",
        "\u212B",
        "\n",
        "-",
        "1",
    )

private val names =
    Arb
        .choice(
            Arb.string(1..30, Codepoint.ascii()),
            Arb.string(1..30, Codepoint.whitespace()),
            // Latin, combining marks, Greek, Cyrillic, general punctuation (incl. zero-width chars): no surrogates.
            Arb.string(1..30, Arb.int(0x20..0x2FFF).map { Codepoint(it) }),
            Arb.list(Arb.element(fragments), 1..12).map { it.joinToString("") },
        ).filter { name -> name.any(::isVisible) }

// Independent of the implementation: a name is valid if it has at least one visible character.
private fun isVisible(c: Char): Boolean =
    !c.isWhitespace() &&
        !Character.isSpaceChar(c) &&
        Character.getType(c).toByte() !in setOf(Character.FORMAT, Character.CONTROL)

class CatalogKeyTest :
    FunSpec({
        test("ignores case and surrounding whitespace") {
            CatalogKey.of("  Sun Cream ") shouldBe CatalogKey.of("sun cream")
        }

        test("collapses inner whitespace of any kind") {
            CatalogKey.of("tooth \t  brush").value shouldBe "tooth brush"
            CatalogKey.of("tooth\u00A0\u00A0brush").value shouldBe "tooth brush"
            CatalogKey.of("tooth\u202Fbrush") shouldBe CatalogKey.of("tooth brush")
        }

        test("removes invisible characters such as zero-width space and BOM") {
            CatalogKey.of("sun\u200Bcream") shouldBe CatalogKey.of("suncream")
            CatalogKey.of("\uFEFFsocks").value shouldBe "socks"
            CatalogKey.of("tooth\u0085brush").value shouldBe "tooth brush"
        }

        test("composed and decomposed letters match") {
            CatalogKey.of("Ga\u030Afl") shouldBe CatalogKey.of("Gåfl")
            CatalogKey.of("Cafe\u0301") shouldBe CatalogKey.of("caf\u00E9")
            // Keys are in composed (NFC) form, so they equal text typed on a keyboard.
            CatalogKey.of("Ga\u030Afl").value shouldBe "g\u00E5fl"
        }

        test("keeps Danish letters distinct") {
            CatalogKey.of("Bær") shouldNotBe CatalogKey.of("Baer")
            CatalogKey.of("ÆBLE").value shouldBe "æble"
        }

        test("equal keys deduplicate in collections") {
            setOf(CatalogKey.of("Sun cream"), CatalogKey.of(" sun  CREAM")).size shouldBe 1
        }

        test("rejects blank names, including NBSP-only names") {
            shouldThrow<IllegalArgumentException> { CatalogKey.of(" \n ") }
            shouldThrow<IllegalArgumentException> { CatalogKey.of("\u00A0\u202F") }
            shouldThrow<IllegalArgumentException> { CatalogKey.of("\u200B\uFEFF") }
        }

        test("keys are always in NFC form") {
            checkAll(names) { name ->
                val key = CatalogKey.of(name).value
                java.text.Normalizer.isNormalized(key, java.text.Normalizer.Form.NFC) shouldBe true
            }
        }

        test("normalising is idempotent") {
            checkAll(names) { name ->
                val once = CatalogKey.of(name)
                CatalogKey.of(once.value) shouldBe once
            }
        }

        test("keys never contain leading, trailing or doubled whitespace") {
            checkAll(names) { name ->
                val key = CatalogKey.of(name).value
                key shouldBe key.trim()
                key shouldNotContain "  "
                Character.isSpaceChar(key.first()) shouldBe false
                Character.isSpaceChar(key.last()) shouldBe false
            }
        }
    })
