# UniMod v0.55 Test 5 — Minecraft .mrpack import

Go to **Discover → Modrinth** to download a `.mrpack` into Provider Inbox, or select an existing verified staged `.mrpack`. In **Provider Inbox**, choose **Inspect .mrpack…** for a no-write summary, then **Import .mrpack to Prism/MultiMC…** to select an existing instance. UniMod compares the game and mod loader (including version), reviews the exact file count, CDNs and potential overwrites, then asks before downloading and installing. Every approved CDN file must match its manifest SHA-1, SHA-512 and byte count.

**Important:** This is a conservative experimental importer. It only accepts Modrinth CDN required-client files, skips optional/server-only files and never writes game saves, launcher metadata or arbitrary executables. It does not create or repair an incompatible launcher profile. For those modpacks, import through Prism Launcher itself. Previous files overwritten by this importer are saved under `~/.config/unimod/recovery/minecraft-packs/` (unless your configuration home differs). Close Minecraft before starting the import.

Rollback is automatic on reported installation errors; no tool can guarantee restoration after abrupt power loss or external writes while installing. Live CDN downloads and real CachyOS profile installation have not been tested from this container.

Run:

    chmod +x ~/Downloads/UniMod-0.55-test5-x86_64.AppImage
    ~/Downloads/UniMod-0.55-test5-x86_64.AppImage

Source tests:

    python3 -m unittest discover -p 'test_*.py' -q
    xvfb-run -a python3 gui_mrpack_import_smoke_v055.py

Nexus catalogue/source discovery remains read-only; OAuth and Nexus downloads remain pending official approval.
