package dk.bjarkebjarke.tally.signin

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import dk.bjarkebjarke.tally.domain.session.GoogleSignIn
import dk.bjarkebjarke.tally.domain.session.GoogleSignInResult
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import javax.inject.Inject

/**
 * The sign-in screen's state (AUTH-01): "Continue with Google" runs [GoogleSignIn] and leaves a [SignInMessage] for the
 * outcomes the user must hear about. A signed-in session needs no state here: the start gates leave sign-in (AUTH-02).
 */
@HiltViewModel
class SignInViewModel
    @Inject
    constructor(
        private val googleSignIn: GoogleSignIn,
    ) : ViewModel() {
        private val state = MutableStateFlow(SignInUiState())
        val uiState: StateFlow<SignInUiState> = state.asStateFlow()

        fun continueWithGoogle() {
            if (state.value.busy) return
            state.value = SignInUiState(busy = true)
            viewModelScope.launch {
                val message =
                    when (googleSignIn()) {
                        GoogleSignInResult.NeedsConnection -> SignInMessage.NeedsConnection
                        GoogleSignInResult.NoAccount -> SignInMessage.NoAccount
                        GoogleSignInResult.EmailHasPasswordAccount -> SignInMessage.EmailHasPasswordAccount
                        GoogleSignInResult.Failed -> SignInMessage.Failed
                        GoogleSignInResult.SignedIn, GoogleSignInResult.Cancelled -> null
                    }
                state.value = SignInUiState(message = message)
            }
        }

        /** The screen has shown the message: it does not show it again. */
        fun messageShown() = state.update { it.copy(message = null) }
    }

data class SignInUiState(
    /** The picker or Firebase is working: the Google button waits. */
    val busy: Boolean = false,
    val message: SignInMessage? = null,
)

/**
 * What the user hears after "Continue with Google"; a closed picker (AUTH-01) has none. [EmailHasPasswordAccount]: the
 * non-Gmail collision (M1.md docs check 3, wireframe 44).
 */
enum class SignInMessage { NeedsConnection, NoAccount, EmailHasPasswordAccount, Failed }
