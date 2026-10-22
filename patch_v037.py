from pathlib import Path
p=Path(__file__).parent/'unimod.py'
s=p.read_text()
s=s.replace('"""UniMod 0.36 - Nexus registration-ready authentication and downloads."""', '"""UniMod 0.37 - reviewed Nexus download queue and NXM links."""')
s=s.replace('import nexus_integration as nexus_integr\n','import nexus_integration as nexus_integr\nfrom nexus_queue import NexusDownloadQueue\n',1)
s=s.replace('self.title(\'UniMod 0.36 — Linux Mod Manager\')',"self.title('UniMod 0.37 — Linux Mod Manager')")
s=s.replace('def __init__(self):\n        super().__init__()\n        self.title', 'def __init__(self, incoming_nxm=None):\n        super().__init__()\n        self.title',1)
needle='self.family_rows={}; self.collapsed_families=set()'
assert needle in s
s=s.replace(needle,needle+'; self.nexus_queue=NexusDownloadQueue()',1)
needle="self.after(150,self.scan_global_library)"
assert needle in s
s=s.replace(needle,needle+"\n        if incoming_nxm is not None:\n            self.after(250, lambda: self.nexus_enqueue_nxm(incoming_nxm, from_browser=True))",1)
needle="ttk.Label(inbox,text='Match ZIP updates to your installed SMAPI and BepInEx mods',style='Section.TLabel').pack(anchor='w',pady=(0,6))"
assert needle in s
s=s.replace(needle,"""ttk.Label(inbox,text='Nexus download queue',style='Section.TLabel').pack(anchor='w',pady=(0,5))
        ttk.Label(inbox,text='Approved Nexus manager links can be queued here. Tokens stay in memory; nothing downloads or installs until you approve it.',wraplength=900).pack(anchor='w',pady=(0,5))
        qbar=ttk.Frame(inbox);qbar.pack(fill='x',pady=(0,5))
        ttk.Button(qbar,text='Paste NXM link…',command=self.nexus_download_nxm).pack(side='left')
        ttk.Button(qbar,text='Download selected (review first)',command=self.nexus_queue_download).pack(side='left',padx=8)
        ttk.Button(qbar,text='Remove selected',command=self.nexus_queue_remove).pack(side='left',padx=8)
        self.nexus_queue_info=tk.StringVar(value='No Nexus requests queued. Select Mod Manager Download on Nexus after enabling the optional URL handler.')
        ttk.Label(inbox,textvariable=self.nexus_queue_info,wraplength=940).pack(anchor='w',pady=(0,5))
        self.nexus_queue_tree=ttk.Treeview(inbox,columns=('game','mod','file','status'),show='headings',height=4,selectmode='browse')
        for name,width in [('game',150),('mod',110),('file',110),('status',380)]:
            self.nexus_queue_tree.heading(name,text=name.capitalize())
            self.nexus_queue_tree.column(name,width=width,stretch=(name=='status'))
        self.nexus_queue_tree.pack(fill='x',pady=(0,12))
        ttk.Separator(inbox).pack(fill='x',pady=(0,10))
        """+needle,1)
start=s.index('    def nexus_download_nxm(self):')
end=s.index('    def nexus_test_connection(self):',start)
s=s[:start]+'''    def nexus_download_nxm(self):
        value=simpledialog.askstring('Nexus manager download',
            'Paste the nxm:// link from the Nexus Mod Manager Download button.\\n'
            'It will be queued for review; nothing downloads yet.',parent=self)
        if value:self.nexus_enqueue_nxm(value)

    def nexus_enqueue_nxm(self, value, from_browser=False):
        # The browser token is kept in memory only, never written to a receipt,
        # export, log or the GUI. A browser click opens a new UniMod instance.
        try:
            entry=self.nexus_queue.add_nxm(value)
        except (ValueError,TypeError) as exc:
            messagebox.showerror('Invalid Nexus manager link',str(exc),parent=self)
            return
        self.nexus_queue_refresh()
        self.nexus_queue_tree.selection_set(str(entry.id))
        self.nexus_queue_tree.see(str(entry.id))
        self.tabs.select(self.inbox_tab)
        self.nexus_queue_info.set('Nexus link queued for review — choose Download selected to proceed. Nothing has been installed.')

    def nexus_queue_refresh(self):
        tree=self.nexus_queue_tree
        for child in tree.get_children():tree.delete(child)
        for row in self.nexus_queue.public_rows():
            tree.insert('','end',iid=str(row['id']),values=(row['game'],row['mod'],row['file'],row['status']))

    def nexus_queue_remove(self):
        sel=self.nexus_queue_tree.selection()
        if not sel:return
        if self.nexus_queue.remove(int(sel[0])):
            self.nexus_queue_refresh()
            self.nexus_queue_info.set('Removed the selected request. No files were changed.')

    def nexus_begin_download(self,ref,file,nxm=None):
        # All website file choices and NXM links enter the *same* review queue.
        try:
            if nxm is not None:
                entry=self.nexus_queue._add(ref['game_domain'],str(ref['mod_id']),
                    str(file['file_id']),file.get('filename') or 'mod.zip',nxm)
            else:
                entry=self.nexus_queue.add_file(ref['game_domain'],ref['mod_id'],file['file_id'],
                    file.get('filename') or f"nexus-{ref['mod_id']}-{file['file_id']}.zip")
        except (KeyError,ValueError,TypeError) as exc:
            messagebox.showerror('Cannot queue Nexus file',str(exc),parent=self)
            return
        self.nexus_queue_refresh()
        self.nexus_queue_tree.selection_set(str(entry.id))
        self.tabs.select(self.inbox_tab)
        self.nexus_queue_info.set('Download queued. Select it and approve Download selected to begin.')

    def nexus_queue_download(self):
        if self.nexus_running:return
        selected=self.nexus_queue_tree.selection()
        if not selected:
            messagebox.showinfo('Select a request','Select a Nexus download request first.',parent=self);return
        entry=self.nexus_queue.get(int(selected[0]))
        if not entry or entry.status=='Downloading':return
        if entry.status=='Downloaded':
            self.nexus_queue_info.set('This file was already downloaded. Review it in Update Inbox.');return
        key=self.nexus_key.get().strip()
        if not key:
            self.nexus_queue_info.set('Connect your Nexus account or enter a private development key to download.')
            messagebox.showinfo('Connect Nexus','Sign in with a registered Nexus application, or use a personal key for private testing.',parent=self)
            self.tabs.select(self.tabs.index('end')-1 if False else self.tabs.index(self.inbox_tab))
            return
        if not messagebox.askyesno('Review Nexus download',
                f'Download {entry.game} / mod #{entry.mod} / file #{entry.file} into your inbox?\\n\\n'
                'This will not install mods. Nexus may restrict direct downloads based on account privileges.',parent=self):return
        self.nexus_running=True
        entry.status='Downloading';entry.note=''
        self.nexus_queue_refresh()
        inbox=str(Path(self.inbox_folder.get()).expanduser())
        def worker():
            try:
                url=nexus_integr.download_link_url(entry.game,entry.mod,entry.file,entry.nxm)
                mirrors=nexus_api_json(url,key)
                location=nexus_integr.select_download_url(mirrors)
                result=nexus_integr.download_archive(location,inbox,entry.filename)
                error=None
            except Exception as exc:
                result=None
                error=nexus_integr.redacted_error(exc,key,(entry.nxm or {}).get('key'))
            self.after(0,lambda:self.nexus_queue_done(entry,result,error))
        threading.Thread(target=worker,daemon=True).start()

    def nexus_queue_done(self,entry,result,error):
        self.nexus_running=False
        if error:
            entry.status='Needs attention'
            entry.note=error
            self.nexus_queue_info.set('Download was not completed: '+error)
            if any(word in error.lower() for word in ('403','access denied','permission','mirror','browser')):
                self.nexus_queue_info.set('Nexus may require a browser-authorized download. Use the official page and Mod Manager Download button.')
                messagebox.showinfo('Nexus download restrictions',
                    'Nexus may require a browser-authorized download. Open the official mod page and choose Mod Manager Download. No restrictions are bypassed.',parent=self)
                webbrowser.open(f'https://www.nexusmods.com/{entry.game}/mods/{entry.mod}?tab=files')
        else:
            self.nexus_queue.mark_downloaded(entry,result)
            self.nexus_queue_info.set(f'Download saved to {result.name}. Use Update Inbox to review before installation.')
        self.nexus_queue_refresh()

''' +s[end:]
# The normal download-file chooser now just enqueues the selection, rather than implies direct completion
s=s.replace("f\"Download {file['name']} (file #{file['file_id']}) into your UniMod download inbox?\\n\\n\"","f\"Queue {file['name']} (file #{file['file_id']}) for a reviewed download?\\n\\n\"")
# banner/desktop/footer and cli
s=s.replace("UniMod v0.34   •   Local installation","UniMod v0.37   •   Local installation")
s=s.replace("'UniMod/0.36'","'UniMod/0.37'")
s=s.replace("'Application-Version':'0.36.0'","'Application-Version':'0.37.0'")
s=s.replace("print('UniMod 0.36')","print('UniMod 0.37')")
s=s.replace("    if '--smoke-test' in sys.argv:","    if '--nxm' in sys.argv:\n        if len(sys.argv)!=3 or sys.argv[1]!='--nxm':\n            raise SystemExit('Usage: unimod.py --nxm <official-nxm-link>')\n        try: nexus_integr.parse_nxm_link(sys.argv[2])\n        except ValueError:\n            raise SystemExit('Invalid or expired Nexus manager link') from None\n        App(incoming_nxm=sys.argv[2]).mainloop()\n    elif '--smoke-test' in sys.argv:")
s=s.replace('self.tabs.select(self.tabs.index(\'end\')-1 if False else self.tabs.index(self.inbox_tab))\n            ','')
p.write_text(s)
