"""End-to-end offline mod.io self-test: simulated API and ZIP downloads only.

Uses a temporary fake game and receipts, never the user's games, credentials,
or network connection. Failures cause a nonzero exit status.
"""
import hashlib
import io
import json
import tempfile
import time
import zipfile
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlsplit


def _zip_payload(version):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w') as z:
        z.writestr('Example/manifest.json', json.dumps({
            'UniqueID': 'SelfTest.Modio', 'Name': 'UniMod Selftest', 'Version': version}))
        z.writestr('Example/version.txt', version)
    return stream.getvalue()


class _Reply(io.BytesIO):
    def __init__(self, url, data):
        super().__init__(data)
        self.url, self.headers = url, {}

    def geturl(self):
        return self.url


class _Opener:
    def __init__(self, url, data):
        self.url, self.data = url, data

    def open(self, request, timeout=30):
        return _Reply(self.url, self.data)


def run():
    """Exercise download, verified staging, install, update, backup and refusal."""
    import modio_files
    import modio_managed
    import provider_downloads
    import provider_staging
    import unimod

    user_id = '456'
    key = 'offline-modio-selftest-only'
    identity = '123/77'
    releases = [(_zip_payload('1.0.0'), '301', 'Example-v1.zip', 1000),
                (_zip_payload('1.1.0'), '302', 'Example-v2.zip', 2000),
                (_zip_payload('1.2.0'), '303', 'Example-v3.zip', 3000)]
    by_id = {r[1]: r for r in releases}

    def url(fid):
        return f'https://u-456.modapi.io/v1/games/123/mods/77/files/{fid}/download/OfflineToken123'

    def metadata(release):
        body, fid, name, when = release
        return {'id': int(fid), 'mod_id': 77, 'game_id': 123,
                'filename': name, 'filesize': len(body), 'version': '1.'+str(int(fid)-301)+'.0',
                'date_added': when, 'filehash': {'md5': hashlib.md5(body).hexdigest()},
                'virus_status': 1, 'virus_positive': 0,
                'download': {'binary_url': url(fid),
                             'date_expires': int(time.time())+600}}

    def fetch(address, headers):
        endpoint = urlsplit(address).path
        if endpoint == '/v1/games/123/mods/77/files':
            return {'data': [metadata(item) for item in reversed(releases)]}
        fid = endpoint.rsplit('/', 1)[-1]
        if fid in by_id:
            return metadata(by_id[fid])
        raise AssertionError('Unexpected provider API endpoint')

    with tempfile.TemporaryDirectory(prefix='unimod-modio-selftest-') as temp:
        root = Path(temp)
        inbox = root/'inbox'
        inbox.mkdir()
        game_root = root/'Stardew'
        mods = game_root/'Mods'
        mods.mkdir(parents=True)
        game = {'name': 'Stardew Valley', 'kind': 'smapi', 'root': str(game_root)}
        stage_file = root/'stage.json'
        install_file = root/'installed.json'
        with patch.object(unimod, 'APP', root/'app'), patch.object(unimod, 'INSTALL_RECEIPTS', install_file):
            listed = modio_files.list_modfiles(identity, user_id=user_id, api_key=key, fetch=fetch)
            assert [item['version_id'] for item in listed] == ['303', '302', '301'], 'Wrong mod.io file order'
            results = {}

            def stage(fid, *, tampered=False):
                selected = next(item for item in listed if item['version_id'] == fid)
                body = by_id[fid][0]
                if tampered:
                    body += b'tampered'
                return provider_staging.stage_download(
                    selected, inbox, stage_file, game_root=str(game_root),
                    downloader=lambda record, directory: modio_files.download_selected(
                        record, directory, user_id=user_id, api_key=key, fetch=fetch,
                        opener=_Opener(url(fid), body)))

            def receipt(fid):
                return next(row for row in provider_staging.read_staged(stage_file)
                            if row['version_id'] == fid)

            stage('301')
            first_receipt = receipt('301')
            assert provider_staging.inspect_receipt(first_receipt, game_root=str(game_root)).is_file()
            assert unimod.provider_install_preflight(game, first_receipt)['status'] == 'Install new'
            assert unimod.provider_install_reviewed(game, first_receipt)['action'] == 'installed'
            installed = mods/'Example'
            assert (installed/'version.txt').read_text() == '1.0.0'
            results['installed'] = 1

            stage('302')
            second_receipt = receipt('302')
            assert unimod.provider_install_preflight(game, second_receipt)['status'] == 'Update existing'
            updated = unimod.provider_install_reviewed(game, second_receipt)
            assert updated['action'] == 'updated' and not updated.get('history_warning')
            assert (installed/'version.txt').read_text() == '1.1.0'
            assert (Path(updated['backup'])/'version.txt').read_text() == '1.0.0'
            tracked = modio_managed.managed_installs(game, unimod.read_receipts(), game_id='123')
            assert len(tracked) == 1 and tracked[0]['version_id'] == '302'
            results['updated'] = 1
            results['backups'] = 1

            # The same already-reviewed bytes must still match their receipt.
            with Path(second_receipt['archive']).open('ab') as output:
                output.write(b'changed-after-download')
            assert unimod.provider_install_preflight(game, second_receipt)['status'] == 'Blocked'
            assert (installed/'version.txt').read_text() == '1.1.0'
            results['tamper_refused'] = 1

            other_root = root/'WrongGame'
            (other_root/'Mods').mkdir(parents=True)
            assert unimod.provider_install_preflight(
                dict(game, root=str(other_root)), first_receipt)['status'] == 'Blocked'
            results['wrong_game_refused'] = 1

            # A corrupted transfer must never appear in the inbox or affect the game.
            try:
                stage('303', tampered=True)
            except provider_downloads.DownloadError:
                pass
            else:
                raise AssertionError('Mismatched mod.io download checksum accepted')
            assert not (inbox/'Example-v3.zip').exists()
            assert (installed/'version.txt').read_text() == '1.1.0'
            results['bad_download_refused'] = 1

            stage('303')
            third_receipt = receipt('303')
            assert unimod.provider_install_preflight(game, third_receipt)['status'] == 'Update existing'
            with patch.object(unimod.shutil, 'copytree', side_effect=OSError('interrupted update simulation')):
                try:
                    unimod.provider_install_reviewed(game, third_receipt)
                except OSError:
                    pass
                else:
                    raise AssertionError('Interrupted update unexpectedly succeeded')
            assert (installed/'version.txt').read_text() == '1.1.0', 'Previous mod not restored'
            tracked = modio_managed.managed_installs(game, unimod.read_receipts(), game_id='123')
            assert len(tracked) == 1 and tracked[0]['version_id'] == '302'
            results['failed_update_restored'] = 1

            text = stage_file.read_text() + install_file.read_text()
            assert key not in text and '/download/OfflineToken123' not in text
            results['secrets_not_persisted'] = 1
    return results


if __name__ == '__main__':
    run()
    print('UNIMOD_MODIO_SELFTEST_OK (offline, temporary files only)')
