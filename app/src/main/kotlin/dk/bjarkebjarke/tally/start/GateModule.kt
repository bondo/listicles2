package dk.bjarkebjarke.tally.start

import android.content.Context
import androidx.core.content.pm.PackageInfoCompat
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.android.qualifiers.ApplicationContext
import dagger.hilt.components.SingletonComponent
import dk.bjarkebjarke.tally.data.config.FirestoreMinVersionRemote
import dk.bjarkebjarke.tally.data.session.FirestoreSession
import dk.bjarkebjarke.tally.domain.config.MinVersionGate
import dk.bjarkebjarke.tally.domain.config.MinVersionRemote
import dk.bjarkebjarke.tally.domain.config.MinVersionStore
import dk.bjarkebjarke.tally.domain.start.EmailVerification
import dk.bjarkebjarke.tally.domain.start.HouseholdNotices
import dk.bjarkebjarke.tally.domain.start.NameState
import dk.bjarkebjarke.tally.domain.start.UpdateGate
import dk.bjarkebjarke.tally.update.PreferencesMinVersionStore
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.flowOf

/**
 * Stand-in bindings for the start-up gates (P10) until their tasks implement them: no update is required, the email is
 * verified, the name is saved and there is no notice, so every gate passes. Each task replaces its own provider:
 * update M1-27 and M1-82 (done), email verified M1-127, name M1-39, notices M1-102.
 */
@Module
@InstallIn(SingletonComponent::class)
object GateModule {
    /** M1-82: the gate reads `config/app.minVersionCode` through the app's one [FirestoreSession], signed out. */
    @Provides
    fun minVersionRemote(session: FirestoreSession): MinVersionRemote = FirestoreMinVersionRemote(session)

    @Provides
    fun minVersionStore(
        @ApplicationContext context: Context,
    ): MinVersionStore = PreferencesMinVersionStore(context, Dispatchers.IO)

    @Provides
    fun updateGate(
        @ApplicationContext context: Context,
        remote: MinVersionRemote,
        store: MinVersionStore,
    ): UpdateGate {
        val installed =
            PackageInfoCompat.getLongVersionCode(
                context.packageManager.getPackageInfo(context.packageName, 0),
            )
        return MinVersionGate(remote, store, installed)
    }

    @Provides
    fun emailVerification(): EmailVerification = EmailVerification { flowOf(true) }

    @Provides
    fun nameState(): NameState = NameState { flowOf(true) }

    @Provides
    fun householdNotices(): HouseholdNotices = HouseholdNotices { flowOf(null) }
}
