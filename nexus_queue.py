"""Session-only reviewed Nexus request queue.

Never writes NXM URL authorization tokens, user identifiers, API keys or CDN
links to disk. The public view contains only non-secret identifiers.
"""
from dataclasses import dataclass, field
import itertools
from pathlib import Path
from nexus_integration import parse_nxm_link, _identity

@dataclass
class QueueEntry:
    id: int
    game: str
    mod: str
    file: str
    filename: str
    nxm: dict | None = field(default=None, repr=False)
    status: str = 'Ready to review'
    note: str = ''
    saved_path: str = ''
    received: int = 0
    total: int = 0

    def public(self):
        return {'id': self.id, 'game': self.game, 'mod': self.mod,
                'file': self.file, 'status': self.status, 'note': self.note,
                'saved_path': self.saved_path,
                'received': self.received, 'total': self.total}

class NexusDownloadQueue:
    def __init__(self):
        self._items=[]
        self._next=itertools.count(1)

    def add_nxm(self, uri):
        nxm=parse_nxm_link(uri)
        return self._add(nxm['game_domain'], nxm['mod_id'], nxm['file_id'],
                         f"nexus-{nxm['game_domain']}-{nxm['mod_id']}-{nxm['file_id']}.zip", nxm)

    def add_file(self, game, mod, file_id, filename):
        _identity(game,mod,file_id)
        # Path coercion is not a security guarantee; final sanitisation occurs
        # in nexus_integration.download_archive.
        return self._add(str(game),str(mod),str(file_id),str(filename),None)

    def _add(self,game,mod,file_id,filename,nxm):
        for entry in self._items:
            if (entry.game,entry.mod,entry.file)==(game,mod,file_id) and entry.status!='Downloaded':
                # Refresh an expired/replaced browser token without logging it.
                if nxm: entry.nxm=nxm
                if entry.status not in ('Downloading','Downloaded'):
                    entry.status='Ready to review';entry.note='';entry.received=0;entry.total=0
                return entry
        entry=QueueEntry(next(self._next),game,mod,file_id,filename,nxm)
        self._items.append(entry)
        return entry

    def get(self, id):
        return next((entry for entry in self._items if entry.id==int(id)),None)

    def public_rows(self):
        return [item.public() for item in self._items]

    def remove(self, id):
        entry=self.get(id)
        if entry and entry.status!='Downloading':
            self._items.remove(entry)
            return True
        return False

    def mark_downloaded(self, entry, result):
        entry.status='Downloaded'
        entry.saved_path=str(Path(result))
        entry.note='Review in Update Inbox before installation'
        entry.nxm=None  # discard one-time browser token promptly
        entry.received=entry.total if entry.total else entry.received

    def ready_items(self):
        """Reviewed download candidates; no automatic network calls."""
        return [entry for entry in self._items if entry.status in ('Ready to review', 'Needs attention')]

    def retry(self, id):
        """Return an unsuccessful request to review state; never retry automatically."""
        entry=self.get(id)
        if not entry or entry.status not in ('Needs attention', 'Cancelled'):
            return False
        entry.status='Ready to review';entry.note='';entry.received=0;entry.total=0
        return True

    def clear_finished(self):
        """Remove completed queue entries, not downloaded files."""
        old_count = len(self._items)
        self._items = [entry for entry in self._items if entry.status != 'Downloaded']
        return old_count - len(self._items)
