package dk.bjarkebjarke.tally.domain.account

/** Who is signed in, as the Account screen shows it (wireframe 18); a part the sign-in did not give is null. */
data class AccountProfile(
    val name: String?,
    val email: String?,
)

/** The signed-in account's profile, from the session on this phone. */
fun interface AccountProfiles {
    fun current(): AccountProfile
}
