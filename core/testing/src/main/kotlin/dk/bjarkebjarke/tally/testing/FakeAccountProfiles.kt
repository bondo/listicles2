package dk.bjarkebjarke.tally.testing

import dk.bjarkebjarke.tally.domain.account.AccountProfile
import dk.bjarkebjarke.tally.domain.account.AccountProfiles

/** An [AccountProfiles] that answers [profile]. */
class FakeAccountProfiles(
    var profile: AccountProfile = AccountProfile(name = null, email = null),
) : AccountProfiles {
    override fun current(): AccountProfile = profile
}
