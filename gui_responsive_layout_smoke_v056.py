"""UI viewport regression using realistic SMAPI and BepInEx installations.

Run with Xvfb at 1024x768, 1920x1080 and 3840x2160.
No downloads, installs, removals or game modifications are performed.
"""
import json
import tempfile
from pathlib import Path
from tkinter import ttk
from unittest.mock import patch

import unimod


def within(widget, region, label):
    widget.update_idletasks()
    assert widget.winfo_ismapped(), (f'{label} is not mapped; '
        f'widget={widget}, manager={widget.winfo_manager()}, '
        f'parent={widget.winfo_parent()}, parent-mapped={widget.nametowidget(widget.winfo_parent()).winfo_ismapped()}, '
        f'active={widget.winfo_toplevel().tabs.tab(widget.winfo_toplevel().tabs.select(),"text")!r}')
    ax,ay=widget.winfo_rootx(),widget.winfo_rooty()
    bx,by=region.winfo_rootx(),region.winfo_rooty()
    aw,ah=widget.winfo_width(),widget.winfo_height()
    bw,bh=region.winfo_width(),region.winfo_height()
    assert (bx-2<=ax and ax+aw<=bx+bw+2 and by-2<=ay
            and ay+ah<=by+bh+2), (
        f'{label} clipped: widget=({ax},{ay},{aw},{ah}), '
        f'region=({bx},{by},{bw},{bh})')


def find_button(root,text):
    todo=[root]
    while todo:
        w=todo.pop()
        if isinstance(w,ttk.Button) and w.cget('text')==text:
            return w
        todo.extend(w.winfo_children())
    raise AssertionError('Missing button: '+text)


with tempfile.TemporaryDirectory() as temp:
    base=Path(temp)
    stardew=base/'Stardew Valley'
    smapi=stardew/'Mods'/'Example'
    smapi.mkdir(parents=True)
    (smapi/'manifest.json').write_text(json.dumps({
        'Name':'Example Mod','UniqueID':'Test.Example','Version':'1.0.0'
    }))
    gk=base/'Graveyard Keeper 2'
    plugin=gk/'BepInEx'/'plugins'/'Author'/'Example'
    plugin.mkdir(parents=True)
    (plugin/'manifest.json').write_text(json.dumps({
        'name':'Example Plugin','version':'1.0.0','id':'author.example'
    }))
    with patch.object(unimod,'CONFIG',base/'games.json'), \
         patch.object(unimod,'SOURCE_OVERRIDES',base/'sources.json'), \
         patch.object(unimod,'detect_games',return_value=[]):
        unimod.cfg_save({'games':[
            {'name':'Stardew Valley','root':str(stardew),'kind':'smapi'},
            {'name':'Graveyard Keeper 2','root':str(gk),'kind':'bepinex'},
        ]})
        app=unimod.App()
        try:
            app.update()
            screen=(app.winfo_screenwidth(),app.winfo_screenheight())
            size=(app.winfo_width(),app.winfo_height())
            print('LAYOUT_SCREEN',screen,'WINDOW',size,flush=True)
            assert 0<size[0]<=screen[0]
            assert 0<size[1]<=screen[1]
            assert size[0]<=1360 and size[1]<=820, '4K app must not fill screen'
            for key in ('Overview','Installed Mods','Mod Websites',
                        'Updates Available','Downloads','All Games & Mods'):
                button=app.rail_buttons[key]
                within(button,app,'Sidebar '+key)
                button.invoke();app.update()
                assert app.tabs.tab(app.tabs.select(),'text').strip()==key

            for name,w in [('Game selector',app.game_combo),
                           ('Install ZIP',app.header_install),
                           ('Add game',app.header_add_game),
                           ('More',app.more_button)]:
                within(w,app,name)

            app.show_page('Overview');app.update()
            page=app.nametowidget(app._tab_with_name('Overview'))
            for text in ('1  My Mods','2  Find Mods','3  Check My Mods'):
                within(find_button(page,text),page,'Home '+text)

            app.show_page('Installed Mods');app.update()
            page=app.nametowidget(app._tab_with_name('Installed Mods'))
            print('MY_MODS_DEBUG',[(child,str(child.winfo_manager()),child.winfo_ismapped(),
                child.winfo_width(),child.winfo_height()) for child in page.winfo_children()],flush=True)
            for text in ('Check My Mods','Advanced view  ▸'):
                within(find_button(page,text),page,'My Mods '+text)
            within(app.filter_entry,page,'Mod search')

            app.show_page('Mod Websites');app.update()
            page=app.nametowidget(app._tab_with_name('Mod Websites'))
            within(app.provider_search_box,page,'Mod search')
            within(find_button(page,'Search'),page,'Find Mods Search')

            app.show_page('Updates Available');app.update()
            page=app.nametowidget(app._tab_with_name('Updates Available'))
            for text in ('Review ready updates…','Review selected update…',
                         'Restore a backup…','More update options  ▸'):
                within(find_button(page,text),page,'Updates '+text)

            app.show_page('Downloads');app.update()
            page=app.nametowidget(app._tab_with_name('Downloads'))
            for text in ('Check selected file','Review & install…',
                         'Review Nexus / ZIP downloads'):
                within(find_button(page,text),page,'Downloads '+text)

            # Non-destructive switch between a real SMAPI and BepInEx fixture.
            app.game_combo.current(1);app.change_game_combo();app.update()
            assert app.current()['kind']=='bepinex'
            app.show_page('Installed Mods');app.update()
            within(app.filter_entry,app.nametowidget(app._tab_with_name('Installed Mods')),
                   'BepInEx mod search')
            assert (smapi/'manifest.json').is_file()
            assert (plugin/'manifest.json').is_file()
            print('UNIMOD_RESPONSIVE_GUI_OK',flush=True)
        finally:
            app.destroy()
