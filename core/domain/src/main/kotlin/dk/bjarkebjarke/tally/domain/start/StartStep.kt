package dk.bjarkebjarke.tally.domain.start

/** What the start-up gates know. The gates after [signedIn] only count while it is true. */
data class StartFacts(
    val updateRequired: Boolean,
    val signedIn: Boolean,
    val emailVerified: Boolean,
    val nameSaved: Boolean,
    val notice: HouseholdNotice?,
)

/** The one screen the app opens on (P10). */
sealed interface StartStep {
    data object Update : StartStep

    data object SignIn : StartStep

    data object VerifyEmail : StartStep

    data object EnterName : StartStep

    data class Notice(
        val notice: HouseholdNotice,
    ) : StartStep

    data object Home : StartStep
}

/** The gate order of P10 (docs/milestones/M1.md section 8): update, signed in, verified, name, notice, home. */
fun startStep(facts: StartFacts): StartStep =
    when {
        facts.updateRequired -> StartStep.Update
        !facts.signedIn -> StartStep.SignIn
        !facts.emailVerified -> StartStep.VerifyEmail
        !facts.nameSaved -> StartStep.EnterName
        facts.notice != null -> StartStep.Notice(facts.notice)
        else -> StartStep.Home
    }
