# Experimental AppImage packaging source

The `runtime.c` and `build_fs.py` files implement a custom SquashFS extract-and-run ELF runtime. This is not the officially supported AppImageKit runtime. The UniMod 0.46 executable was produced from an AppDir containing bundled Python 3.13/Tcl/Tk files inherited from the verified 0.44 development AppImage, with the 0.46 application sources overlaid before the SquashFS rebuild.

A reproducible **official** AppImage build route is provided in the top-level `build-appimage.sh` and `.github/workflows/appimage.yml`, when PyInstaller and `appimagetool` are available. No private keys, Nexus tokens, game saves or installed mod folders are bundled.
