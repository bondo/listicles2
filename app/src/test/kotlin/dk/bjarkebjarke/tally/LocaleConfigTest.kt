package dk.bjarkebjarke.tally

import io.kotest.matchers.collections.shouldContainExactlyInAnyOrder
import io.kotest.matchers.shouldBe
import io.kotest.matchers.shouldNotBe
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.xmlpull.v1.XmlPullParser

/**
 * M1-24 (LANG-02): the app declares exactly its two languages, English and Danish, through the AGP-generated
 * locale config (`generateLocaleConfig`), so the Android 13+ per-app language picker offers just those.
 * Android 8-12 follow the phone; there is no in-app picker (decision 6, OQ-12).
 */
@RunWith(RobolectricTestRunner::class)
class LocaleConfigTest {
    private fun generatedLocales(): List<String> {
        val app = RuntimeEnvironment.getApplication()
        val id = app.resources.getIdentifier("_generated_res_locale_config", "xml", app.packageName)
        id shouldNotBe 0
        val parser = app.resources.getXml(id)
        val tags = mutableListOf<String>()
        var event = parser.eventType
        while (event != XmlPullParser.END_DOCUMENT) {
            if (event == XmlPullParser.START_TAG && parser.name == "locale") {
                tags += parser.getAttributeValue("http://schemas.android.com/apk/res/android", "name")
            }
            event = parser.next()
        }
        return tags
    }

    @Test
    fun generatedLocaleConfigHoldsExactlyEnglishAndDanish() {
        generatedLocales() shouldContainExactlyInAnyOrder listOf("en", "da")
    }

    @Test
    fun noOtherLanguageIsOffered() {
        val locales = generatedLocales()
        listOf("sv", "nb", "de", "en-US", "und").forEach { (it in locales) shouldBe false }
    }
}
