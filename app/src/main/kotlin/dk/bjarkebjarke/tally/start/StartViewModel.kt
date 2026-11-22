package dk.bjarkebjarke.tally.start

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import dk.bjarkebjarke.tally.domain.session.SessionState
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.catch
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.flow.stateIn
import javax.inject.Inject

/**
 * The start-up gates (P10, docs/milestones/M1.md section 8) as one state: signed out opens sign-in, signed in opens
 * the M1 home (Q1 A). M1-62 adds the update, verified-email, name and household-notice gates in front of the home.
 */
@HiltViewModel
class StartViewModel
    @Inject
    constructor(
        session: SessionState,
    ) : ViewModel() {
        val uiState: StateFlow<StartUiState> =
            session
                .signedIn()
                .map { signedIn -> StartUiState.Ready(if (signedIn) StartRoute.Home else StartRoute.SignIn) }
                // Checklist section 4: a failing session source opens sign-in instead of crashing at start.
                .catch { emit(StartUiState.Ready(StartRoute.SignIn)) }
                .stateIn(viewModelScope, SharingStarted.WhileSubscribed(STOP_TIMEOUT_MS), StartUiState.Loading)

        private companion object {
            const val STOP_TIMEOUT_MS = 5_000L
        }
    }

sealed interface StartUiState {
    /** Not known yet whether anyone is signed in: the root shows its background only. */
    data object Loading : StartUiState

    data class Ready(
        val route: StartRoute,
    ) : StartUiState
}

/** The root's Navigation 3 keys. The back stack is derived from the gate state at every start, so it is not saved. */
sealed interface StartRoute {
    data object SignIn : StartRoute

    data object Home : StartRoute
}
