#!/usr/bin/env bash
set -euo pipefail
src="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
dst="${XDG_DATA_HOME:-$HOME/.local/share}/unimod"
apps="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
icons="${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor/256x256/apps"
command -v python3 >/dev/null || { echo 'Install Python first.' >&2; exit 1; }
python3 -c 'import tkinter' || { echo 'Install the tk package first.' >&2; exit 1; }
mkdir -p "$dst" "$apps" "$icons"
cp "$src/unimod.png" "$icons/unimod.png"
if [ "$src" != "$dst" ]; then
  cp "$src/unimod.py" "$src/nexus_integration.py" "$src/nexus_queue.py" "$src/nxm_handler.py" "$src/instance_bridge.py" "$src/LICENSE" "$dst/"
  cp "$src/stardew-aio-nexus-links.json" "$dst/"
  cp -a "$src/json5" "$dst/"
  cp "$src/launch.sh" "$dst/launch.sh"
  chmod +x "$dst/launch.sh"
fi
# Quotes escape a path containing spaces in the desktop entry's Exec key.
python3 - "$dst" "$apps" <<'PY'
from pathlib import Path
import sys
root, apps = map(Path, sys.argv[1:])
launcher = root / 'launch.sh'
if any(ch in str(launcher) for ch in '\n\r'):
    raise SystemExit('Unsupported installation path')
escaped = str(launcher).replace('\\', '\\\\').replace('"', '\\"').replace('`', '\\`').replace('$', '\\$')
content = ('[Desktop Entry]\nType=Application\nName=UniMod\nComment=Manage existing Steam game mods\n'
           'Exec="' + escaped + '"\nIcon=unimod\nCategories=Game;Utility;\nTerminal=false\n')
(apps / 'unimod.desktop').write_text(content, encoding='utf-8')
PY
printf 'Installed UniMod launcher at %s/unimod.desktop\n' "$apps"
