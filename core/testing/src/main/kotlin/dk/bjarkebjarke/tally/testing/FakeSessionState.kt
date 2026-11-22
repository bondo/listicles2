package dk.bjarkebjarke.tally.testing

import dk.bjarkebjarke.tally.domain.session.SessionState
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.filterNotNull

/** A [SessionState] the test drives (AUTH-02): `null` until the test says whether someone is signed in. */
class FakeSessionState(
    signedIn: Boolean? = null,
) : SessionState {
    private val state = MutableStateFlow(signedIn)

    var signedIn: Boolean?
        get() = state.value
        set(value) {
            state.value = value
        }

    override fun signedIn(): Flow<Boolean> = state.filterNotNull()
}
