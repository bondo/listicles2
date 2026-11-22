package dk.bjarkebjarke.tally.start

import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.components.SingletonComponent
import dk.bjarkebjarke.tally.domain.start.EmailVerification
import dk.bjarkebjarke.tally.domain.start.HouseholdNotices
import dk.bjarkebjarke.tally.domain.start.NameState
import dk.bjarkebjarke.tally.domain.start.UpdateGate
import kotlinx.coroutines.flow.flowOf

/**
 * Stand-in bindings for the start-up gates (P10) until their tasks implement them: no update is required, the email is
 * verified, the name is saved and there is no notice, so every gate passes. Each task replaces its own provider:
 * update M1-27, email verified M1-15, name M1-39, notices M1-18.
 */
@Module
@InstallIn(SingletonComponent::class)
object GateModule {
    @Provides
    fun updateGate(): UpdateGate = UpdateGate { flowOf(false) }

    @Provides
    fun emailVerification(): EmailVerification = EmailVerification { flowOf(true) }

    @Provides
    fun nameState(): NameState = NameState { flowOf(true) }

    @Provides
    fun householdNotices(): HouseholdNotices = HouseholdNotices { flowOf(null) }
}
