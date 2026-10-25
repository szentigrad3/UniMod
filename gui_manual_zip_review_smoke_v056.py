"""Xvfb: user-chosen ZIP cannot install without a review and approval."""
import json
import tempfile
import zipfile
from pathlib import Path
from unittest.mock import patch
import unimod

with tempfile.TemporaryDirectory() as temp:
    base=Path(temp)
    game=base/'Stardew Valley'
    mods=game/'Mods'
    mods.mkdir(parents=True)
    archive=base/'Example.zip'
    with zipfile.ZipFile(archive,'w') as z:
        z.writestr('Example/manifest.json',json.dumps({
            'Name':'Example','UniqueID':'Tests.Example','Version':'1.0'}))
    with (
        patch.object(unimod,'CONFIG',base/'games.json'),
        patch.object(unimod,'SOURCE_OVERRIDES',base/'sources.json'),
        patch.object(unimod,'detect_games',return_value=[]),
        patch.object(unimod.filedialog,'askopenfilename',return_value=str(archive)),
    ):
        unimod.cfg_save({'games':[{'name':'Stardew Valley','root':str(game),'kind':'smapi'}]})
        app=unimod.App()
        try:
            with patch.object(unimod.messagebox,'askyesno',return_value=False) as prompt:
                app.install_archive()
                assert prompt.call_count==1, 'New install must ask for confirmation'
                assert not list(mods.iterdir()), 'Cancel must leave mods untouched'
            with patch.object(unimod.messagebox,'askyesno',return_value=True), \
                 patch.object(unimod.messagebox,'showinfo') as notice:
                app.install_archive()
                assert (mods/'Example'/'manifest.json').exists()
                assert notice.called
            with patch.object(unimod.messagebox,'askyesno',return_value=False) as prompt:
                app.install_archive()
                assert prompt.call_count==1
                assert 'Update found' in prompt.call_args.args[0]
                assert len(list(mods.iterdir()))==1
            print('UNIMOD_MANUAL_ZIP_REVIEW_GUI_OK')
        finally:
            app.destroy()
