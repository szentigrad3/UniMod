# UniMod 0.55 Test 12

- Add `modio_files.py`: game/mod-scoped official user-path modfile browsing, exact ID refetch at download, expiring URL handling and fail-closed metadata validation.
- Accept only size-bounded ZIP modfiles with official MD5 and valid platform/virus metadata.
- Add restricted mod.io signed API-download host handling and per-chunk MD5 verification; local SHA-256 staging receipts contain no credentials or download URLs.
- Enable selected mod.io ZIPs in the existing Provider Inbox for reviewed SMAPI/BepInEx install/update with recovery backups.
- Bind downloads to the verified current game and mod.io user/key session, block game/key changes.
- Add offline regression checks for game mismatch, altered releases, expiration, download errors, package installation, update-backup recovery, and GUI wiring.
- Protected Nexus and CurseForge downloads remain disabled pending approvals. Live API responses on CachyOS untested.
