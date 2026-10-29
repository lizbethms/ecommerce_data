"""Cada estructura frente a una referencia ingenua o una propiedad conocida."""
import random
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.structures.bloom import BloomFilter
from src.structures.bplus_tree import BPlusTree
from src.structures.count_min import CountMinSketch, WindowedCMS
from src.structures.graph import WeightedGraph, louvain, modularity, pagerank
from src.structures.hash_table import HashTable
from src.structures.heap import MinHeap
from src.structures.hnsw import HNSW
from src.structures.kd_tree import KDTree, squared_distance
from src.structures.lru import LRUCache
from src.structures.minhash_lsh import LSHIndex, MinHash, jaccard
from src.structures.sorting import binary_search, merge_sort
from src.structures.topk import top_k
from src.structures.trie import Trie

RNG = random.Random(7)


class TestStructures(unittest.TestCase):
    def test_merge_sort_and_binary_search(self):
        data = [RNG.randint(0, 50) for _ in range(500)]
        pairs = list(enumerate(data))
        self.assertEqual(merge_sort(pairs, key=lambda p: p[1]), sorted(pairs, key=lambda p: p[1]))
        ordered = merge_sort(data)
        for value in range(-2, 55):
            i = binary_search(ordered, value)
            self.assertEqual(i >= 0, value in data)
            if i >= 0:
                self.assertEqual(ordered[i], value)

    def test_heap_and_topk(self):
        heap = MinHeap()
        data = [RNG.random() for _ in range(300)]
        for x in data:
            heap.push(x, x)
        self.assertEqual([heap.pop()[0] for _ in range(len(data))], sorted(data))
        heap.push(1, 'a'), heap.push(1, 'b'), heap.push(0, 'c')
        self.assertEqual([heap.pop()[1] for _ in range(3)], ['c', 'a', 'b'])  # estable
        self.assertEqual(top_k(data, 5), sorted(data, reverse=True)[:5])

    def test_hash_table(self):
        table, reference = HashTable(), {}
        for _ in range(3000):
            key = RNG.randint(0, 800)
            if RNG.random() < 0.3 and key in reference:
                del table[key], reference[key]
            else:
                table[key] = reference[key] = RNG.random()
        self.assertEqual(len(table), len(reference))
        self.assertEqual(dict(table.items()), reference)

    def test_lru(self):
        cache = LRUCache(2)
        cache.put('a', 1), cache.put('b', 2)
        cache.get('a')
        cache.put('c', 3)  # expulsa 'b'
        self.assertIsNone(cache.get('b'))
        self.assertEqual((cache.get('a'), cache.get('c')), (1, 3))

    def test_bplus_tree(self):
        tree = BPlusTree(order=4)
        items = [(RNG.randint(0, 200), i) for i in range(1000)]
        for key, value in items:
            tree.insert(key, value)
        tree.remove(items[0][0], items[0][1])
        alive = items[1:]
        expected = sorted((k, v) for k, v in alive if 50 <= k <= 120)
        self.assertEqual(sorted(tree.range(50, 120)), expected)
        self.assertEqual(sorted(tree.search(77)), sorted(v for k, v in alive if k == 77))
        self.assertEqual([k for k, _ in tree.range()], sorted(k for k, _ in alive))
        self.assertGreater(tree.height(), 2)

    def test_kd_tree_matches_brute_force(self):
        points = [(i, [RNG.random() for _ in range(4)]) for i in range(400)]
        tree = KDTree(points)
        for _ in range(20):
            q = [RNG.random() for _ in range(4)]
            brute = sorted(points, key=lambda p: squared_distance(q, p[1]))[:5]
            self.assertEqual([k for k, _ in tree.knn(q, 5)], [k for k, _ in brute])

    def test_kd_tree_validates_vectors_and_freezes_points(self):
        with self.assertRaisesRegex(ValueError, 'Dimensiones incompatibles'):
            squared_distance([0, 1], [0])
        with self.assertRaisesRegex(ValueError, 'Dimensión inválida'):
            KDTree([('a', [0, 1]), ('b', [2])])
        with self.assertRaisesRegex(ValueError, 'finitos'):
            KDTree([('a', [0, float('nan')])])
        with self.assertRaisesRegex(ValueError, 'ID duplicado'):
            KDTree([('a', [0]), ('a', [1])])
        vector = [0.0, 0.0]
        tree = KDTree([('a', vector), ('b', [2.0, 2.0])])
        vector[:] = [100.0, 100.0]
        self.assertEqual(tree.knn([0.0, 0.0], 1)[0][0], 'a')
        with self.assertRaisesRegex(ValueError, 'Dimensión inválida'):
            tree.knn([0.0], 1)

    def test_kd_tree_ties_are_deterministic(self):
        points = [('z', [1.0, 0.0]), ('a', [-1.0, 0.0]), ('m', [0.0, 1.0])]
        expected = ['a', 'm']
        self.assertEqual([key for key, _ in KDTree(points).knn([0.0, 0.0], 2)], expected)
        self.assertEqual([key for key, _ in KDTree(reversed(points)).knn([0.0, 0.0], 2)], expected)

    def test_kd_tree_query_metrics(self):
        points = [(i, [float(i), float(i % 3)]) for i in range(100)]
        neighbors, stats = KDTree(points).knn([20.1, 2.0], 4, with_stats=True)
        self.assertEqual(len(neighbors), 4)
        self.assertEqual(stats['total_nodes'], len(points))
        self.assertLessEqual(stats['nodes_visited'], stats['total_nodes'])
        self.assertLessEqual(stats['distance_evaluations'], stats['nodes_visited'])
        self.assertGreater(stats['branches_pruned'], 0)
        self.assertAlmostEqual(stats['visited_fraction'], stats['nodes_visited'] / len(points))

    def test_hnsw_recall(self):
        points = [(i, [RNG.random() for _ in range(8)]) for i in range(600)]
        index = HNSW(M=8, ef_construction=64, ef_search=64, seed=1)
        for key, vector in points:
            index.insert(key, vector)
        hits = 0
        for _ in range(30):
            q = [RNG.random() for _ in range(8)]
            exact = {k for k, _ in sorted(points, key=lambda p: squared_distance(q, p[1]))[:10]}
            hits += len(exact & {k for k, _ in index.search(q, 10)})
        self.assertGreater(hits / 300, 0.85)

    def test_bloom_has_no_false_negatives(self):
        bloom = BloomFilter(500, 0.01)
        keys = [f'k{i}' for i in range(500)]
        for key in keys:
            bloom.add(key)
        self.assertTrue(all(key in bloom for key in keys))
        false_positives = sum(f'absent{i}' in bloom for i in range(5000)) / 5000
        self.assertLess(false_positives, 0.05)

    def test_bloom_validation_bulk_clear_and_stats(self):
        for capacity, rate in ((0, 0.01), (True, 0.01), (10, 0), (10, 1), (10, float('nan'))):
            with self.assertRaises(ValueError):
                BloomFilter(capacity, rate)
        bloom = BloomFilter(100, 0.01)
        self.assertEqual(bloom.update(['a', 'b', 'c']), 3)
        self.assertEqual(len(bloom), 3)
        self.assertTrue(all(key in bloom for key in ('a', 'b', 'c')))
        stats = bloom.stats()
        self.assertEqual(stats['inserted'], 3)
        self.assertGreater(stats['set_bits'], 0)
        self.assertGreater(stats['fill_ratio'], 0)
        self.assertLess(stats['fill_ratio'], 1)
        self.assertFalse(stats['capacity_exceeded'])
        self.assertFalse(stats['insertion_calls_exceeded'])
        self.assertAlmostEqual(stats['observed_fp_estimate'], bloom.observed_fp_estimate())
        bloom.clear()
        self.assertEqual(len(bloom), 0)
        self.assertEqual(bloom.set_bits(), 0)
        self.assertFalse(any(key in bloom for key in ('a', 'b', 'c')))

    def test_bloom_hash_positions_are_distinct_and_type_aware(self):
        bloom = BloomFilter(100, 0.01)
        positions = list(bloom._positions('clave'))
        self.assertEqual(len(positions), bloom.k)
        self.assertEqual(len(set(positions)), bloom.k)
        self.assertNotEqual(list(bloom._positions(1)), list(bloom._positions('1')))
        self.assertNotEqual(list(bloom._positions(b'1')), list(bloom._positions('1')))

    def test_count_min_never_underestimates(self):
        sketch, exact = CountMinSketch(64, 4), {}
        for _ in range(3000):
            key = RNG.randint(0, 300)
            sketch.add(key)
            exact[key] = exact.get(key, 0) + 1
        self.assertTrue(all(sketch.estimate(k) >= v for k, v in exact.items()))

    def test_windowed_cms_expires(self):
        window = WindowedCMS(60, slots=6, width=256)
        for t in range(0, 30):
            window.add('user', t)
        self.assertGreaterEqual(window.estimate('user', 29), 30)
        self.assertEqual(window.estimate('user', 200), 0)

    def test_minhash_estimates_jaccard(self):
        minhash = MinHash(128, seed=3)
        a, b = set(range(0, 100)), set(range(50, 150))
        estimate = MinHash.estimate(minhash.signature(a), minhash.signature(b))
        self.assertAlmostEqual(estimate, jaccard(a, b), delta=0.12)
        lsh = LSHIndex(bands=32, rows=4)
        lsh.insert('a', minhash.signature(a))
        lsh.insert('a2', minhash.signature(a | {1000}))
        lsh.insert('z', minhash.signature(set(range(5000, 5100))))
        self.assertEqual([k for k, _ in lsh.query('a')], ['a2'])

    def test_pagerank_and_louvain(self):
        graph = WeightedGraph()
        for group in (range(0, 6), range(6, 12)):
            for u in group:
                for v in group:
                    if u < v:
                        graph.add_edge(u, v, 3)
        graph.add_edge(0, 6, 1)
        rank = pagerank(graph)
        self.assertAlmostEqual(sum(rank.values()), 1.0, places=6)
        self.assertEqual(max(rank, key=rank.get) in (0, 6), True)
        partition = louvain(graph)
        self.assertEqual(len(set(partition.values())), 2)
        self.assertEqual(len({partition[u] for u in range(6)}), 1)
        self.assertGreater(modularity(graph, partition), 0.4)

    def test_trie(self):
        trie = Trie()
        trie.insert('samsung', 5, 'p1'), trie.insert('samsonite', 9, 'p2'), trie.insert('apple', 7, 'p3')
        self.assertEqual([t for t, *_ in trie.complete('sam', 5)], ['samsonite', 'samsung'])
        trie.add_weight('samsung', 10)
        self.assertEqual(trie.complete('s', 1)[0][0], 'samsung')
        self.assertEqual(trie.complete('x'), [])


if __name__ == '__main__':
    unittest.main()
