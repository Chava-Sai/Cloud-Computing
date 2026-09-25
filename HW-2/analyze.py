#!/usr/bin/env python3
"""
analyze.py -- CS528 HW2 analysis (single-threaded graph algorithms).

Opens a Google Cloud Storage bucket, lists the HTML files under a prefix,
reads each one, builds an in-memory directed multigraph, and computes:

  * average / median / max / min / quintiles of incoming and outgoing links
  * PageRank (hand-coded iterative algorithm) and the top-5 pages
  * the node with the best closeness centrality (hand-coded BFS)

All graph logic lives in graphlib_hw.py and uses only the standard library.
The ONLY third-party dependency is google-cloud-storage, used purely to read
objects from the bucket (not for any graph computation).

Examples
--------
Read directly from the bucket (laptop / Cloud Shell / VM):
    python3 analyze.py --bucket thermal-circle-508221-m7-hw2 --prefix hw2/

Read from a local directory instead of GCS (handy for testing):
    python3 analyze.py --local files_small

Typical bucket layout expected:
    gs://thermal-circle-508221-m7-hw2/hw2/0.html
    gs://thermal-circle-508221-m7-hw2/hw2/1.html
    ...
"""
import argparse
import os
import re
import tempfile
import time

from graphlib_hw import WebGraph, parse_links


def log(msg):
    print(msg, flush=True)


# --------------------------------------------------------------------- loaders
def validate_ids(ids):
    """The supplied generator creates exactly the ids 0 through n-1."""
    if not ids:
        raise ValueError("No numbered HTML pages found")
    if ids != list(range(len(ids))):
        raise ValueError("Expected every page from 0.html through (n-1).html; dataset has missing ids")


def load_from_local(directory):
    """Read all N.html files from a local directory. Returns (graph, n)."""
    names = [f for f in os.listdir(directory) if re.fullmatch(r"(0|[1-9][0-9]*)\.html", f)]
    ids = sorted(int(f[:-5]) for f in names)
    validate_ids(ids)
    n = len(ids)
    g = WebGraph(n)
    for i in ids:
        with open(os.path.join(directory, f"{i}.html"), "r",
                  encoding="utf-8") as fh:
            g.set_out_links(i, parse_links(fh.read()))
    g.finalize()
    return g, n


def load_from_gcs(bucket_name, prefix, authenticated=False, download_workers=1):
    """Read all N.html blobs under prefix from a GCS bucket. Returns (graph,n)."""
    if download_workers < 1:
        raise ValueError("download_workers must be at least 1")
    from google.cloud import storage  # imported lazily so --local needs no SDK
    from google.cloud.storage.retry import DEFAULT_RETRY
    client = storage.Client() if authenticated else storage.Client.create_anonymous_client()
    prefix = prefix.rstrip("/") + "/" if prefix else ""
    request_timeout = (10, 60)  # connect timeout, then read-inactivity timeout
    retry = DEFAULT_RETRY.with_timeout(300)

    # Small partial responses avoid downloading unnecessary object metadata.
    # Keep nextPageToken so the SDK visits EVERY page, not just the first 100.
    t_list = time.perf_counter()
    log("Listing objects (up to 100 per response)...")
    blobs = client.list_blobs(
        bucket_name, prefix=prefix, page_size=100,
        fields="nextPageToken,items(name,generation)",
        timeout=request_timeout, retry=retry,
    )
    id_to_blob = {}
    for listed, b in enumerate(blobs, 1):
        base = b.name[len(prefix):]
        if re.fullmatch(r"(0|[1-9][0-9]*)\.html", base):
            id_to_blob[int(base[:-5])] = b
        if listed % 100 == 0:
            log(f"  ...listed {listed} objects")

    ids = sorted(id_to_blob)
    validate_ids(ids)
    n = len(ids)
    log(f"Object listing time: {time.perf_counter() - t_list:.2f}s")
    if download_workers > 1:
        return load_with_transfer_manager(id_to_blob, ids, download_workers,
                                          request_timeout, retry), n
    log(f"Found {n} numbered pages. Downloading sequentially...")

    g = WebGraph(n)
    # Second pass: download each object and parse its links (single-threaded).
    for k, i in enumerate(ids):
        if k % 100 == 0:
            log(f"  downloading {id_to_blob[i].name} ({k + 1}/{n})")
        try:
            text = id_to_blob[i].download_as_text(timeout=request_timeout, retry=retry)
        except Exception as exc:
            raise RuntimeError(
                f"Download failed for {id_to_blob[i].name}; {k}/{n} pages read. "
                "This run is incomplete."
            ) from exc
        g.set_out_links(i, parse_links(text))
        if (k + 1) % 100 == 0 or k + 1 == n:
            log(f"  ...read {k + 1}/{n} files")
    g.finalize()
    return g, n


def load_with_transfer_manager(id_to_blob, ids, workers, request_timeout, retry):
    """Library-managed downloads first; parse and construct the graph afterwards."""
    from google.cloud.storage import transfer_manager

    n = len(ids)
    log(f"Found {n} numbered pages. Downloading with {workers} Google transfer-manager workers...")
    # A fresh directory means every run reads all objects from the bucket.
    # It is removed automatically after parsing, including if a download fails.
    with tempfile.TemporaryDirectory(prefix="hw2-downloads-") as directory:
        t_download = time.perf_counter()
        for start in range(0, n, 100):
            batch = ids[start:start + 100]
            pairs = [(id_to_blob[i], os.path.join(directory, f"{i}.html")) for i in batch]
            log(f"  downloading files {start + 1}-{start + len(batch)}/{n}")
            results = transfer_manager.download_many(
                pairs, worker_type=transfer_manager.THREAD, max_workers=workers,
                download_kwargs={"timeout": request_timeout, "retry": retry},
                raise_exception=False,
            )
            for (blob, _), result in zip(pairs, results):
                if result is not None:
                    raise RuntimeError(f"Download failed for {blob.name}; this run is incomplete.") from result
            log(f"  ...downloaded {start + len(batch)}/{n} files")
        log(f"Download time: {time.perf_counter() - t_download:.2f}s")
        log("All downloads finished. Parsing and constructing the graph on one thread...")
        t_parse = time.perf_counter()
        graph, _ = load_from_local(directory)
        log(f"Parse + graph construction time: {time.perf_counter() - t_parse:.2f}s")
    return graph


# ------------------------------------------------------------------- reporting
def print_link_stats(stats):
    for direction in ("incoming", "outgoing"):
        s = stats[direction]
        q = s["quintiles"]
        log(f"\n{direction.capitalize()} links across all pages:")
        log(f"  average : {s['average']:.4f}")
        log(f"  median  : {s['median']:.4f}")
        log(f"  max     : {s['max']}")
        log(f"  min     : {s['min']}")
        log("  five quintile upper endpoints (linear-interpolated percentiles):")
        log(f"    20th : {q[20]:.4f}")
        log(f"    40th : {q[40]:.4f}")
        log(f"    60th : {q[60]:.4f}")
        log(f"    80th : {q[80]:.4f}")
        log(f"   100th : {q[100]:.4f}")


def main():
    ap = argparse.ArgumentParser(description="CS528 HW2 graph analysis")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--bucket", help="GCS bucket name (e.g. thermal-circle-508221-m7-hw2)")
    src.add_argument("--local", help="Local directory of N.html files (testing)")
    ap.add_argument("--prefix", default="", help="Object prefix inside the bucket, e.g. hw2/")
    ap.add_argument("--damping", type=float, default=0.85, help="PageRank damping d (default 0.85)")
    ap.add_argument("--threshold", type=float, default=0.5,
                    help="Convergence threshold in %% of total PR (default 0.5)")
    ap.add_argument("--convergence", choices=("sum", "l1", "both"), default="both",
                    help="PageRank stopping rule: literal sum, L1 movement, or both (default)")
    ap.add_argument("--authenticated", action="store_true",
                    help="Use Google credentials; default reads the public bucket anonymously")
    ap.add_argument("--download-workers", type=int, default=1,
                    help="Google transfer-manager download workers (default 1; use 8 for parallel I/O only)")
    ap.add_argument("--expected-nodes", type=int,
                    help="Fail if the dataset size differs (use 12000 for HW2)")
    ap.add_argument("--skip-closeness", action="store_true",
                    help="Skip the (slow) closeness centrality computation")
    ap.add_argument("--verbose-pr", action="store_true", help="Print PageRank iterations")
    args = ap.parse_args()
    if args.download_workers < 1:
        ap.error("--download-workers must be at least 1")
    if args.local and args.download_workers != 1:
        ap.error("--download-workers applies only to --bucket")

    t_all = time.perf_counter()

    # ---- load
    log("=" * 60)
    log("Loading files and building the graph...")
    t0 = time.perf_counter()
    if args.local:
        g, n = load_from_local(args.local)
        source = f"local dir '{args.local}'"
    else:
        g, n = load_from_gcs(args.bucket, args.prefix, args.authenticated, args.download_workers)
        source = f"gs://{args.bucket}/{args.prefix}"
    if args.expected_nodes is not None and n != args.expected_nodes:
        ap.error(f"Expected {args.expected_nodes} pages but loaded {n}")
    t_load = time.perf_counter() - t0
    total_edges = sum(g.out_counts)
    log(f"Loaded {n} nodes, {total_edges} link-slots (edges w/ dups) "
        f"from {source}")
    log(f"Graph build + read time: {t_load:.2f}s")

    # ---- link statistics
    log("\n" + "=" * 60)
    log("LINK STATISTICS")
    t0 = time.perf_counter()
    stats = g.link_statistics()
    print_link_stats(stats)
    log(f"\n(stats time: {time.perf_counter() - t0:.3f}s)")

    # ---- pagerank
    log("\n" + "=" * 60)
    log("PAGERANK (hand-coded iterative algorithm)")
    t0 = time.perf_counter()
    pr, iters = g.pagerank(damping=args.damping,
                           threshold_pct=args.threshold,
                           verbose=args.verbose_pr, convergence=args.convergence)
    t_pr = time.perf_counter() - t0
    log(f"Stopping rule '{args.convergence}' met after {iters} iterations "
        f"(threshold {args.threshold}%). Time: {t_pr:.2f}s")
    if args.convergence == "sum":
        log("Scalar-sum stability does not imply individual PageRank scores have converged.")
    log("Top 5 pages by PageRank:")
    for rank, (node, score) in enumerate(g.top_k_pagerank(pr, 5), 1):
        log(f"  {rank}. page {node}.html   PR = {score:.8f}   "
            f"(in={g.in_counts[node]}, out={g.out_counts[node]})")

    # ---- closeness centrality
    if not args.skip_closeness:
        log("\n" + "=" * 60)
        log("CLOSENESS CENTRALITY (hand-coded BFS from every node)")
        log("Single-threaded BFS over all nodes.")
        t0 = time.perf_counter()
        best, score, _ = g.best_closeness()
        t_cc = time.perf_counter() - t0
        log(f"Best closeness centrality: page {best}.html  score = {score:.8f}")
        log(f"Closeness time: {t_cc:.2f}s")
    else:
        log("\n(closeness centrality skipped by --skip-closeness)")

    log("\n" + "=" * 60)
    log(f"TOTAL wall time: {time.perf_counter() - t_all:.2f}s")


if __name__ == "__main__":
    main()
