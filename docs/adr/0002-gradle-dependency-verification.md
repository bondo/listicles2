# ADR 0002: Gradle dependency verification stays checksum-only

Status: accepted (M1-44, issue 189 item 6). Re-evaluate before the first external tester (M2) or when a dependency starts
publishing signatures the owner wants to trust.

## Context
`gradle/verification-metadata.xml` has `verify-metadata` on and `verify-signatures` off. Every artifact is pinned by its
sha256. The checksums are trust on first use: they are whatever Gradle resolved when `--write-verification-metadata` last ran.

## Decision
Keep checksum-only verification. Signature verification needs a trusted-keys list for each publisher, and many Android and
Kotlin libraries publish none or rotate keys without notice, so every update would become a key review. The weaker point is the
regeneration step, not the verification step.

## Consequences
* A changed artifact under an unchanged version fails the build, which is the attack this protects against.
* A regenerated file is reviewed in its PR like any other diff: `scripts/dependency_floors.py` rejects known-vulnerable
  versions, and Dependabot's 7-day cooldown keeps a fresh release from being proposed at once.
* Hand edits and agent-made regenerations of the file are not signed off by any publisher key; the owner's merge is the check.
