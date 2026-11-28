package dk.bjarkebjarke.tally.account

import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.components.SingletonComponent
import dk.bjarkebjarke.tally.data.session.FirebaseAuthentication
import dk.bjarkebjarke.tally.domain.account.AccountProfiles

/** The Account screen's profile source (M1-25): Firebase Auth. A test replaces it with a fake. */
@Module
@InstallIn(SingletonComponent::class)
object AccountModule {
    @Provides
    fun accountProfiles(authentication: FirebaseAuthentication): AccountProfiles = authentication
}
