# UniMod v0.55 Test 12 — mod.io public file downloads and managed ZIP updates

**Experimental Linux x86_64 test build** based on Test 11. No private mod.io key is bundled or saved.

## Steps

1. After rotating any exposed key, choose a configured game and open **Discover → mod.io**.
2. Enter **mod.io User ID**, the matching mod.io **Game ID**, and a private personal API key in the masked field. Confirm **Verify mod.io game ID…**.
3. Search for a mod, select an official result and choose **Browse release files…**.
4. Choose **Fetch files**. Only published ZIPs with valid official MD5, expected exact game/mod/file IDs and supported platform/virus-scan metadata are listed. If none are listed, use the official game mod page.
5. Select the ZIP and **Download selected to inbox**, confirm the file and game. UniMod fetches a fresh exact-modfile record to avoid expired signed URLs, checks metadata did not change, and downloads into the inbox after approval.
6. Open **Provider Inbox → Review & install selected…** for a matching selected game. Only supported SMAPI and BepInEx ZIPs with trustworthy internal package IDs pass preflight. Existing mods are backed up before updates. If the ZIP cannot be matched reliably, installation is refused and the archive stays in the inbox.

## Security and limitations

- Session-only API key. The receipt contains an archive hash, game binding, mod/file ID and version only; not the key or signed download URL.
- Hash checking uses mod.io's published MD5, followed by a local SHA-256 receipt. This does not independently guarantee that a downloaded mod is safe.
- Only explicitly approved, identity-compatible ZIP files may be installed into SMAPI/BepInEx. Arbitrary-game mod installations, auto-updates without approval and mod.io subscription management are not implemented.
- The direct mod.io download endpoint and known mod.io CDN redirect hosts are allowlisted; unfamiliar CDN hosts fail closed. Expiring links require an exact-ID refresh.
- No live mod.io key was used to run tests. Confirm functionality first with a disposable test game/profile and inspect file metadata before installation.
- Nexus OAuth downloads and CurseForge API-file access are unchanged and remain approval-gated.

## Checks

- 518 offline Python regression tests, including 8 new mod.io cases.
- Virtual Linux GUI tests for mod.io source verification, release selection, download approval, and changed-key rejection.
- Experimental self-extracting ELF/AppImage-compatible build; not official AppImageKit Type 2.
