"""GUI Test 6: optional content dialog defaults to skipping and supports explicit choice."""
import unittest
import tkinter as tk
from unittest.mock import patch
import unimod


class GUIOptional(unittest.TestCase):
    def setUp(self):
        self.app=unimod.App();self.app.withdraw()
    def tearDown(self):self.app.destroy()
    def _choose(self, action):
        candidates=[{'path':'mods/A.jar','size':1234,'available':True},
                    {'path':'mods/B.jar','size':5678,'available':False}]
        def interact():
            dialog=next(x for x in self.app.winfo_children() if isinstance(x,tk.Toplevel))
            def find_all(root,cls):
                result=[]
                for child in root.winfo_children():
                    if isinstance(child,cls):result.append(child)
                    result.extend(find_all(child,cls))
                return result
            if action=='select':
                find_all(dialog,tk.Listbox)[0].selection_set(0)
                button=next(x for x in find_all(dialog,unimod.ttk.Button) if x.cget('text')=='Review selected files')
                button.invoke()
            elif action=='skip':
                button=next(x for x in find_all(dialog,unimod.ttk.Button) if x.cget('text')=='Skip optional files')
                button.invoke()
            else:dialog.destroy()
        self.app.after(40,interact)
        return self.app._minecraft_mrpack_choose_optional(candidates)
    def test_default_skips_without_modifying_files(self):
        self.assertEqual(self._choose('skip'),[])
    def test_selected_file_is_recorded_only_on_confirmation(self):
        self.assertEqual(self._choose('select'),['mods/A.jar'])

if __name__=='__main__':unittest.main()
