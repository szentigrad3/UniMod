# UniMod v0.55 test1 — CachyOS/Linux validation

Experimental source build. v0.54 is the last separately documented baseline.

## Run from source

```bash
unzip UniMod-0.55-test1-Linux-source.zip
cd unimod-v0.55-test1
python3 -m unittest discover -p 'test_*.py' -q
python3 unimod.py
```

Tkinter is required (`python3-tk` in some distributions). The production AppImage workflow is `./build-appimage.sh` and expects an x86_64 Linux host with PyInstaller and appimagetool; that binary has not been produced or smoke tested here.

## Minecraft dependency install

1. Choose Discover -> Modrinth. Select and download a supported `.jar` to the Provider Inbox. The downloaded Modrinth file must have a staged UniMod receipt.
2. Choose Provider Inbox, select that JAR and click **Install Modrinth JAR + required dependencies…**. UniMod discovers a single local Prism/MultiMC profile or lets you choose one.
3. The planner reads the game and loader versions and recursively resolves only missing *required* dependencies from Modrinth. Optional dependencies remain optional. Exact required versions are respected. No downloads or game files are touched while planning.
4. Review the list, total size and target profile and approve. All missing dependencies download to the managed app cache first and are verified against their Modrinth SHA-512 fingerprints. Already verified cache items may be reused.
5. UniMod installs required dependencies in dependency order and finally the chosen JAR. A failing installation attempts to undo earlier changes and restore the original managed installation receipts. Backups are stored under `~/.config/unimod/recovery/minecraft/`.

To avoid corrupting running Minecraft, fully close the instance first. Back up important saves/profile data yourself before testing this experimental build.

## `.mrpack` inspection

Select a staged `.mrpack` in Provider Inbox and click **Inspect .mrpack…**. UniMod validates its recorded archive hash and reports Minecraft version, loader, file counts, client overrides and unsupported origins. It **does not import modpacks yet**. Unsafe pack paths fail closed.

## Nexus / CurseForge

Nexus OAuth is preserved from v0.53/v0.54 but remains approval-gated pending Nexus Mods' formal public-client registration. CurseForge read-only search remains key-gated; this build does not supply or request private credentials.
