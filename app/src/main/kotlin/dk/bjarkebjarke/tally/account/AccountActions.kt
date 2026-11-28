package dk.bjarkebjarke.tally.account

/** What the Account screen's controls do (wireframes 18, 39, 45). */
data class AccountActions(
    val onBack: () -> Unit,
    val onSignOut: () -> Unit,
    val onSignOutAnyway: () -> Unit,
    val onCancel: () -> Unit,
    val onFailureShown: () -> Unit,
)
