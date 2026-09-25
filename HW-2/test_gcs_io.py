"""Offline tests of actual SDK pagination and download failure handling.

These tests require the project's Google Storage dependency. Requests are
mocked, so no bucket, network connection, or credentials are needed.
"""
import contextlib
import io
import unittest
from unittest.mock import patch

from analyze import load_from_gcs

try:
    from google.cloud import storage
except ImportError:
    storage = None


@unittest.skipIf(storage is None, 'Install requirements.txt to test SDK pagination')
class StorageLoadingTests(unittest.TestCase):
    def test_partial_metadata_listing_follows_next_page(self):
        client = storage.Client.create_anonymous_client()
        responses = [
            {'items': [{'name': 'hw2/0.html', 'generation': '100'}],
             'nextPageToken': 'second-page'},
            {'items': [{'name': 'hw2/1.html', 'generation': '200'}]},
        ]
        generations = []

        def download(blob, **kwargs):
            generations.append((blob.name, blob.generation))
            return '<a HREF="1.html">' if blob.name == 'hw2/0.html' else ''

        with patch.object(storage.Client, 'create_anonymous_client', return_value=client), \
             patch.object(client._connection, 'api_request', side_effect=responses) as requests, \
             patch.object(storage.Blob, 'download_as_text', download), \
             contextlib.redirect_stdout(io.StringIO()):
            graph, count = load_from_gcs('test-bucket', 'hw2/')
        self.assertEqual(count, 2)
        self.assertEqual(graph.out_links, [[1], []])
        self.assertEqual(generations, [('hw2/0.html', 100), ('hw2/1.html', 200)])
        self.assertEqual(requests.call_count, 2)
        self.assertEqual(requests.call_args_list[1].kwargs['query_params']['pageToken'],
                         'second-page')
        selector = requests.call_args_list[0].kwargs['query_params']['fields']
        self.assertIn('nextPageToken', selector)

    def test_failed_download_never_returns_partial_graph(self):
        client = storage.Client.create_anonymous_client()
        response = {'items': [{'name': 'hw2/0.html', 'generation': '100'}]}
        with patch.object(storage.Client, 'create_anonymous_client', return_value=client), \
             patch.object(client._connection, 'api_request', return_value=response), \
             patch.object(storage.Blob, 'download_as_text', side_effect=TimeoutError('read timeout')), \
             contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(RuntimeError, 'hw2/0.html.*0/1 pages read') as caught:
                load_from_gcs('test-bucket', 'hw2/')
        self.assertIsInstance(caught.exception.__cause__, TimeoutError)


if __name__ == '__main__':
    unittest.main()
