#!/usr/bin/env python3
"""Virtual Linux GUI smoke: one-click Check My Mods, no installation writes."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import unimod


def buttons(widget):
    for child in widget.winfo_children():
        if child.winfo_class()=='TButton':
            yield child
        yield from buttons(child)


with TemporaryDirectory() as folder:
    base=Path(folder)
    root=base/'game'
    mods=root/'Mods'
    mods.mkdir(parents=True)
    package=mods/'AIO Test Mod'
    package.mkdir()
    (package/'manifest.json').write_text(
        '{"Name":"AIO Test Mod","UniqueID":"Tests.AIO","Version":"1.0",'
        '"Dependencies":[{"UniqueID":"Tests.NotInstalled","IsRequired":true}]}')
    manifest=package/'manifest.json'
    original=manifest.read_bytes()
    with patch.object(unimod,'CONFIG',base/'config.json'), \
         patch.object(unimod,'SOURCE_OVERRIDES',base/'sources.json'), \
         patch.object(unimod,'detect_games',return_value=[]):
        unimod.cfg_save({'games':[]})
        app=unimod.App()
        try:
            app.current=lambda:{'kind':'smapi','name':'Mock Stardew','root':str(root)}
            app.show_game_health()
            dialog=next(w for w in app.winfo_children()
                        if w.winfo_class()=='Toplevel' and 'Check My Mods' in w.title())
            names={b.cget('text'):b for b in buttons(dialog)}
            assert {'Review Dependencies','Open Installation Audit',
                    'Copy safe report','Close'}.issubset(names)
            names['Copy safe report'].invoke()
            report=app.clipboard_get()
            assert 'UniMod — Check My Mods' in report
            assert 'Required dependencies needing review: 1' in report
            assert str(root) not in report
            assert 'Tests.NotInstalled' not in report
            assert manifest.read_bytes()==original
            names['Close'].invoke()
            print('PASS: Check My Mods — existing SMAPI dependency scan, no writes, redacted report')
        finally:
            app.destroy()
