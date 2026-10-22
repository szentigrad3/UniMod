# UniMod 0.46 — MO2 archive provenance and source matching

- Detect Mod Organizer 2's Nexus `.zip.meta` source records.
- Require exact SMAPI UniqueID match inside the companion downloaded ZIP.
- Recognise multiple SMAPI components in one archive, proposing the same source page.
- Reject wrong-game, invalid, oversized or symlinked `.meta` files.
- Surface conflicting Nexus IDs instead of assigning or overwriting.
- Keep the user-approved review workflow, existing backups, updates and registration gating.
- Fix version strings and application request headers for v0.46.
- This feature is local-only and is not a substitute for a Nexus-authorised catalogue lookup.
