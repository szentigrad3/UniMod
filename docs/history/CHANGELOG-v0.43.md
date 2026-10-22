# UniMod v0.43 — Source-resolution reliability

- Fixed stale v0.41 window title.
- Uses SMAPI v4.5.2 API route for Stardew ID lookups.
- Recognises official Nexus URLs in SMAPI suggestedUpdate responses for the exact requested UniqueID.
- Refuses conflicting Nexus IDs between API metadata and suggestions.
- Distinguishes empty/incomplete catalogue results from request failures.
- Makes the limitations of the sunset SMAPI compatibility catalogue visible.
- Existing mods and configuration are not modified by lookups.
