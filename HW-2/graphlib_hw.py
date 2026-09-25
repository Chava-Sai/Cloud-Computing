"""
graphlib_hw.py  --  Hand-written graph analysis for CS528 HW2.

NO external graph libraries are used (no networkx, igraph, graph-tool, etc.).
Only the Python standard library. The graph, PageRank, statistics, and
closeness centrality are all implemented from scratch here.

Data model
----------
Each generated file "i.html" contains zero or more <a HREF="j.html"> tags.
The generator can emit the SAME target more than once in a file and can emit
self-links (i -> i). We preserve that faithfully:

    out_links[i]  -> list of targets j (WITH duplicates, in order encountered)
    C(i)          -> len(out_links[i])  == number of <a> slots in file i
    in_counts[j]  -> total number of link slots pointing at j (WITH duplicates)

For PageRank we use the multiplicity-aware form: a page i that links to j
k times contributes k * PR(i)/C(i) to j. This is exactly the classic
formula applied to the raw link slots the generator produced.

Dangling nodes (C(i) == 0) are possible (a file may contain no links).
Their PageRank mass is redistributed uniformly across all nodes each
iteration so that no rank "leaks" out of the system.
"""

import re
import math
import statistics
from collections import deque

# Matches  <a HREF="123.html">  case-insensitively on the tag and attribute.
# The generator writes  <a HREF="  exactly, but we stay tolerant of case/space.
_LINK_RE = re.compile(r'<a\s+href\s*=\s*"(\d+)\.html"', re.IGNORECASE)


def parse_links(text):
    """Return a list of integer targets found in one file's text (with dups)."""
    return [int(m) for m in _LINK_RE.findall(text)]


class WebGraph:
    """A directed multigraph over node ids 0..n-1 built from parsed link lists."""

    def __init__(self, num_nodes):
        if num_nodes < 1:
            raise ValueError("The graph must contain at least one page")
        self.n = num_nodes
        # forward adjacency WITH duplicates preserved
        self.out_links = [[] for _ in range(num_nodes)]
        # reverse adjacency as (source, multiplicity) so PageRank is efficient.
        # built lazily by finalize()
        self.in_edges = None          # list[ list[ (src, mult) ] ]
        self.in_counts = None         # total in-slots per node (with dups)
        self.out_counts = None        # C(i) with dups == len(out_links[i])

    def set_out_links(self, node, targets):
        """Record the outgoing links (a list of ints, dups allowed) for `node`."""
        if not 0 <= node < self.n:
            raise ValueError(f"Invalid source page: {node}")
        targets = list(targets)
        if any(not 0 <= target < self.n for target in targets):
            raise ValueError(f"Page {node}.html links to a page outside the dataset")
        self.out_links[node] = targets

    def finalize(self):
        """Precompute reverse adjacency and degree counts. Call once after load."""
        n = self.n
        self.out_counts = [len(self.out_links[i]) for i in range(n)]
        self.in_counts = [0] * n

        # Build reverse adjacency collapsing multiplicity: for each source i,
        # count how many times it points to each target, then store (i, mult).
        rev = [dict() for _ in range(n)]
        for i in range(n):
            for j in self.out_links[i]:
                rev[j][i] = rev[j].get(i, 0) + 1
                self.in_counts[j] += 1
        self.in_edges = [list(d.items()) for d in rev]

    # ----------------------------------------------------------------- stats
    def link_statistics(self):
        """Average, median, max, min, and quintiles for in- and out-links."""
        return {
            "incoming": _describe(self.in_counts),
            "outgoing": _describe(self.out_counts),
        }

    # -------------------------------------------------------------- pagerank
    def pagerank(self, damping=0.85, threshold_pct=0.5, max_iter=1000,
                 verbose=False, convergence="both"):
        """
        Iterative PageRank with the assignment's exact formula:

            PR(A) = (1-d)/n + d * ( PR(T1)/C(T1) + ... + PR(Tn)/C(Tn) )

        with d = 0.85 (so (1-d) = 0.15). Dangling mass (from nodes with
        C=0) is spread uniformly so total rank is conserved.

        Convergence criterion
        ---------------------
        "sum" implements the literal scalar-sum stopping rule in the prompt:
            abs(sum(new) - sum(old)) / sum(old) * 100 <= threshold_pct
        With uniform initialization and dangling redistribution, this normally
        stops after ONE iteration even if individual ranks are still moving.
        "l1" tests sum(abs(new[i]-old[i])) / sum(new) * 100 instead.
        "both" (default) requires both tests, retaining the scalar-sum check
        and adding a safeguard for individual ranks. This is an explicit
        implementation choice, not a claim about the professor's intent.

        Returns (pr_list, iterations_run).
        """
        n = self.n
        if not math.isfinite(damping) or not 0 <= damping < 1:
            raise ValueError("damping must be finite and in [0, 1)")
        if not math.isfinite(threshold_pct) or threshold_pct <= 0:
            raise ValueError("threshold_pct must be positive and finite")
        if max_iter < 1:
            raise ValueError("max_iter must be positive")
        if convergence not in ("sum", "l1", "both"):
            raise ValueError("convergence must be sum, l1, or both")
        d = damping
        base = (1.0 - d) / n
        pr = [1.0 / n] * n           # start uniform; total = 1.0

        dangling = [i for i in range(n) if self.out_counts[i] == 0]

        iterations = 0
        while True:
            iterations += 1

            # rank leaked by dangling nodes, spread uniformly to everyone
            dangling_mass = 0.0
            for i in dangling:
                dangling_mass += pr[i]
            dangling_share = d * dangling_mass / n

            new_pr = [base + dangling_share] * n
            # push contributions along edges using reverse adjacency
            for a in range(n):
                s = 0.0
                for (t, mult) in self.in_edges[a]:
                    ct = self.out_counts[t]
                    if ct:  # t has outgoing links
                        s += mult * pr[t] / ct
                new_pr[a] += d * s

            # L1 movement of the rank vector, as a percentage of total rank
            l1 = 0.0
            for i in range(n):
                l1 += abs(new_pr[i] - pr[i])
            cur_sum = sum(new_pr)
            change_pct = (l1 / cur_sum * 100.0) if cur_sum else 0.0
            old_sum = sum(pr)
            sum_change_pct = abs(cur_sum - old_sum) / old_sum * 100.0

            pr = new_pr
            if verbose:
                print(f"  iter {iterations:3d}  sum={cur_sum:.6f}  "
                      f"sum-change={sum_change_pct:.6f}%  L1-change={change_pct:.4f}%")
            sum_ok = sum_change_pct <= threshold_pct
            l1_ok = change_pct <= threshold_pct
            if ((convergence == "sum" and sum_ok)
                    or (convergence == "l1" and l1_ok)
                    or (convergence == "both" and sum_ok and l1_ok)):
                break
            if iterations >= max_iter:
                raise RuntimeError(f"PageRank did not converge in {max_iter} iterations")

        return pr, iterations

    def top_k_pagerank(self, pr, k=5):
        """Return list of (node, score) for the top-k pages by PageRank."""
        order = sorted(range(self.n), key=lambda i: pr[i], reverse=True)
        return [(i, pr[i]) for i in order[:k]]

    # ---------------------------------------------------- closeness centrality
    def closeness_centrality_all(self, method="auto"):
        """
        Closeness centrality for every node using hand-written BFS on the
        directed graph (each edge weight 1; link multiplicity is irrelevant to
        shortest-path distance). Uses Wasserman-Faust normalization so nodes
        that can only reach part of a (possibly disconnected) graph are still
        compared fairly:

            C(u) = ( reached / (N-1) ) * ( reached / sum_of_distances )

        where `reached` = number of OTHER nodes reachable from u, and
        sum_of_distances is the total shortest-path distance to them. Nodes
        that reach nobody get closeness 0.

        method:
          "queue"  - classic per-node BFS with a dict of distances (clear,
                     used for small graphs / tests).
          "bitmask"- level-synchronous BFS where each node's neighbor set is a
                     Python big-integer bitmask so frontier expansion is a fast
                     OR of integers. Much faster on the dense 12K graph. Still
                     single-threaded and library-free.
          "auto"   - bitmask when n is large, else queue.

        Returns a list of closeness scores indexed by node.
        """
        n = self.n
        if method not in ("auto", "queue", "bitmask"):
            raise ValueError("method must be auto, queue, or bitmask")
        if method == "auto":
            method = "bitmask" if n > 2000 else "queue"
        if method == "bitmask":
            return self._closeness_bitmask()
        return self._closeness_queue()

    def _closeness_queue(self):
        n = self.n
        adj = [list(set(self.out_links[i])) for i in range(n)]
        closeness = [0.0] * n
        for src in range(n):
            dist = {src: 0}
            q = deque((src,))
            total = 0
            reached = 0
            while q:
                u = q.popleft()
                du = dist[u]
                for v in adj[u]:
                    if v not in dist:
                        dist[v] = du + 1
                        total += du + 1
                        reached += 1
                        q.append(v)
            closeness[src] = 0.0 if total == 0 else \
                (reached / (n - 1)) * (reached / total)
        return closeness

    def _closeness_bitmask(self):
        n = self.n
        # Build one big-integer neighbor bitmask per node (dedup automatically).
        nbr = [0] * n
        for i in range(n):
            m = 0
            for j in set(self.out_links[i]):
                m |= (1 << j)
            nbr[i] = m

        closeness = [0.0] * n
        popcount = int.bit_count if hasattr(int, "bit_count") else \
            (lambda x: bin(x).count("1"))
        for src in range(n):
            visited = 1 << src
            d1 = nbr[src] & ~visited
            if d1 == 0:
                closeness[src] = 0.0
                continue
            visited |= d1
            c = popcount(d1)
            reached = c
            total = c            # depth 1 contributes 1 each
            frontier = d1
            depth = 2
            while frontier:
                nxt = 0
                f = frontier
                while f:
                    low = f & (-f)          # lowest set bit
                    idx = low.bit_length() - 1
                    nxt |= nbr[idx]
                    f ^= low
                nxt &= ~visited
                if nxt == 0:
                    break
                c = popcount(nxt)
                reached += c
                total += depth * c
                visited |= nxt
                frontier = nxt
                depth += 1
            closeness[src] = (reached / (n - 1)) * (reached / total)
        return closeness

    def best_closeness(self, method="auto"):
        """Return (best_node, best_score, all_scores)."""
        c = self.closeness_centrality_all(method=method)
        best = max(range(self.n), key=lambda i: c[i])
        return best, c[best], c


# --------------------------------------------------------------------- helpers
def _describe(values):
    """Compute four summary values and five quintile upper endpoints."""
    vals = list(values)
    vals_sorted = sorted(vals)
    n = len(vals_sorted)
    avg = sum(vals_sorted) / n if n else 0.0
    med = statistics.median(vals_sorted) if n else 0.0
    mx = vals_sorted[-1] if n else 0
    mn = vals_sorted[0] if n else 0
    quintiles = _quintiles(vals_sorted)
    return {
        "average": avg,
        "median": med,
        "max": mx,
        "min": mn,
        "quintiles": quintiles,  # upper endpoints: P20, P40, P60, P80, P100
    }


def _quintiles(sorted_vals):
    """
    Five quintile upper endpoints at the 20/40/60/80/100th percentiles using
    linear interpolation between closest ranks (same method numpy uses by
    default). Implemented by hand to avoid dependencies.
    """
    n = len(sorted_vals)
    out = {}
    if n == 0:
        return {20: 0, 40: 0, 60: 0, 80: 0, 100: 0}
    for p in (20, 40, 60, 80, 100):
        rank = (p / 100.0) * (n - 1)
        lo = int(rank)
        hi = min(lo + 1, n - 1)
        frac = rank - lo
        out[p] = sorted_vals[lo] + frac * (sorted_vals[hi] - sorted_vals[lo])
    return out
