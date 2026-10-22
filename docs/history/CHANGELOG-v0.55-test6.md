# UniMod v0.55 Test 6 — reviewed Modrinth optional pack files

- Added explicit per-file opt-in to optional client files in staged Modrinth `.mrpack` import.
- Required client files remain required. `client: unsupported` files are never installed.
- Optional files are skipped by default and must be explicitly selected before a second independent manifest/profile preflight and final yes/no confirmation.
- Unsupported CDNs, overrides that collide with optional destinations, and unsafe paths are not selectable.
- The final review includes optional selection count and recalculated download, backup and overwrite totals.
- Import receipts now record the exact optional paths chosen by the user.
- Transactional rollback, approved-file revalidation, SHA-1/SHA-512 and size checks are maintained.
- Optional-only packs can be inspected; an empty selection cannot trigger an import.
- Added nine offline tests, two GUI optional-dialog smoke tests; updated GUI build CI to run the new checks.
- Corrected release/window title and AppImage workflow names from Test 5 to Test 6.

**Not included:** Nexus file downloads/OAuth before formal client approval; automatic installation of unverified external CDN files; automatic Minecraft loader/profile creation.

**Testing limitations:** verified under offline synthetic instance fixtures and Xvfb; real Prism/MultiMC instances and live downloads require end-user validation. The distributed portable binary is an experimental custom SquashFS extract-and-run ELF, not an official AppImageKit runtime.
