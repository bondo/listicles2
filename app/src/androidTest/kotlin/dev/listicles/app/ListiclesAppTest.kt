package dev.listicles.app

import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithText
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class ListiclesAppTest {
    @get:Rule
    val compose = createComposeRule()

    @Test
    fun showsWelcomeText() {
        val welcome = InstrumentationRegistry.getInstrumentation().targetContext.getString(R.string.welcome)
        compose.setContent { ListiclesApp() }
        compose.onNodeWithText(welcome).assertExists()
    }
}
