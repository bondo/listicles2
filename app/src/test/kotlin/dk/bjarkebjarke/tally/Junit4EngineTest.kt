package dk.bjarkebjarke.tally

import org.junit.Assert.assertEquals
import org.junit.Test

/** Fixture: a JUnit 4 test. It must appear in the results, or the JUnit 4 engine is missing (issue #212). */
class Junit4EngineTest {
    @Test
    fun junit4TestsRun() {
        assertEquals(4, 2 + 2)
    }
}
