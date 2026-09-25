"""
test_closeness.py -- Correctness tests for closeness centrality, independent
of the random 12K graph. Run:  python3 test_closeness.py

We use the Wasserman-Faust normalized closeness (same as the implementation):

    C(u) = ( reached / (N-1) ) * ( reached / sum_of_distances )

where `reached` is the number of OTHER nodes reachable from u and
sum_of_distances is the total shortest-path distance to those nodes.
Each tiny graph below has a closeness value we can compute by hand.
"""
from graphlib_hw import WebGraph


def approx(a, b, tol=1e-9):
    return abs(a - b) < tol


def build(n, edges):
    g = WebGraph(n)
    out = [[] for _ in range(n)]
    for s, t in edges:
        out[s].append(t)
    for i in range(n):
        g.set_out_links(i, out[i])
    g.finalize()
    return g


def test_directed_line():
    # 0->1->2->3 (a directed path).
    # From 0: distances 1,2,3 to nodes 1,2,3. reached=3, sumdist=6, N=4.
    #   C(0) = (3/3)*(3/6) = 0.5
    # From 3: reaches nobody -> C(3)=0.
    g = build(4, [(0, 1), (1, 2), (2, 3)])
    c = g.closeness_centrality_all()
    assert approx(c[0], 0.5), f"C(0)={c[0]} != 0.5"
    assert approx(c[3], 0.0), f"C(3)={c[3]} != 0.0"
    # Node 0 reaches the most at least cost -> should be the global best.
    best, score, _ = g.best_closeness()
    assert best == 0, f"best node {best} != 0"
    print(f"[PASS] directed line: C(0)=0.5, C(3)=0, best=0")


def test_star_center_best():
    # Center 0 -> 1,2,3 and each leaf -> 0.
    # From 0: dist 1 to each of 3 leaves. reached=3, sumdist=3, N=4.
    #   C(0) = (3/3)*(3/3) = 1.0  (maximum possible)
    g = build(4, [(0, 1), (0, 2), (0, 3), (1, 0), (2, 0), (3, 0)])
    c = g.closeness_centrality_all()
    assert approx(c[0], 1.0), f"C(0)={c[0]} != 1.0"
    best, score, _ = g.best_closeness()
    assert best == 0 and approx(score, 1.0), f"best={best}, score={score}"
    print(f"[PASS] star: center closeness = 1.0 and is the best node")


def test_undirected_triangle_uniform():
    # Fully connected triangle (both directions). Every node reaches the other
    # two at distance 1. reached=2, sumdist=2, N=3 -> C = (2/2)*(2/2)=1.0 each.
    g = build(3, [(0, 1), (1, 0), (0, 2), (2, 0), (1, 2), (2, 1)])
    c = g.closeness_centrality_all()
    for i in range(3):
        assert approx(c[i], 1.0), f"C({i})={c[i]} != 1.0"
    print("[PASS] symmetric triangle: all closeness = 1.0")


def test_isolated_node_zero():
    # Node 2 has no edges at all. Its closeness must be 0.
    g = build(3, [(0, 1), (1, 0)])
    c = g.closeness_centrality_all()
    assert approx(c[2], 0.0), f"C(2)={c[2]} != 0.0"
    print("[PASS] isolated node closeness = 0.0")


def test_known_middle_value():
    # Graph: 0->1, 1->2, 0->2  (0 reaches 1 at 1, 2 at 1). reached=2,
    # sumdist=2, N=3 -> C(0) = (2/2)*(2/2) = 1.0.
    # From 1: reaches 2 at dist 1. reached=1, sumdist=1 -> C(1)=(1/2)*(1/1)=0.5
    g = build(3, [(0, 1), (1, 2), (0, 2)])
    c = g.closeness_centrality_all()
    assert approx(c[0], 1.0), f"C(0)={c[0]} != 1.0"
    assert approx(c[1], 0.5), f"C(1)={c[1]} != 0.5"
    print(f"[PASS] known middle values: C(0)=1.0, C(1)=0.5")


def test_multiplicity_ignored_for_distance():
    # Duplicate edge 0->1 twice should NOT change distances/closeness vs single.
    g1 = build(3, [(0, 1), (1, 2)])
    g2 = build(3, [(0, 1), (0, 1), (1, 2)])
    c1 = g1.closeness_centrality_all()
    c2 = g2.closeness_centrality_all()
    for i in range(3):
        assert approx(c1[i], c2[i]), f"closeness changed by dup edge at {i}"
    print("[PASS] duplicate edges don't affect closeness distances")


if __name__ == "__main__":
    print("Running closeness centrality tests (independent of the 12K graph)\n")
    test_directed_line()
    test_star_center_best()
    test_undirected_triangle_uniform()
    test_isolated_node_zero()
    test_known_middle_value()
    test_multiplicity_ignored_for_distance()
    print("\nAll closeness centrality tests passed.")
