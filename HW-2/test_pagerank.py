"""
test_pagerank.py -- Correctness tests for PageRank, independent of the random
12K graph. Run:  python3 test_pagerank.py

Each test builds a tiny graph BY HAND whose PageRank we can reason about
analytically, then checks our implementation against it.
"""
from graphlib_hw import WebGraph


def approx(a, b, tol=1e-6):
    return abs(a - b) < tol


def build(n, edges):
    """edges: list of (src, dst); duplicates allowed to test multiplicity."""
    g = WebGraph(n)
    out = [[] for _ in range(n)]
    for s, t in edges:
        out[s].append(t)
    for i in range(n):
        g.set_out_links(i, out[i])
    g.finalize()
    return g


def test_sum_conserved():
    # Any graph: total PageRank must stay ~1 (mass conservation).
    g = build(4, [(0, 1), (1, 2), (2, 3), (3, 0), (0, 2)])
    pr, iters = g.pagerank(threshold_pct=0.0001, max_iter=500)
    assert approx(sum(pr), 1.0, 1e-6), f"sum={sum(pr)} not 1.0"
    print(f"[PASS] total pagerank conserved (=1.0), {iters} iters")


def test_symmetric_cycle_uniform():
    # Perfectly symmetric directed cycle 0->1->2->0: every node identical,
    # so each PR must equal 1/3.
    g = build(3, [(0, 1), (1, 2), (2, 0)])
    pr, _ = g.pagerank(threshold_pct=0.0001, max_iter=500)
    for i in range(3):
        assert approx(pr[i], 1 / 3, 1e-6), f"pr[{i}]={pr[i]} != 1/3"
    print("[PASS] symmetric 3-cycle gives uniform 1/3 each")


def test_hub_gets_highest():
    # Star: 1,2,3 all point to 0. Node 0 must have the highest PR.
    g = build(4, [(1, 0), (2, 0), (3, 0)])
    pr, _ = g.pagerank(threshold_pct=0.0001, max_iter=500)
    assert pr[0] == max(pr), f"hub not highest: {pr}"
    # leaves 1,2,3 are symmetric -> equal PR
    assert approx(pr[1], pr[2]) and approx(pr[2], pr[3]), f"leaves unequal: {pr}"
    print(f"[PASS] hub node has highest pagerank ({pr[0]:.4f})")


def test_two_node_closed_formula():
    # 0<->1 mutual links. By symmetry PR(0)=PR(1)=0.5 exactly.
    g = build(2, [(0, 1), (1, 0)])
    pr, _ = g.pagerank(threshold_pct=0.0001, max_iter=500)
    assert approx(pr[0], 0.5, 1e-6) and approx(pr[1], 0.5, 1e-6), pr
    print("[PASS] 2-node mutual link -> 0.5 / 0.5")


def test_known_three_node_values():
    # Directed graph 0->1, 0->2, 1->2, 2->0. Solve the linear system by hand
    # with d=0.85, n=3, base=0.05.
    #   C(0)=2, C(1)=1, C(2)=1
    #   PR0 = 0.05 + 0.85*(PR2/1)
    #   PR1 = 0.05 + 0.85*(PR0/2)
    #   PR2 = 0.05 + 0.85*(PR0/2 + PR1/1)
    # Solving (see report) gives approximately:
    #   PR0=0.3877, PR1=0.2148, PR2=0.3975  (sum=1.0)
    g = build(3, [(0, 1), (0, 2), (1, 2), (2, 0)])
    pr, _ = g.pagerank(threshold_pct=0.00001, max_iter=2000)
    expected = [0.38779, 0.21481, 0.39740]
    for i in range(3):
        assert approx(pr[i], expected[i], 1e-3), \
            f"pr[{i}]={pr[i]:.5f} expected {expected[i]:.5f}"
    print(f"[PASS] hand-solved 3-node values match "
          f"({pr[0]:.4f},{pr[1]:.4f},{pr[2]:.4f})")


def test_multiplicity_matters():
    # 0 links to 1 twice and to 2 once. So 1 should receive 2x the share 2 does
    # from node 0. With no other in-links, PR(1) > PR(2).
    g = build(3, [(0, 1), (0, 1), (0, 2)])
    pr, _ = g.pagerank(threshold_pct=0.00001, max_iter=2000)
    assert pr[1] > pr[2], f"multiplicity ignored: pr1={pr[1]} pr2={pr[2]}"
    print(f"[PASS] duplicate links weighted correctly (pr1={pr[1]:.4f} > "
          f"pr2={pr[2]:.4f})")


def test_dangling_node_conserves_mass():
    # Node 2 has no outgoing links (dangling). Mass must still sum to 1.
    g = build(3, [(0, 1), (1, 2)])  # 2 dangles
    pr, _ = g.pagerank(threshold_pct=0.00001, max_iter=2000)
    assert approx(sum(pr), 1.0, 1e-6), f"dangling leaked mass: sum={sum(pr)}"
    print(f"[PASS] dangling node conserves total mass (sum={sum(pr):.6f})")


if __name__ == "__main__":
    print("Running PageRank correctness tests (independent of the 12K graph)\n")
    test_sum_conserved()
    test_symmetric_cycle_uniform()
    test_hub_gets_highest()
    test_two_node_closed_formula()
    test_known_three_node_values()
    test_multiplicity_matters()
    test_dangling_node_conserves_mass()
    print("\nAll PageRank tests passed.")
