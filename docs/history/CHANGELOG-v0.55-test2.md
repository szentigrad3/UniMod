# UniMod v0.55 Test 2 — Game-specific source identification fix

- Fixed the Updates Available button showing Stardew Valley SMAPI source identification while Graveyard Keeper or other BepInEx games are selected.
- The button now follows the selected game: Stardew Valley/SMAPI uses the automatic SMAPI catalogue lookup; Graveyard Keeper and other non-SMAPI games open Source Matching to review/assign sources.
- Button text updates when changing games; with no game selected it is disabled.
- This does not add automatic online identification for Graveyard Keeper, and does not change any installed mods without approval.
- Modrinth dependency resolution, Minecraft profile support, and Nexus approval gating remain unchanged from Test 1.
