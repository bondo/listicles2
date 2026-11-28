package dk.bjarkebjarke.tally.domain.start

import kotlinx.coroutines.flow.Flow

/** START-01: whether this app version is too old to run. M1-27 implements it; until then nothing blocks the start. */
fun interface UpdateGate {
    fun updateRequired(): Flow<Boolean>
}

/** AUTH-06: whether the signed-in account's email is verified. M1-127 implements it. Asked while signed in. */
fun interface EmailVerification {
    fun verified(): Flow<Boolean>
}

/** AUTH-12: whether the user has a saved name (`users/{uid}.name`, P9). M1-39 implements it. Asked while signed in. */
fun interface NameState {
    fun saved(): Flow<Boolean>
}

/** HH-06: a self-heal notice not yet seen, `null` while there is none. M1-102 implements it. Asked while signed in. */
fun interface HouseholdNotices {
    fun pending(): Flow<HouseholdNotice?>
}

enum class HouseholdNotice { Removed, HouseholdDeleted }
