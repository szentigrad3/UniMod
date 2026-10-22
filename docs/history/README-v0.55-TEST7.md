# UniMod v0.55 Test 7 — CachyOS test guide

## Launch

```
chmod +x UniMod-0.55-test7-x86_64.AppImage
./UniMod-0.55-test7-x86_64.AppImage
```

This is an experimental self-extracting ELF portable executable named `.AppImage` for continuity with prior test builds; it is **not** a Type 2/AppImageKit image. It embeds Python 3.13 and Tk, and requires the Linux `tar` utility to extract its own bundled application in an isolated temporary folder. The source also contains a separate official AppImageKit build script and GitHub workflow.

## Try CurseForge discovery

1. Open **Discover → Providers**, select CurseForge, enter an **approved** CurseForge API key (session only), and enter a numeric CurseForge Game ID. If you don't know the ID, find it from the official CurseForge developer catalogue first.
2. Select **Verify CurseForge game ID…**. Read the official returned game title, and approve the ID only if correct.
3. Search for a mod. Select a result and press **Browse release files…** to inspect read-only metadata; no in-app CurseForge download is available.
4. If you want to link a catalogue page to a locally installed mod, initiate from **Source Matching** and confirm the candidate publisher and game. A different game ID cannot be assigned.
5. Change the API key or game ID to verify that the prior approval is invalidated.

## Existing workflows

- Graveyard Keeper and Graveyard Keeper 2 Nexus discovery remain separate, read-only, and require explicit source linking.
- The Modrinth `.mrpack` importer continues to offer optional client files off by default with hash verification and rollback, but live installations still need end-user testing.
- Nexus download and login authorization remain provider-registration-gated.

## Regression commands

```
python3 -m unittest discover -p 'test_*.py' -q
xvfb-run -a python3 gui_curseforge_preview_smoke_v055.py
xvfb-run -a python3 gui_nexus_candidates_smoke_v055.py
xvfb-run -a python3 unimod.py --smoke-test
```

The distributed binary has only been smoke-tested on virtual Linux, not on a real CachyOS desktop or with live provider credentials.
