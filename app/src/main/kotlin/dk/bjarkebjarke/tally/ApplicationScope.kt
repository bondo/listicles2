package dk.bjarkebjarke.tally

import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.components.SingletonComponent
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import javax.inject.Qualifier
import javax.inject.Singleton

/**
 * The application-wide [CoroutineScope], for work that must outlive the screen that started it (checklist section 5),
 * such as sign-out's steps 2 to 5 (M1-14). Its `SupervisorJob` keeps one failed child from ending the others.
 */
@Qualifier
@Retention(AnnotationRetention.BINARY)
annotation class ApplicationScope

/** Its own module, so a test that replaces the session (SignedOutStartTest) keeps it (M1-88). */
@Module
@InstallIn(SingletonComponent::class)
object ApplicationScopeModule {
    @Provides
    @Singleton
    @ApplicationScope
    fun applicationScope(): CoroutineScope = CoroutineScope(SupervisorJob() + Dispatchers.Default)
}
