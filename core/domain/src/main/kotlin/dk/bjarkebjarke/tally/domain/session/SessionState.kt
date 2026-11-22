package dk.bjarkebjarke.tally.domain.session

import kotlinx.coroutines.flow.Flow

/**
 * Whether someone is signed in on this phone (AUTH-02; signed in stays signed in offline). The start-up root routes on
 * it (M1-60, P10); M1-14 implements it with Firebase Auth.
 */
fun interface SessionState {
    fun signedIn(): Flow<Boolean>
}
