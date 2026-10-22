# UniMod v0.55 Test 8 — CachyOS test guide

## Launch

```bash
chmod +x UniMod-0.55-test8-x86_64.AppImage
./UniMod-0.55-test8-x86_64.AppImage
```

The supplied executable is an **experimental portable ELF** with an embedded Python/Tk runtime, named `.AppImage` for continuity. It is not an AppImageKit Type 2 image. `tar` must be available on the host. The source includes a separate official AppImageKit build workflow.

## Test Graveyard Keeper local archive matching

1. Install/scan Graveyard Keeper or Graveyard Keeper 2 BepInEx mods.
2. Open **Tools → Source Matching → Match downloaded Nexus ZIPs…**.
3. Choose a folder containing original downloaded `.zip` files and matching `.zip.meta` files from Mod Organizer 2. The scan is local-only and does **not** download anything.
4. Review `Review candidate` rows; open each Nexus page to verify game, author and file.
5. Select the confirmed rows and press **Save reviewed source links**. No DLL files are modified.

Without the original ZIP **and** matching `.meta` sidecar, the new scanner cannot infer a Nexus ID, even when a DLL name matches a catalogue search result. Sidecar metadata is untrusted; byte equality is not evidence of Nexus publisher authenticity. Conflicting IDs and duplicate DLL bytes are blocked. Keep manual page-linking available for mods downloaded without MO2.

## Regression checks

```bash
python3 -m unittest discover -p 'test_*.py' -q
xvfb-run -a python3 gui_bepinex_nexus_evidence_smoke_v055.py
xvfb-run -a python3 gui_nexus_candidates_smoke_v055.py
xvfb-run -a python3 unimod.py --smoke-test
```

## Retained features

- Graveyard Keeper Nexus catalogue discovery is still read-only.
- Modrinth `.mrpack` installation to existing Prism/MultiMC profiles retains optional-file selection, review, checksums and rollback.
- CurseForge catalogue and file preview remain read-only and require authorised API access.
- Nexus downloads/OAuth remain disabled pending official app registration approval.
