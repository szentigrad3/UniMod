# Test 9 experimental portable binary

The attached Linux `.AppImage` is **not** an AppImageKit AppImage. It is a custom
self-extracting ELF using `portable-runtime-test9.c` and a bounded embedded
`app/` + `runtime/` gzip tar archive. It requires `tar`, x86_64 Linux,
a compatible glibc, a graphical desktop and local system trust stores.

The original binary embeds a Python 3.13/Tk runtime copied from the prior
Test 8 validated payload. This runtime is not represented as new source code
in the source ZIP; to rebuild the experimental executable, provide a supported
Python/Tk runtime and re-create the embedded tar payload with its entry-point
modules. The C source includes the required `UniModT9` payload trailer format.

For **standard AppImageKit Type 2 packaging**, use `build-appimage.sh` or the
included GitHub Actions workflow; they require PyInstaller and appimagetool.
Do not claim a Type 2 AppImage was built by the custom portable launcher.
