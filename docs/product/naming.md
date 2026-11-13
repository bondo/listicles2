# App and repo name shortlist (M0.5-04, issue #17)

Status: proposal for the owner's decision in M0.5-O2. No agent renames anything. Research date: **2026-11-13**.

The app: shared household lists for Android (inventories, packing templates that merge into trip checklists), real-time sync,
English and Danish UI. Working name: **Listicles**.

## 1. What was and was not verified

Only public sources, and no personal details in any request.

| Check | Method | Result |
|---|---|---|
| GitHub user/org names | GitHub search API (`search/users`, `in:login`) | Done for all candidates (table below). The direct `users/<name>` endpoint was blocked in this environment, so a name that appears in search results is taken, and one that does not is **probably** free (search is not a reservation check) |
| GitHub repo names | GitHub search API (`search/repositories`, `in:name`) | Done. Counts include loose matches; they show crowding, not conflicts. Repo names are per owner, so a repo never collides, but a popular same-named project causes confusion |
| Play Store | Web search for each name plus "Google Play" | **Not verified.** `play.google.com` is not reachable from this environment, so no listing was opened. Web search found no listing for Nestlist, Hearthlist or Listicles, which is weak evidence, not a check. Play Console (when the account exists) is the only real check for a package id and a title |
| Domains (.com, .dk, .app) | Tried RDAP and DNS from the sandbox | **Not verified.** The proxy blocks RDAP hosts and DNS does not resolve outside the allowed list (even `listicles.com` failed), so "no answer" says nothing. The owner should check at a registrar (for .dk: punktum.dk) |
| Trademarks | Not checked | The owner should search EUIPO/DKPTO and USPTO before committing |

Nothing below claims a name is available. "Not found" means only "not found by the method named".

## 2. Candidates

GitHub columns are from the 2026-11-13 searches. "Users" are accounts whose login contains the name.

| # | Name | GitHub login match | GitHub repos named like it | Play Store | Domains |
|---|---|---|---|---|---|
| 1 | Listicles (current) | user `Listicles` exists | 38 (e.g. dragonmc77/Listicles) | not verified; web search found no app | not verified |
| 2 | Nestlist | user `nestlist` exists, plus `NestListsg`, `nestlistltd` | 37 | not verified; web search found none; a different app, Nestify, is a family organiser | not verified |
| 3 | Hearthlist | `HearthLister` only (no exact match) | 3 | not verified; web search found none, but Hearth Display Inc. sells family "Hearth Lists" and an app | not verified |
| 4 | Samlet | user `samlet` exists, 59 matches | 134 | not verified | not verified |
| 5 | Huskr | no exact match (19 partial) | 15 | not verified | not verified |
| 6 | Packmate | user `packmate` exists, 5 matches | 117 | not verified | not verified |
| 7 | Tallyhome | user `tallyhome` exists | 16 | not verified | not verified |

Handle for the GitHub org/repo: a repo name (`bondo/<name>`) is always possible, so a taken user name only matters if we want an org.

## 3. Pros, cons and how each reads

| Name | Pros | Cons | English | Danish |
|---|---|---|---|---|
| Listicles | Already in code and docs, so zero rename cost; memorable | A "listicle" is a clickbait article, so it suggests content, not a tool; search results are crowded; says nothing about households or sharing | Playful, clear that it is about lists | Understandable (liste), slightly odd ending; pronounced roughly as in English |
| Nestlist | Home and shared-space feel, easy to say and spell; works in both languages | Taken GitHub user, a company-looking `nestlistltd`, and many "Nest" brands (Google Nest, Nestify) | Clear: a list for the nest | "Nest" and "liste" are both Danish words, so it reads as "rede-liste" (a bit comic), still pronounceable |
| Hearthlist | Warm, household feel; GitHub looks mostly free | Likely collision with Hearth Display's "Hearth Lists"; "th" is hard for Danish speakers | Warm, slightly twee | "Hearth" is unknown to many Danes; hard to pronounce |
| Samlet | Danish word meaning "gathered, combined, together", which fits sharing and merging lists; short | Not an English word; Danish brand with "Samlet" in many company names; 134 GitHub repos; English speakers may not pronounce it | Meaningless but easy to read | Excellent, natural, but generic ("samlet" also means "total") |
| Huskr | Short, "huske" (to remember) is the Danish word for a memo list | Dropped-vowel style is dated; unclear in English | Reads as "Husker" (a Nebraska football team) | Clever for Danes, reads as "husker" ("remembers") |
| Packmate | Clear meaning for packing lists | Only covers packing; 117 GitHub repos; "Pack mate" is a generic phrase | Clear | Understandable, a bit cheesy |
| Tallyhome | Fits inventories and homes | "Tally" is accounting-flavoured; awkward in Danish | Clear | "Tally" is unfamiliar |

## 4. Recommendation

**Nestlist**, on condition that the owner confirms the Play title, the package id `dev.nestlist.app` and a domain at a registrar, and finds no trademark conflict.
It is meaningful in both languages, short, and fits households. If the owner's checks show a conflict (the GitHub user `nestlist` and a `nestlistltd` account suggest a company or product may use the name), the fallback is **keep Listicles**: it costs nothing and nothing found is blocking it. Samlet is the pick if the owner prefers a Danish-first brand.

## 5. Where the name appears

Renaming is a task for M1-01 to plan after the owner decides; nothing is renamed by this document.

| Place | Current value | Cost to change |
|---|---|---|
| Android `applicationId` and `namespace` (`app/build.gradle.kts`) | `dev.listicles.app` | Cheap before the first release; **permanent once published on Play**; also changes the package directories and the Firebase Android app registration |
| App label, English and Danish (`app_name` in `app/src/main/res/values/strings.xml` and `values-da/strings.xml`) | `Listicles` | Trivial; the Danish label may differ from the English one |
| Firebase project (and project id) | not created yet in this repo | The project id cannot be changed later; display name can. Pick before creating it |
| `google-services.json` package name | not committed | Must match `applicationId` |
| GitHub repo `bondo/listicles2` | `listicles2` | GitHub redirects the old URL, but CI, badge URLs (README status image), CODEOWNERS and docs links must be updated; secrets and branch protection carry over |
| Firebase test package (`firebase/package.json`, lockfile) | contains `listicles` | Cheap |
| Docs and README | `Listicles` throughout (`README.md`, `docs/PLAN.md`, `CLAUDE.md`) | Search and replace; `CLAUDE.md` is a process file, owner or tooling session only |
| Release artefacts, signing key alias, Play listing | not created yet | Name them after the decision |
| Domain and invite link host | none yet | Decide with the name |

## 6. Open questions for the owner

1. Register-check the domains (.com, .dk, .app) and a Play title, and run a trademark search for the chosen name.
2. Same name for the English and Danish app label, or a Danish variant?
3. Keep `bondo/listicles2` as the repo name and rename later, or rename at M1-01?
