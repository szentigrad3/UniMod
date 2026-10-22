# UniMod 0.40 — Unified Update Review

- New **Updates Available** page, accessible from the main rail and the top **Check updates** button.
- Read-only combined overview of Nexus exact-ID and GitHub release checks, including unlinked and unchecked mods.
- Components with identical exact Nexus IDs are grouped into a single update-source row, but individual installed mods are preserved.
- Confirmed newer releases only; unknown versions, conflicts, rate limits and missing sources are explicitly distinguished.
- Check connected sources on demand; no background polling, no automatic API requests at startup.
- Select a confirmed Nexus entry to choose its files through the existing reviewed queue or open its official web page.
- Existing download inbox and backup-protected ZIP replacement remain separate explicit user steps.
- Nexus browser sign-in remains gated by registered application approval, and no personal key is written to disk.

**Limitations:** Nexus checking requires an authorised session key during private testing. Bulk refresh checks at most 25 unique Nexus page IDs per request; rerun as appropriate. Live end-to-end Nexus account/download testing remains pending.
