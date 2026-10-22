# UniMod v0.55 Test 6 — CachyOS test guide

## What changed

Staged Modrinth `.mrpack` imports now offer a second review screen for **optional** Minecraft client files. They start deselected. Pick only files you want, then approve the final installation summary. Unknown source hosts, unsafe destinations, and server-only files remain blocked.

## Test workflow

1. Keep Test 5 as a fallback and use a disposable Prism Launcher / MultiMC profile to test new imports.
2. Run `chmod +x UniMod-0.55-test6-x86_64.AppImage && ./UniMod-0.55-test6-x86_64.AppImage`.
3. In UniMod open **Provider Inbox**, select a verified staged `.mrpack`, choose **Import .mrpack to Prism/MultiMC…**.
4. Choose a profile with exactly matching Minecraft/loader versions. If the pack has optional client files, review them (off by default). Unsupported entries are marked unavailable.
5. Examine the final download, overwrite and backup counts and explicitly confirm.
6. Check installed files in your profile and receipts in `~/.config/unimod/minecraft-pack-receipts.json`. Recovery files are under `~/.config/unimod/recovery/minecraft-packs/`.

## Safety and limitations

- Required content must come from accepted Modrinth CDN URLs and match the declared file size and SHA-1/SHA-512 hashes.
- Only the reviewed destinations under allowed Minecraft content/config folders can be modified. Existing files are backed up before replacement; failures restore previous content.
- Client-unsupported/server-only content cannot be selected.
- Nexus Mods read-only catalogues remain available, including Graveyard Keeper; Nexus OAuth and protected download flows are still held for official provider registration.
- Live Modrinth downloads, real installations, and compatibility on your CachyOS system still need testing. The portable ELF uses a custom extraction runtime rather than the official AppImageKit runtime.

## Tests

`python3 -m unittest discover -p 'test_*.py' -q`

`xvfb-run -a python3 gui_mrpack_optional_smoke_v055.py`

`xvfb-run -a python3 unimod.py --smoke-test`
