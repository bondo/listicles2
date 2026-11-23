package dk.bjarkebjarke.tally.appcheck

import com.google.firebase.appcheck.AppCheckProviderFactory
import com.google.firebase.appcheck.playintegrity.PlayIntegrityAppCheckProviderFactory
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.components.SingletonComponent

/** M1-26 (R5): release builds attest with Play Integrity. Enforcement is off in the console until M1-O4. */
@Module
@InstallIn(SingletonComponent::class)
object AppCheckFactoryModule {
    @Provides
    fun factory(): AppCheckProviderFactory = PlayIntegrityAppCheckProviderFactory.getInstance()
}
