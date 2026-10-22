# UniMod 0.52 — Unified Provider Inbox (2026-10-22)

## Added
- Download receipts for GitHub, Modrinth and Thunderstore containing only provider identity, archive SHA-256, size, selected game, and dependency/compatibility metadata. Never stores signed URLs, browser tokens or API keys.
- A **Provider Inbox** screen with explicit staged-file review before any game modification.
- Thunderstore **Stage selected ZIP to Provider Inbox** action in the existing Thunderstore screen; the old separate reviewed Thunderstore installer is preserved.
- SMAPI/BepInEx ZIP-only managed installation through existing safe import and backup-protected update paths.
- Conservative preflight rejecting changed archives, ambiguous/multi-package updates, duplicate SMAPI identities, unresolved required SMAPI/Thunderstore dependencies, disabled providers, missing minimum-version checks and cross-game staged records.
- Managed installation receipts for new provider installs, including recovery of newly created folders if a subsequent receipt write fails.

## Important exclusions
- Minecraft Modrinth JAR, MRPACK, and ZIP assets are still **download-only**. Minecraft loader/server/profile deployment and automatic Modrinth dependency resolution are NOT implemented.
- Generic GitHub assets have no standard game compatibility; users must review and explicitly approve any supported SMAPI/BepInEx ZIP.
- Nexus public SSO still requires Nexus-issued app slug and live integration testing; existing private-test functions preserved.
- CurseForge and mod.io approved API credentials are still required for their gated features.
- Experimental extract-and-run AppImage runtime remains in use; native CachyOS testing is pending.

## Validation
- 361 offline automated tests, including 15 new v0.52 staging and safety checks.
- Provider Inbox, GitHub/Modrinth file dialog, catalogue, Updates review and Thunderstore GUI smoke tests on virtual Linux.
