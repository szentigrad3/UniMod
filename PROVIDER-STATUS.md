# Provider status — 0.55.0-test12

This is a development preview. Live provider verification is pending; see the main README and latest development note.

**UniMod v0.55 Test 10:** Review-only source candidate ranking and provider access requirements added. Existing approvals are unchanged.

**UniMod v0.55 Test 9:** Graveyard Keeper / GK2 no-archive local search hints are available with user review, but are never treated as verified Nexus identities. Nexus login/downloads remain approval-gated.

> v0.55 Test 8: Graveyard Keeper (1 and 2) now have offline, review-gated Nexus ZIP/`.meta` DLL hash matching. Nexus OAuth/downloads are still approval-gated.

# UniMod 0.54 — Provider support matrix

| Provider | Discovery | Staging | Managed installation |
|---|---|---|---|
| Nexus Mods | Exact ID and approved private-test API | Existing queue with NXM handling | Existing reviewed SMAPI/BepInEx ZIP updates, backup/recovery; production sign-in approval pending |
| Thunderstore | Public community catalogue | **New** stage selected ZIP to shared Provider Inbox | Explicit review, checked required dependencies, SMAPI/BepInEx ZIP-only; legacy independent managed installer preserved |
| GitHub | Public search + release listing | Release-asset archive verification and SHA-256 receipt | Explicit review only for identified SMAPI/BepInEx ZIPs; repo presence does not establish game compatibility |
| Modrinth | Public search + loader/game version filters | SHA-1/SHA-256/SHA-512 verified assets with staged receipts | **New:** reviewed `.jar` install/update for verified Prism/MultiMC instances; exact loader/version and managed required dependencies checked; `.mrpack` remains download-only |
| CurseForge | API-key gated search | Not implemented | Not implemented; provider approval required |
| mod.io | Verified user API-path and game-scoped searches | **Test 12:** exact-ID ZIP release lists, MD5-verified reviewed staging with refreshed expiring links | **Test 12:** SMAPI/BepInEx ZIP installs and updates via existing identity-based preflight, explicit approval and recovery backups; live requests untested |
| Steam Workshop | Official link | Steam manages downloads | Managed by Steam; UniMod does not bypass restrictions |
| ModDB | Official link | Not implemented | Not implemented |

All source search results are leads, not confirmed provenance. Downloads do not install automatically. The AppImage is an experimental extract-and-run build, not official AppImageKit.

## v0.55 Test 5 Modrinth modpacks

Reviewed `.mrpack` import is available for existing Prism/MultiMC profiles only. The exact installed Minecraft **and loader version** must match the pack. Required client files on `cdn.modrinth.com` are verified against SHA-1/SHA-512 and size before writes; unsupported hosts are blocked. Archive overrides are limited to explicitly allowed game content/config paths; optional and server-only files are skipped. File backups and transactional rollback are used. No launcher creation, game execution, OAuth, Nexus downloads or unapproved installations are enabled. Network downloads remain untested in this environment.


## v0.55 Test 7
CurseForge supports explicitly verified game IDs and read-only release-file metadata for users with an approved, session-only API key. CurseForge downloads remain disabled; Nexus downloads/OAuth remain registration-gated.
