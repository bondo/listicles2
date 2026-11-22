package dk.bjarkebjarke.tally.start

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import dk.bjarkebjarke.tally.domain.session.SessionState
import dk.bjarkebjarke.tally.domain.start.EmailVerification
import dk.bjarkebjarke.tally.domain.start.HouseholdNotices
import dk.bjarkebjarke.tally.domain.start.NameState
import dk.bjarkebjarke.tally.domain.start.StartFacts
import dk.bjarkebjarke.tally.domain.start.StartStep
import dk.bjarkebjarke.tally.domain.start.UpdateGate
import dk.bjarkebjarke.tally.domain.start.startStep
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.catch
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.flatMapLatest
import kotlinx.coroutines.flow.flowOf
import kotlinx.coroutines.flow.stateIn
import javax.inject.Inject

/**
 * The start-up gates (P10, docs/milestones/M1.md section 8) as one state: [startStep] picks the first gate that stops
 * the start (update, sign-in, verified email, name, household notice) or the M1 home (Q1 A).
 */
@HiltViewModel
class StartViewModel
    @Inject
    constructor(
        update: UpdateGate,
        session: SessionState,
        email: EmailVerification,
        name: NameState,
        notices: HouseholdNotices,
    ) : ViewModel() {
        val uiState: StateFlow<StartUiState> =
            combine(
                update.updateRequired().orElse(false),
                laterGates(session, email, name, notices),
            ) { required, later ->
                StartUiState.Ready(startStep(later.copy(updateRequired = required)))
            }.stateIn(viewModelScope, SharingStarted.WhileSubscribed(STOP_TIMEOUT_MS), StartUiState.Loading)

        private companion object {
            const val STOP_TIMEOUT_MS = 5_000L
        }
    }

/**
 * A failing source ends its own flow with [fallback] (checklist section 4: errors become state), so the other sources
 * stay observed and the next signed-in start asks the source again. The fallback is the safe side of each gate: no
 * update is blocked, email and name count as missing (their step), a missing notice is dropped, a failing session is
 * signed out.
 */
private fun <T> Flow<T>.orElse(fallback: T): Flow<T> = catch { emit(fallback) }

/** The gates after the update gate. Signed out stops at sign-in without asking the later gates (no account yet). */
@OptIn(ExperimentalCoroutinesApi::class)
private fun laterGates(
    session: SessionState,
    email: EmailVerification,
    name: NameState,
    notices: HouseholdNotices,
): Flow<StartFacts> =
    session.signedIn().orElse(false).flatMapLatest { signedIn ->
        if (signedIn) {
            combine(
                email.verified().orElse(false),
                name.saved().orElse(false),
                notices.pending().orElse(null),
            ) { verified, saved, notice ->
                StartFacts(false, signedIn = true, emailVerified = verified, nameSaved = saved, notice = notice)
            }
        } else {
            flowOf(StartFacts(false, signedIn = false, emailVerified = true, nameSaved = true, notice = null))
        }
    }

sealed interface StartUiState {
    /** Not known yet whether anyone is signed in: the root shows its background only. */
    data object Loading : StartUiState

    data class Ready(
        val route: StartStep,
    ) : StartUiState
}
