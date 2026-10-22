# UniMod 0.43 experimental runtime

This ELF packs the existing previously tested v0.41 SquashFS runtime plus a v0.43
source-built overlay containing `unimod.py` and `smapi_catalogue.py`. The
original runtime uses an extract-and-run technique; it is **not** an official
AppImageKit/AppImageLauncher-compatible build.

Bundled runtime may not work on older Linux versions. Review dependency and
network privileges before use. No personal API keys or game mods are embedded.
