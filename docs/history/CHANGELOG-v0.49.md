# UniMod 0.49 — Other-manager download discovery

- Include known Vortex download locations when looking for existing Nexus archives (Linux and limited Wine defaults).
- Recognise nested per-game folders with existing strict depth, size and archive-count bounds.
- Add **Remember folder** in the Find mod sources window. Remembered locations are opt-in and stored locally in `~/.config/unimod/download-locations.json`, permissions 0600.
- No broad scanning of the home directory or Steam library; no new external API calls.
- Archive-to-installed-mod matching still requires exact SMAPI UniqueIDs. Metadata can be forged; source suggestions require review and never install automatically.
- Nexus SSO remains gated until UniMod's application registration is approved.

This does not reconstruct absent archives or make an online Nexus match from a guessed name. It improves coverage where users already have downloaded ZIPs in Vortex or custom folders.
