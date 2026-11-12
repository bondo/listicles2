# ADR 0001: detekt stays on 1.23.8 for now

Status: accepted (M0, 2026-11). Re-evaluate when detekt 2.0.0 (stable) is released.

## Context
PLAN section 5.4 asks M0 to evaluate detekt 2.x, which supports Kotlin 2.4 and type resolution, and to stay on 1.23
with the gap recorded if 2.x is not stable enough.

## What was tested (scratch copy, Kotlin 2.4.20, AGP 9.4.1, Gradle 9.8.2)
| | 1.23.8 | 2.0.0-alpha.6 (latest 2.x on the Gradle plugin portal) |
|---|---|---|
| Release status | stable | **alpha only**; no 2.0.0 release yet |
| Plugin id / group | `io.gitlab.arturbosch.detekt` | `dev.detekt` (renamed) |
| Source-only `detekt` on Kotlin 2.4.20 | works | works |
| Type-resolved `detektMain` / `detektTest` on `:core:domain` (JVM) | works, no Kotlin-version warnings | works |
| Type-resolved tasks on `:app` (AGP 9) | **not registered** (no `detektDebug` etc.) | `detektDebug`, `detektRelease`, `detektMain` registered and run |
| Config migration | none | `build:` section removed, `UnusedPrivateMember` split into `UnusedPrivateFunction/Property/Class`, report API renamed (`md`, `xml`, `txt` removed) |

## Decision
Stay on 1.23.8 (stable). Use the type-resolved `detektMain` and `detektTest` on `:core:domain`, where the
business logic lives (wired into `verify.sh`; CI needs the same tasks added to the `static` job, an owner-reviewed
change because it touches the workflow files). `:app` gets source-only detekt.

## Known gap
No type-resolved detekt on `:app` until 2.x is stable. Rules that need types (for example always-true checks,
`UnnecessarySafeCall`, `RedundantSuspendModifier`) do not run on Compose/UI code. The Kotlin compiler warnings
and Android Lint cover part of that.

## Consequences
When 2.0.0 is released: rename the plugin, migrate `config/detekt/detekt.yml` as above, enable type-resolved tasks for
`:app`, and drop this gap. Dependabot will not propose the jump because the group id changed, so re-check this ADR by hand.
