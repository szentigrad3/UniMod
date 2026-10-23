"""Prevent missed newer mod.io releases and false update ordering."""
import time
import unittest
from urllib.parse import urlsplit, parse_qs
import modio_files
import modio_managed

KEY = 'local-mock-key-no-secrets'
IDENTITY = '123/77'

def raw(fid, added=100, **changes):
    row = {'id': fid, 'game_id': 123, 'mod_id': 77,
           'filename': f'mod-{fid}.zip', 'filesize': 512,
           'filehash': {'md5': 'f' * 32}, 'version': str(fid),
           'date_added': added, 'virus_status': 1, 'virus_positive': 0,
           'download': {'binary_url':
               f'https://u-456.modapi.io/v1/games/123/mods/77/files/{fid}/download/freshtoken',
               'date_expires': int(time.time()) + 3600}}
    row.update(changes)
    return row

class ReleaseOrderTests(unittest.TestCase):
    def test_request_newest_first_even_when_over_hundred_releases(self):
        seen = []
        def fetch(url, headers):
            seen.append(url)
            return {'data': [raw(50, 500), raw(90, 1000), raw(99, 800)],
                    'result_total': 120, 'result_count': 3}
        rows = modio_files.list_modfiles(IDENTITY, user_id='456', api_key=KEY, fetch=fetch)
        self.assertEqual([row['version_id'] for row in rows], ['90', '99', '50'])
        params = parse_qs(urlsplit(seen[0]).query)
        self.assertEqual(params['_sort'], ['-date_added'])
        self.assertEqual(params['_limit'], ['100'])
        self.assertNotIn(KEY, str(rows))

    def test_unverified_dates_are_not_treated_as_newer(self):
        for value in (None, True, -5, 'invalid', 99999999999999):
            with self.subTest(value=value):
                self.assertEqual(modio_files._parse_modfile(raw(90, value), '123', '77')['date_added'], 0)

    def test_exact_installed_file_date(self):
        seen = []
        def fetch(url, headers):
            seen.append(url)
            return {'id': 88, 'game_id': 123, 'mod_id': 77, 'date_added': 650}
        date = modio_files.get_modfile_date(IDENTITY, '88', user_id='456', api_key=KEY, fetch=fetch)
        self.assertEqual(date, 650)
        self.assertIn('/games/123/mods/77/files/88?', seen[0])

    def test_wrong_identity_in_file_date_response_is_rejected(self):
        baseline = {'id': 88, 'mod_id': 77, 'game_id': 123, 'date_added': 900}
        for changes in ({'mod_id': 12}, {'game_id': 999}, {'id': 9}, {'id': None}):
            with self.subTest(changes=changes), self.assertRaises(modio_files.ModioError):
                modio_files.get_modfile_date(IDENTITY, '88', user_id='456', api_key=KEY,
                    fetch=lambda *_: {**baseline, **changes})

    def test_newer_requires_publication_date_not_higher_file_id(self):
        current = {'identity': IDENTITY, 'version_id': '88'}
        listed = [
            {'provider': 'mod.io', 'identity': IDENTITY, 'version_id': '87',
             'version': 'newer', 'date_added': 1100},
            {'provider': 'mod.io', 'identity': IDENTITY, 'version_id': '100',
             'version': 'older', 'date_added': 500},
            {'provider': 'mod.io', 'identity': IDENTITY, 'version_id': '89',
             'version': 'unknown', 'date_added': 0},
            {'provider': 'mod.io', 'identity': IDENTITY, 'version_id': '88',
             'version': 'installed', 'date_added': 1000},
        ]
        rows = modio_managed.newer_release_candidates(current, listed, current_date_added=1000)
        self.assertEqual([x['available_file_id'] for x in rows], ['87', '89'])
        self.assertEqual([x['review_status'] for x in rows],
                         ['Newer publication date', 'Release order unverified'])

    def test_missing_installed_date_is_unverified_not_newer(self):
        current = {'identity': IDENTITY, 'version_id': '88'}
        other = {'provider': 'mod.io', 'identity': IDENTITY, 'version_id': '89',
                 'version': '2.0', 'date_added': 2000}
        rows = modio_managed.newer_release_candidates(current, [other], current_date_added=0)
        self.assertEqual(rows[0]['review_status'], 'Release order unverified')

    def test_wrong_game_duplicate_and_same_day_are_not_update(self):
        current = {'identity': IDENTITY, 'version_id': '88'}
        newer = {'provider': 'mod.io', 'identity': IDENTITY, 'version_id': '99',
                 'version': '2.0', 'date_added': 2000}
        rows = [dict(newer, identity='123/99'), dict(newer, provider='Other'),
                newer, newer, dict(newer, version_id='101', date_added=1000)]
        result = modio_managed.newer_release_candidates(current, rows, current_date_added=1000)
        self.assertEqual([x['available_file_id'] for x in result], ['99'])

if __name__ == '__main__':
    unittest.main()
