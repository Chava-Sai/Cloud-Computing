"""Offline tests of actual SDK pagination and download failure handling.

These tests require the project's Google Storage dependency. Requests are
mocked, so no bucket, network connection, or credentials are needed.
"""
import contextlib
import io
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from analyze import load_from_gcs, load_with_transfer_manager

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

    def test_parallel_downloads_finish_before_parsing_and_match_graph(self):
        from google.cloud.storage import transfer_manager
        from graphlib_hw import parse_links
        # 101 files force two batches. Node 0 links to 1 twice and to itself;
        # node 1 links to 100, which has no outgoing links.
        ids = list(range(101))
        blobs = {i: SimpleNamespace(name=f"hw2/{i}.html") for i in ids}
        batches = []
        paths = []

        def download(pairs, **kwargs):
            self.assertEqual(kwargs['worker_type'], transfer_manager.THREAD)
            self.assertEqual(kwargs['max_workers'], 8)
            batches.append(len(pairs))
            for blob, filename in pairs:
                paths.append(Path(filename))
                node = int(Path(filename).stem)
                body = ('<a HREF="1.html"><a HREF="1.html"><a HREF="0.html">'
                        if node == 0 else '<a HREF="100.html">' if node == 1 else '')
                Path(filename).write_text(body, encoding='utf-8')
            return [None] * len(pairs)

        def parse(text):
            self.assertEqual(batches, [100, 1], 'Parsing started before all downloads finished')
            return parse_links(text)

        with patch.object(transfer_manager, 'download_many', side_effect=download), \
             patch('analyze.parse_links', side_effect=parse), \
             contextlib.redirect_stdout(io.StringIO()):
            graph = load_with_transfer_manager(blobs, ids, 8, (10, 60), None)
        self.assertEqual(graph.n, 101)
        self.assertEqual(graph.out_links[0], [1, 1, 0])
        self.assertEqual(graph.out_links[1], [100])
        self.assertEqual(sum(graph.out_counts), 4)
        self.assertTrue(all(not path.exists() for path in paths))

    def test_parallel_failure_removes_files_and_does_not_parse(self):
        from google.cloud.storage import transfer_manager
        paths = []

        def download(pairs, **kwargs):
            for blob, filename in pairs:
                paths.append(Path(filename))
                Path(filename).write_text('partial data')
            return [TimeoutError('read timed out')]

        with patch.object(transfer_manager, 'download_many', side_effect=download), \
             patch('analyze.load_from_local') as parse, \
             contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(RuntimeError, 'hw2/0.html'):
                load_with_transfer_manager({0: SimpleNamespace(name='hw2/0.html')},
                                           [0], 8, (10, 60), None)
        parse.assert_not_called()
        self.assertTrue(all(not path.exists() for path in paths))


if __name__ == '__main__':
    unittest.main()
