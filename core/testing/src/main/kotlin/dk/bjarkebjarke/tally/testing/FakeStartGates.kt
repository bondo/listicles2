package dk.bjarkebjarke.tally.testing

import dk.bjarkebjarke.tally.domain.start.EmailVerification
import dk.bjarkebjarke.tally.domain.start.HouseholdNotice
import dk.bjarkebjarke.tally.domain.start.HouseholdNotices
import dk.bjarkebjarke.tally.domain.start.NameState
import dk.bjarkebjarke.tally.domain.start.UpdateGate
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow

/** An [UpdateGate] the test drives (START-01); no update required until the test says so. */
class FakeUpdateGate : UpdateGate {
    private val state = MutableStateFlow(false)

    var required: Boolean
        get() = state.value
        set(value) {
            state.value = value
        }

    override fun updateRequired(): Flow<Boolean> = state
}

/** An [EmailVerification] the test drives (AUTH-06); verified until the test says otherwise. */
class FakeEmailVerification : EmailVerification {
    private val state = MutableStateFlow(true)

    var isVerified: Boolean
        get() = state.value
        set(value) {
            state.value = value
        }

    override fun verified(): Flow<Boolean> = state
}

/** A [NameState] the test drives (AUTH-12); a name is saved until the test says otherwise. */
class FakeNameState : NameState {
    private val state = MutableStateFlow(true)

    var isSaved: Boolean
        get() = state.value
        set(value) {
            state.value = value
        }

    override fun saved(): Flow<Boolean> = state
}

/** A [HouseholdNotices] the test drives (HH-06); no notice until the test sets one. */
class FakeHouseholdNotices : HouseholdNotices {
    private val state = MutableStateFlow<HouseholdNotice?>(null)

    var notice: HouseholdNotice?
        get() = state.value
        set(value) {
            state.value = value
        }

    override fun pending(): Flow<HouseholdNotice?> = state
}
