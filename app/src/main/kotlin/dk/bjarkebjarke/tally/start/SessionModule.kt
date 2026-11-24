package dk.bjarkebjarke.tally.start

import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.components.SingletonComponent
import dk.bjarkebjarke.tally.domain.session.SessionState
import kotlinx.coroutines.flow.flowOf

/** Stand-in until M1-88 binds the Firebase Auth session: nobody is signed in, so the app opens on sign-in. */
@Module
@InstallIn(SingletonComponent::class)
object SessionModule {
    @Provides
    fun sessionState(): SessionState = SessionState { flowOf(false) }
}
