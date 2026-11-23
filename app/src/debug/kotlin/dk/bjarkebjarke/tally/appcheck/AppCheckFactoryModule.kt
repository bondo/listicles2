package dk.bjarkebjarke.tally.appcheck

import com.google.firebase.appcheck.AppCheckProviderFactory
import com.google.firebase.appcheck.debug.DebugAppCheckProviderFactory
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.components.SingletonComponent

/**
 * M1-26 (R5): debug builds use the debug provider. It logs a debug secret to logcat on first use; the owner registers
 * that for their own devices in the console. Nothing is stored in the repo, and CI uses the emulators.
 */
@Module
@InstallIn(SingletonComponent::class)
object AppCheckFactoryModule {
    @Provides
    fun factory(): AppCheckProviderFactory = DebugAppCheckProviderFactory.getInstance()
}
