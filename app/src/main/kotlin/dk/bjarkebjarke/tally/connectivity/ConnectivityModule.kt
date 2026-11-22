package dk.bjarkebjarke.tally.connectivity

import dagger.Binds
import dagger.Module
import dagger.hilt.InstallIn
import dagger.hilt.components.SingletonComponent
import dk.bjarkebjarke.tally.domain.connectivity.Connectivity

@Module
@InstallIn(SingletonComponent::class)
interface ConnectivityModule {
    @Binds
    fun connectivity(implementation: AndroidConnectivity): Connectivity
}
