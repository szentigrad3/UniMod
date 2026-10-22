# UniMod v0.55 Test 3 — CachyOS / Linux x86_64

## Graveyard Keeper source matching

1. Select your Graveyard Keeper (or Graveyard Keeper 2) game. Open **Source Matching** from Tools or the **Updates Available** action.
2. Select an installed mod with **Unmatched** / **Source needed**, then click **Find candidate pages…**.
3. UniMod opens **Mod Websites**, prefills the selected mod name and searches **GitHub** read-only. Search results are NOT a confirmation that the candidate matches the installed DLL. You can change the provider/query; Thunderstore needs its exact community slug; CurseForge/mod.io require their own approved API key.
4. Select a candidate and **Open selected official page** to check publisher, game and mod identity yourself. Only then click **Link reviewed page to selected mod…**, verify the confirmation dialog and approve.
5. The source URL is saved only in UniMod's configuration, not to your Graveyard Keeper files. It does not make the installed mod updatable by itself; downloads/installations still use their separate safety checks and approval screens.

## Launch

    chmod +x ~/Downloads/UniMod-0.55-test3-x86_64.AppImage
    ~/Downloads/UniMod-0.55-test3-x86_64.AppImage

The provided executable bundles Python/Tk in a custom extraction runtime. It is not guaranteed to integrate with every desktop's AppImage launcher. If Linux reports a loader or shared library problem, run from the source ZIP with Python/Tk installed and share the terminal output. Keep Test 2 as fallback.

## Validation

    python3 -m unittest discover -p 'test_*.py' -q
    xvfb-run -a python3 gui_source_candidates_smoke_v055.py
    xvfb-run -a python3 gui_source_route_smoke_v055.py

Automated tests use temporary fixture games. No tests operate on actual user installations; live provider queries still need end-user validation. Nexus OAuth remains approval-gated.
