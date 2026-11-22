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
            combine(update.updateRequired(), laterGates(session, email, name, notices)) { updateRequired, later ->
                StartUiState.Ready(startStep(later.copy(updateRequired = updateRequired)))
            }
                // Checklist section 4: a failing gate source opens sign-in instead of crashing at start.
                .catch<StartUiState> { emit(StartUiState.Ready(StartStep.SignIn)) }
                .stateIn(viewModelScope, SharingStarted.WhileSubscribed(STOP_TIMEOUT_MS), StartUiState.Loading)

        private companion object {
            const val STOP_TIMEOUT_MS = 5_000L
        }
    }

/** The gates after the update gate. Signed out stops at sign-in without asking the later gates (no account yet). */
@OptIn(ExperimentalCoroutinesApi::class)
private fun laterGates(
    session: SessionState,
    email: EmailVerification,
    name: NameState,
    notices: HouseholdNotices,
): Flow<StartFacts> =
    session.signedIn().flatMapLatest { signedIn ->
        if (signedIn) {
            combine(email.verified(), name.saved(), notices.pending()) { verified, saved, notice ->
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
