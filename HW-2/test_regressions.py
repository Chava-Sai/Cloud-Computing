"""Run every test with: python3 -m unittest discover -v

All expected graphs are small and deterministic; no 12K dataset or cloud
credentials are needed. Floyd-Warshall below is an independent distance oracle.
"""
import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace

import test_pagerank
import test_closeness
from analyze import load_from_local, load_from_gcs
from graphlib_hw import WebGraph, _describe, parse_links


def graph(n, edges):
    return test_pagerank.build(n, edges)


class ExistingTests(unittest.TestCase):
    """Make the original function-based tests discoverable by unittest."""


for module in (test_pagerank, test_closeness):
    for name in dir(module):
        if name.startswith('test_'):
            function = getattr(module, name)
            def run(self, function=function):
                with contextlib.redirect_stdout(io.StringIO()):
                    function()
            setattr(ExistingTests, module.__name__ + '_' + name, run)
            # unittest requires method names beginning with test.


class RegressionTests(unittest.TestCase):
    def test_nine_statistics_per_direction(self):
        stats = _describe([0, 1, 2, 3, 4, 5])
        self.assertEqual([stats[k] for k in ('average', 'median', 'max', 'min')],
                         [2.5, 2.5, 5, 0])
        self.assertEqual(stats['quintiles'], {20: 1, 40: 2, 60: 3, 80: 4, 100: 5})

    def test_parser_counts_duplicates_and_self_links(self):
        self.assertEqual(parse_links('<a HREF="0.html">x</a><a href="2.html">'
                                     '<a HREF="2.html">'), [0, 2, 2])
        g = graph(3, [(0, 0), (0, 2), (0, 2), (2, 1)])
        self.assertEqual(g.out_counts, [3, 0, 1])
        self.assertEqual(g.in_counts, [1, 1, 2])

    def test_exact_nonsymmetric_pagerank(self):
        # Solve x=.05+.85z, y=.05+.425x, z=.05+.425x+.85y.
        g = graph(3, [(0, 1), (0, 2), (1, 2), (2, 0)])
        ranks, _ = g.pagerank(threshold_pct=1e-10)
        for actual, expected in zip(ranks, [686/1769, 380/1769, 703/1769]):
            self.assertAlmostEqual(actual, expected, places=11)

    def test_exact_dangling_pagerank(self):
        # x=.075+.425y; y=.075+.85x+.425y => (20/57,37/57).
        ranks, _ = graph(2, [(0, 1)]).pagerank(threshold_pct=1e-10)
        for actual, expected in zip(ranks, [20/57, 37/57]):
            self.assertAlmostEqual(actual, expected, places=11)

    def test_literal_sum_stops_before_vector_settles(self):
        g = graph(3, [(0, 1), (0, 2), (1, 2), (2, 0)])
        ranks, iterations = g.pagerank(convergence='sum')
        self.assertEqual(iterations, 1)
        for actual, expected in zip(ranks, [1/3, 23/120, 19/40]):
            self.assertAlmostEqual(actual, expected)
        settled, iterations = g.pagerank(convergence='both')
        self.assertGreater(iterations, 1)
        self.assertGreater(sum(abs(a-b) for a,b in zip(ranks, settled)), .005)

    def test_nonconvergence_is_reported(self):
        with self.assertRaises(RuntimeError):
            graph(3, [(0, 1), (1, 2)]).pagerank(max_iter=1, threshold_pct=1e-10)

    def test_both_closeness_algorithms_against_independent_oracle(self):
        # Exhaust all 512 directed three-node graphs, including self-links,
        # disconnected graphs and sinks. Distances use a different algorithm.
        possible = [(i, j) for i in range(3) for j in range(3)]
        for mask in range(1 << len(possible)):
            edges = [e for b, e in enumerate(possible) if mask & (1 << b)]
            dist = [[0 if i == j else float('inf') for j in range(3)] for i in range(3)]
            for i, j in edges:
                dist[i][j] = min(dist[i][j], 1)
            for k in range(3):
                for i in range(3):
                    for j in range(3):
                        dist[i][j] = min(dist[i][j], dist[i][k] + dist[k][j])
            expected = []
            for i in range(3):
                ds = [dist[i][j] for j in range(3) if i != j and dist[i][j] < float('inf')]
                expected.append(len(ds)**2 / (2 * sum(ds)) if ds else 0.0)
            g = graph(3, edges + edges[:1])  # also exercise duplicate links
            for method in ('queue', 'bitmask'):
                self.assertEqual(g.closeness_centrality_all(method), expected, (mask, method))

    def test_single_node(self):
        g = graph(1, [])
        self.assertEqual(g.pagerank()[0], [1.0])
        for method in ('queue', 'bitmask'):
            self.assertEqual(g.closeness_centrality_all(method), [0.0])

    def test_empty_missing_and_invalid_pages_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                load_from_local(directory)
            Path(directory, '1.html').write_text('')
            with self.assertRaises(ValueError):
                load_from_local(directory)
            Path(directory, '0.html').write_text('<a HREF="9.html">')
            with self.assertRaises(ValueError):
                load_from_local(directory)

    def test_public_bucket_and_prefix_selection(self):
        def blob(name, body):
            return SimpleNamespace(name=name, download_as_text=lambda **kwargs: body)
        blobs = [blob('hw2/0.html', '<a HREF="1.html">'), blob('hw2/1.html', ''),
                 blob('hw2/nested/0.html', '<a HREF="999.html">')]
        fake_client = SimpleNamespace(list_blobs=lambda bucket, **kwargs: blobs)
        from unittest.mock import Mock
        client_class = Mock()
        client_class.create_anonymous_client.return_value = fake_client
        storage = SimpleNamespace(Client=client_class)
        modules = {'google': SimpleNamespace(cloud=SimpleNamespace(storage=storage)),
                   'google.cloud': SimpleNamespace(storage=storage), 'google.cloud.storage': storage,
                   'google.cloud.storage.retry': SimpleNamespace(DEFAULT_RETRY=Mock())}
        with patch.dict('sys.modules', modules):
            g, count = load_from_gcs('test-bucket', 'hw2')
        client_class.create_anonymous_client.assert_called_once_with()
        client_class.assert_not_called()
        self.assertEqual(count, 2)
        self.assertEqual(g.out_links, [[1], []])


if __name__ == '__main__':
    unittest.main()
