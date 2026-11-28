package dk.bjarkebjarke.tally.account

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import dk.bjarkebjarke.tally.domain.account.AccountProfile
import dk.bjarkebjarke.tally.domain.account.AccountProfiles
import dk.bjarkebjarke.tally.domain.session.SignOut
import dk.bjarkebjarke.tally.domain.session.SignOutResult
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import javax.inject.Inject

/**
 * The Account screen's state (wireframe 18): who is signed in, and "Sign out" (AUTH-03)
 * with its question (wireframes 39 and 45). A finished sign-out needs no state here: the start gates leave the screen.
 */
@HiltViewModel
class AccountViewModel
    @Inject
    constructor(
        private val profiles: AccountProfiles,
        private val signOutSteps: SignOut,
    ) : ViewModel() {
        private val state = MutableStateFlow(AccountUiState(profiles.current()))
        val uiState: StateFlow<AccountUiState> = state.asStateFlow()

        /** The screen opened: the account that is signed in now (a view model outlives a sign-out in its activity). */
        fun opened() = state.update { it.copy(profile = profiles.current()) }

        fun signOut(): Unit = begin { signOutSteps() }

        /** "Sign out anyway": whatever was not sent yet is lost. */
        fun signOutAnyway(): Unit = begin { signOutSteps.discardingUnsentChanges() }

        fun cancelSignOut() = state.update { it.copy(question = null) }

        /** The screen has shown the failure message: it does not show it again. */
        fun failureShown() = state.update { it.copy(failed = false) }

        private fun begin(step: suspend () -> SignOutResult) {
            if (state.value.signingOut) return
            state.update { it.copy(signingOut = true, question = null, failed = false) }
            viewModelScope.launch {
                val result = step()
                state.update {
                    when (result) {
                        SignOutResult.SignedOut -> {
                            it.copy(signingOut = false)
                        }

                        SignOutResult.Failed -> {
                            it.copy(signingOut = false, failed = true)
                        }

                        is SignOutResult.ConfirmUnsentChanges -> {
                            it.copy(
                                signingOut = false,
                                question =
                                    if (result.unsentChangesSeen) {
                                        SignOutQuestion.NotSentYet
                                    } else {
                                        SignOutQuestion.MayNotBeSent
                                    },
                            )
                        }
                    }
                }
            }
        }
    }

data class AccountUiState(
    val profile: AccountProfile,
    /** Sign-out is running: "Sign out" waits. */
    val signingOut: Boolean = false,
    val question: SignOutQuestion? = null,
    /** The copy on the phone could not be deleted, so the user is still signed in. */
    val failed: Boolean = false,
)

/** Which text the "Sign out?" question uses: wireframe 39 when an unsent change is known, else wireframe 45. */
enum class SignOutQuestion { NotSentYet, MayNotBeSent }
