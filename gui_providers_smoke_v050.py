"""Standalone offline UI smoke test for provider discovery, under Xvfb."""
import unittest
from unittest.mock import patch
import tkinter as tk
import provider_catalogues
import unimod

class ProviderSmoke(unittest.TestCase):
 def test_browser_and_selection(self):
  app=unimod.App();app.withdraw()
  try:
   app.show_page('Mod Websites')
   app.provider_choice.set('Modrinth')
   app.provider_query.set('world generation')
   data=[{'provider':'Modrinth','title':'World Generator','author':'A','version':'1.0',
        'url':'https://modrinth.com/mod/TEST123','description':'Custom worlds',
        'identity':'TEST123','downloads':100}]
   with patch('provider_catalogues.search',return_value=data):
    app.provider_begin_search()
    # Poll on the Tk UI thread rather than waiting for async network calls.
    import time
    deadline=time.monotonic()+3
    while app.provider_loading and time.monotonic()<deadline:
     app.update()
     time.sleep(.02)
   self.assertFalse(app.provider_loading)
   self.assertEqual(len(app.provider_tree.get_children()),1)
   app.provider_tree.selection_set('0')
   with patch('webbrowser.open') as opened:app.provider_open_result()
   opened.assert_called_once_with('https://modrinth.com/mod/TEST123')
  finally:app.destroy()
if __name__=='__main__':unittest.main()
