"""Regression tests for UniMod's owner-only local single-instance bridge."""
import os
import socket
import stat
import tempfile
import unittest
from pathlib import Path

from instance_bridge import SingleInstance, send_to_running
from nexus_queue import NexusDownloadQueue

NXM = 'nxm://stardewvalley/mods/3753/files/123456?key=token12345&expires=9999999999&user_id=17'

class SingleInstanceTests(unittest.TestCase):
    def test_forward_nxm_only_to_existing_owner(self):
        with tempfile.TemporaryDirectory() as tmp:
            first=SingleInstance(Path(tmp)/'run')
            self.assertTrue(first.acquire())
            first.start()
            try:
                self.assertTrue(send_to_running(first.folder, NXM))
                action, value=first.events.get(timeout=2)
                self.assertEqual(action,'nxm')
                self.assertEqual(value,NXM)
                self.assertTrue(send_to_running(first.folder))
                self.assertEqual(first.events.get(timeout=2),('present',None))
                self.assertEqual(stat.S_IMODE(first.sockpath.stat().st_mode),0o600)
                self.assertEqual(stat.S_IMODE(first.folder.stat().st_mode),0o700)
                second=SingleInstance(first.folder)
                self.assertFalse(second.acquire())
                self.assertNotIn('token12345', (first.folder/'instance.lock').read_text())
                self.assertEqual(sorted(p.name for p in first.folder.iterdir()), ['instance.lock','instance.sock'])
            finally: first.close()
            self.assertFalse((first.folder/'instance.sock').exists())
            # Closing releases ownership for the next app launch.
            again=SingleInstance(first.folder)
            self.assertTrue(again.acquire());again.close()

    def test_invalid_and_oversized_messages_are_not_forwarded(self):
        with tempfile.TemporaryDirectory() as tmp:
            first=SingleInstance(Path(tmp)/'run')
            first.acquire();first.start()
            try:
                with self.assertRaises(ValueError):
                    send_to_running(first.folder, 'https://example.com/file.zip')
                with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as client:
                    client.settimeout(2);client.connect(str(first.sockpath))
                    client.sendall(b'{"action":"nxm","uri":"wrong"}\n')
                    self.assertEqual(client.recv(128),b'INVALID\n')
                self.assertTrue(first.events.empty())
                self.assertTrue(send_to_running(first.folder, NXM))
            finally: first.close()

    def test_session_only_queue_bulk_operations(self):
        q=NexusDownloadQueue()
        a=q.add_nxm(NXM)
        b=q.add_file('stardewvalley','123','321','sample.zip')
        self.assertEqual(len(q.ready_items()),2)
        q.mark_downloaded(a,Path('/tmp/sample.zip'))
        self.assertEqual(len(q.ready_items()),1)
        self.assertEqual(q.clear_finished(),1)
        self.assertEqual(q.get(a.id),None)
        self.assertEqual(q.get(b.id),b)
        self.assertNotIn('token12345',repr(q.public_rows()))

if __name__=='__main__':unittest.main()
