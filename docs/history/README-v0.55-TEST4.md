# UniMod v0.55 Test 4 — Graveyard Keeper + Nexus catalogue

From **Tools → Source Matching**, choose an installed Graveyard Keeper mod and **Find candidate pages…**. The Mod Websites page selects **Nexus Mods** and searches the official read-only GraphQL metadata API for the exact game. Select a result, open and review its official page, then choose **Link reviewed page to selected mod…** to approve the assignment. For mods not listed on Nexus, select GitHub or another provider. Graveyard Keeper 2 uses a separate game domain and never mixes search results with the original game.

This update does NOT download from Nexus, install mods, or enable OAuth. Nexus account functions remain approval-gated. A linked source is still not proof of matching binary; check the author and game/version yourself.

If Nexus metadata search fails, visit https://www.nexusmods.com/games/graveyardkeeper/mods or https://www.nexusmods.com/games/graveyardkeeper2/mods, find the exact page, and assign its URL manually. API connectivity could not be tested from this build container.

To run on CachyOS:

    chmod +x ~/Downloads/UniMod-0.55-test4-x86_64.AppImage
    ~/Downloads/UniMod-0.55-test4-x86_64.AppImage

For source testing:

    python3 -m unittest discover -p 'test_*.py' -q
    xvfb-run -a python3 gui_source_candidates_smoke_v055.py
    xvfb-run -a python3 gui_source_route_smoke_v055.py
    xvfb-run -a python3 gui_nexus_candidates_smoke_v055.py
