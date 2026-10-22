"""Opt-in registration of UniMod as the Linux x-scheme-handler/nxm target.

Installs a desktop entry only when the user requests it. Does not register
credentials, inspect browser history, or handle other URL schemes.
"""
import os
from pathlib import Path
import subprocess


def build_entry(executable):
    path=Path(executable).expanduser().resolve(strict=True)
    if not path.is_file() or not os.access(path, os.X_OK):
        raise ValueError('Select an executable UniMod AppImage before enabling NXM links')
    if not path.name.lower().endswith('.appimage'):
        raise ValueError('The NXM handler requires a runnable UniMod AppImage')
    if any(ch in str(path) for ch in '\n\r\x00'):
        raise ValueError('Invalid AppImage location')
    # Desktop entry Exec requires quoting executable paths with spaces.
    escaped=str(path).replace('\\','\\\\').replace('"','\\"').replace('`','\\`').replace('$','\\$')
    return ('[Desktop Entry]\nType=Application\nName=UniMod — Nexus Downloads\n'
            'Comment=Review Nexus Mods Mod Manager Download links in UniMod\n'
            'Exec="'+escaped+'" --nxm %u\n'
            'Icon=unimod\nTerminal=false\nNoDisplay=true\n'
            'MimeType=x-scheme-handler/nxm;\nCategories=Game;Utility;\n')


def install(executable, data_home=None, mime_runner=None):
    content=build_entry(executable)
    base=Path(data_home or os.environ.get('XDG_DATA_HOME') or (Path.home()/'.local/share'))
    directory=base/'applications'
    directory.mkdir(parents=True,exist_ok=True)
    target=directory/'unimod-nxm.desktop'
    # The handler is never implicitly installed by normal UniMod startup.
    tmp=directory/'.unimod-nxm.desktop.tmp'
    tmp.write_text(content,encoding='utf-8')
    tmp.replace(target)
    runner=mime_runner or (lambda: subprocess.run(['xdg-mime','default','unimod-nxm.desktop','x-scheme-handler/nxm'],check=True,timeout=15))
    try:
        runner()
    except (OSError,subprocess.SubprocessError) as exc:
        raise RuntimeError('Desktop file installed, but xdg-mime registration failed. Check that xdg-mime is installed.') from None
    return target
