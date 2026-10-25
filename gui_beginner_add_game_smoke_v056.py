"""Xvfb: adding a recognized game requires a directory, not tech jargon."""
import tempfile
from pathlib import Path
from unittest.mock import patch

import unimod

with tempfile.TemporaryDirectory() as temp:
    root=Path(temp)
    game=root/'Simple Game'
    (game/'BepInEx'/'plugins').mkdir(parents=True)
    with patch.object(unimod,'CONFIG',root/'games.json'), \
         patch.object(unimod,'SOURCE_OVERRIDES',root/'sources.json'), \
         patch.object(unimod,'detect_games',return_value=[]), \
         patch.object(unimod.filedialog,'askdirectory',return_value=str(game)), \
         patch.object(unimod.simpledialog,'askstring',side_effect=AssertionError('Technical prompt shown')), \
         patch.object(unimod.messagebox,'askyesno',side_effect=AssertionError('Unexpected fallback dialog')):
        unimod.cfg_save({'games': []})
        app=unimod.App()
        try:
            app.add_game()
            app.update()
            assert len(app.data['games'])==1
            assert app.data['games'][0]['kind']=='bepinex'
            assert app.game_combo_value.get()=='Simple Game'
            assert app.tabs.tab(app.tabs.select(),'text').strip()=='Overview'
            assert not (game/'Mods').exists()
            with patch.object(unimod.messagebox,'showinfo') as notice:
                app.add_game()
                assert len(app.data['games'])==1
                notice.assert_called_once()
            print('UNIMOD_BEGINNER_ADD_GAME_GUI_OK')
        finally:
            app.destroy()
