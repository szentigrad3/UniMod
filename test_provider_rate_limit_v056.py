"""A 429 must expose only bounded retry-after, never provider errors or URL."""
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

import provider_catalogues


class RateLimitTests(unittest.TestCase):
    def fetch429(self, raw_retry):
        class Opener:
            def open(self,request,timeout=15):
                raise HTTPError(request.full_url,429,'Too Many Requests',
                                {'Retry-After':raw_retry},None)
        with patch.object(provider_catalogues.urllib.request,'build_opener',return_value=Opener()):
            with self.assertRaises(provider_catalogues.ProviderRateLimited) as result:
                provider_catalogues.fetch_json(
                    'https://api.mod.io/v1/games?api_key=super-private-test-key')
        error=result.exception
        self.assertNotIn('super-private',str(error))
        self.assertNotIn('api.mod.io',str(error))
        return error.retry_after_seconds

    def test_retry_after_header_and_rolling_limit(self):
        self.assertEqual(self.fetch429('57'),57)
        self.assertEqual(self.fetch429('0'),60)
        self.assertEqual(self.fetch429(None),60)
        self.assertEqual(self.fetch429('99999'),3600)


if __name__=='__main__':
    unittest.main()
