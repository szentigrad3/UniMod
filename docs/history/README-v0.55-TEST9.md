# UniMod v0.55 Test 9 — CachyOS tester guide

## Launch Linux x86_64 bundle

```bash
chmod +x UniMod-0.55-test9-x86_64.AppImage
./UniMod-0.55-test9-x86_64.AppImage
```

**Important:** This experimental portable file is an ELF self-extracting Python/Tk launcher, named `.AppImage` for continuity with prior test builds. It is **not** a standard AppImageKit Type 2 image; host requires `tar`, compatible glibc and a working graphical desktop. The source ZIP retains a separate official AppImageKit CI build workflow.

## Match Graveyard Keeper / Graveyard Keeper 2 DLLs without Nexus ZIPs

1. Select **Graveyard Keeper** or **Graveyard Keeper 2** and scan installed mods.
2. Open **Tools → Source Matching → Search without Nexus ZIP…**.
3. Review the DLL, suggested query, and status. Invalid, duplicated, symlinked or existing-source entries cannot be searched.
4. Select a **Search ready** row, choose **Search selected on Nexus**, and review the official, game-specific read-only catalogue results.
5. **Verify the game's exact Nexus mod page, uploader, supported game and file yourself.** Only then use the existing explicit source-link approval. Search-name similarity is not provenance evidence; the button does not authenticate a DLL, automatically bind a link, or download/update a mod.

**For stronger local evidence**, continue using **Match downloaded Nexus ZIPs…** with original archives and valid matching `.meta` sidecars, available since Test 8.

## Run regression tests from extracted source

```bash
python3 -m unittest discover -p 'test_*.py' -q
xvfb-run -a python3 gui_bepinex_search_hints_smoke_v055.py
xvfb-run -a python3 gui_bepinex_nexus_evidence_smoke_v055.py
xvfb-run -a python3 unimod.py --smoke-test
```

## Safety, permission and network limits

- No user-installed game files are changed by this new feature.
- Nexus GraphQL metadata search does not turn on protected OAuth/download functionality.
- Results can be wrong. A filename or local manifest does not prove original publisher or Nexus mod ID.
- No live Nexus catalogue calls or actual user's CachyOS installation tested in this environment.
