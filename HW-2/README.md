# Homework 2: Cloud Storage and Graph Analysis

Chava-Sai | CS528 Cloud Computing

This program reads 12,000 linked HTML pages from Google Cloud Storage and
computes incoming and outgoing link statistics, PageRank, and directed
closeness centrality. Parsing and graph algorithms use Python's standard
library. Graph processing runs on one thread and does not use graph libraries.
Optional parallel downloads use Google Storage's built-in transfer manager,
as permitted by the instructor's Piazza clarification.

## Project details

| Setting | Value |
| --- | --- |
| Google Cloud project ID | `thermal-circle-508221-m7` |
| Bucket | `thermal-circle-508221-m7-hw2` |
| Region | `us-central1` |
| Object directories | `hw2/` (uncompressed), `hw2-gzip/` (gzip content encoding) |
| Pages | `0.html` through `11999.html` |
| Generator arguments | `-n 12000 -m 325` |
| Repository | https://github.com/Chava-Sai/Cloud-Computing.git |

The bucket allows anonymous listing and reading through the `allUsers`
principal with `roles/storage.objectViewer`. Uniform bucket-level access is
enabled, so permissions are managed through IAM rather than individual object
ACLs. The analysis uses an anonymous client by default.

## Install and run

```bash
git clone https://github.com/Chava-Sai/Cloud-Computing.git
cd Cloud-Computing/HW-2
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
python3 -m unittest discover -v
python3 -u analyze.py \
  --bucket thermal-circle-508221-m7-hw2 \
  --prefix hw2/ \
  --expected-nodes 12000 \
  --download-workers 32 \
  --convergence both \
  --verbose-pr
```

These commands work on the laptop, Cloud Shell, and a Linux VM with Python,
venv, pip, and Git installed. For the package versions used in the laptop run,
install `results/laptop-packages.txt` instead of `requirements.txt`.
Google Cloud credentials are not required to analyze the public bucket.

Object listing uses responses of at most 100 entries containing only names,
generations, and the next-page token. Keeping that token allows the client to
retrieve the entire directory. Network requests
use a 10-second connection timeout and a 60-second read-inactivity timeout,
with a 300-second retry budget for transient failures. An attempt already in
progress may finish after the retry budget. Progress is printed during listing
and after every 100 downloads; a failed download identifies its object name.

`--download-workers 1` (the default) downloads and parses one file at a time.
`--download-workers 32` uses 32 workers managed by
`google.cloud.storage.transfer_manager.download_many`. Downloads are submitted
in batches of 100 to provide progress updates. All files are downloaded into a
fresh temporary directory before any parsing begins. After the final batch
completes successfully, parsing, graph construction, statistics, PageRank, and
closeness run sequentially on the main thread. Temporary files are removed on
completion or failure; runs do not reuse cached downloads. Allow approximately
1 GB of temporary disk space. Listing, downloading, and parsing timings are
printed separately in transfer-manager mode, as well as the combined loading
time. Use the same worker count for all three environment benchmarks.

## Files

| File | Purpose |
| --- | --- |
| `generate.py` | Supplied generator logic, with added comments and formatting. |
| `analyze.py` | Load pages, validate the dataset, run the analysis, and print timings. |
| `graphlib_hw.py` | Graph representation, parsing, statistics, PageRank, and closeness. |
| `upload_to_gcs.py` | Sequential uploader using the Google Cloud Storage client. |
| `test_pagerank.py` | PageRank tests on small graphs with known properties. |
| `test_closeness.py` | Closeness tests with manually calculated distances. |
| `test_regressions.py` | Unified test discovery and additional correctness checks. |
| `test_gcs_io.py` | SDK pagination, download failures, and processing order tests, with no network requests. |
| `requirements.txt` | Direct dependency: `google-cloud-storage`. |
| `results/` | Saved run output, test output, and environment details. |

## Report

The Overleaf source is [report/HW2_Report.tex](report/HW2_Report.tex).
Upload it with [report/billing.png](report/billing.png), select pdfLaTeX,
and compile the report. It includes the measured outputs, algorithm and test
explanations, setup and cleanup instructions, billing evidence and limitations,
and the required disclosure of AI assistance.

The billing screenshot shows current-month project totals of $0.01 usage cost,
-$0.01 savings, and $0.00 net for September 1-25, 2026. This is not an isolated
final HW2 cost: the same project was used for HW1, and recent billing data had
not fully updated. The report explains how to retrieve assignment-period costs
and records the instructor's clarification concerning delayed billing.

## Dataset and bucket setup

The following commands generate the dataset and reproduce the bucket setup.
Bucket creation and upload require an authenticated Google Cloud account with
the appropriate project permissions. The existing bucket already contains the
data and can be used directly with the analysis command above.

```bash
mkdir -p files_12k
cd files_12k
python3 ../generate.py -n 12000 -m 325
cd ..

gcloud config set project thermal-circle-508221-m7

gcloud storage buckets create gs://thermal-circle-508221-m7-hw2 \
  --project=thermal-circle-508221-m7 \
  --location=us-central1 \
  --default-storage-class=STANDARD \
  --uniform-bucket-level-access

gcloud storage buckets add-iam-policy-binding gs://thermal-circle-508221-m7-hw2 \
  --member=allUsers \
  --role=roles/storage.objectViewer

gcloud storage rsync files_12k gs://thermal-circle-508221-m7-hw2/hw2/ \
  --recursive --project=thermal-circle-508221-m7
```

The generator uses `random.seed(0)`. With `-m 325`, its original loops produce
between 0 and 323 outgoing link occurrences per page. Duplicate targets and
self-links are retained. The dataset has 1,946,934 link occurrences.

Anonymous listing and reading can be checked with:

```bash
curl --fail --silent --show-error \
  'https://storage.googleapis.com/storage/v1/b/thermal-circle-508221-m7-hw2/o?prefix=hw2%2F&maxResults=1'

curl --fail --silent --show-error \
  --output /tmp/hw2-public-0.html \
  --write-out 'HTTP status: %{http_code}\n' \
  'https://storage.googleapis.com/thermal-circle-508221-m7-hw2/hw2/0.html'
```

Both checks succeeded; the file request returned HTTP 200.

## Program parameters

| Parameter | Meaning |
| --- | --- |
| `--bucket NAME` | Read pages from the specified bucket. |
| `--prefix PATH` | Directory prefix inside the bucket; use `hw2/` or `hw2-gzip/`. |
| `--local DIRECTORY` | Read local pages instead of the bucket. |
| `--expected-nodes N` | Reject a dataset with a different number of pages; use `12000`. |
| `--damping D` | PageRank damping factor; default `0.85`. |
| `--threshold PCT` | PageRank stopping threshold in percent; default `0.5`. |
| `--convergence sum` | Check the percentage change in the total PageRank. |
| `--convergence l1` | Check the total absolute movement of individual ranks. |
| `--convergence both` | Require both stopping checks; the default and the recorded run's mode. |
| `--verbose-pr` | Print total rank and both change measurements each iteration. |
| `--download-workers N` | Download worker count; default `1`, use `32` for library-managed parallel downloads only. |
| `--authenticated` | Use Google application default credentials instead of anonymous access. |
| `--skip-closeness` | Omit closeness for troubleshooting; not used in the complete run. |

Exactly one of `--bucket` and `--local` is required. The loader checks for
contiguous page IDs and rejects links to pages outside the dataset.

## Algorithms

### Graph and link statistics

Each page is a node, and each HTML link is a directed edge. Repeated links
count separately for incoming degree, outgoing degree, and PageRank.
The graph stores outgoing targets and reverse edges with multiplicities.

Incoming and outgoing degrees are summarized separately. Each summary has
nine values: average, median, maximum, minimum, and the five quintile upper
endpoints P20, P40, P60, P80, and P100. Percentiles use linear interpolation;
P100 is the maximum.

### PageRank

Ranks start at `1/n`. Each iteration applies the link contribution formula:

```text
PR_new(A) = 0.15/n + 0.85 * sum(PR_old(T) / C(T))
```

The sum includes each link occurrence from an incoming page T, and C(T) counts
all outgoing link occurrences. Pages with no outgoing links redistribute their
rank uniformly across all pages. This adds dangling-node handling to the
printed link contribution formula and preserves total rank at approximately 1.

The two stopping measurements are:

```text
sum-change (%) = 100 * abs(sum(new) - sum(old)) / sum(old)
L1-change (%)  = 100 * sum(abs(new[i] - old[i])) / sum(new)
```

The `sum` option implements the assignment's literal total-rank stopping rule.
Because total rank is conserved, it normally stops after one iteration even
when individual scores are still changing. The default `both` option adds the
requirement that L1 movement is also at most 0.5%. The recorded run uses `both`
and takes three iterations. Reaching the iteration limit without satisfying
the selected criterion raises an error.

### Closeness centrality

Closeness uses shortest directed paths from a page to the pages it can reach.
Breadth-first search computes the distances. Duplicate links do not change
shortest paths. For R reachable pages other than the source, N total pages,
and distance sum S, the Wasserman-Faust normalized score is:

```text
closeness = (R / (N - 1)) * (R / S)
```

A page that reaches no other pages has score zero. Small graphs use a queue
implementation. Graphs with more than 2,000 nodes use integer bitmasks to
represent neighbor sets and expand BFS levels. Both implementations are
single-threaded.

## Correctness tests

Run all tests with `python3 -m unittest discover -v`. The suite contains 27
tests, all of which passed on the laptop, Cloud Shell, and VM. Tests are
independent of the generated 12,000-page graph.

PageRank checks include symmetric graphs, exact nonuniform scores from solved
equations, dangling nodes, duplicate links, and the difference between the two
stopping criteria. Closeness checks include paths, stars, isolated nodes, and
both BFS implementations compared with an independently implemented
Floyd-Warshall distance calculation on all 512 directed three-node graphs.
Additional tests check parsing, statistics, dataset validation, anonymous
bucket loading, and pagination. Transfer tests verify that all downloads finish
before parsing starts and that failed transfers remove temporary files without
returning a partial graph.

## Recorded results across three environments

All three completed runs used source commit `2dd9507`, 32 Google transfer-manager
download workers, `--expected-nodes 12000`, `--convergence both`, and
`--verbose-pr`. Each run listed and read all 12,000 objects from the public
bucket and returned exit code 0. Graph processing remained single-threaded.

| Setting | Laptop | Cloud Shell | VM |
| --- | --- | --- | --- |
| Python | 3.13.7 | 3.12.3 | 3.11.2 |
| Platform | Apple M4 Pro, macOS 27.0, 24 GiB RAM | Linux, Intel Xeon at 2.20 GHz | Debian 12, e2-medium, AMD EPYC 7B12 |
| Prefix | `hw2/` | `hw2-gzip/` | `hw2/` |
| Object encoding | Uncompressed | gzip | Uncompressed |

| Stage (seconds) | Laptop | Cloud Shell | VM |
| --- | ---: | ---: | ---: |
| Object listing | 10.92 | 28.59 | 4.69 |
| Download | 111.23 | 136.99 | 112.08 |
| Parse and graph construction | 1.23 | 4.02 | 3.50 |
| Combined loading stage | 123.99 | 170.32 | 120.99 |
| Link statistics | 0.001 | 0.005 | 0.004 |
| PageRank | 0.29 | 0.90 | 0.63 |
| Closeness | 102.67 | 255.93 | 339.36 |
| Total wall time | 226.96 | 427.16 | 460.99 |

Combined loading includes listing, downloading, parsing, and other loader
overhead; it is not an additional stage to add to those component timings.
These are individual measurements, not averages of repeated trials.

All runs produced 1,946,934 link occurrences, the same incoming and outgoing
statistics, the same top five PageRank pages shown below, and the same best
closeness page, `10376.html`, with score `0.50464735`.

### Cloud Shell downloads and gzip

Uncompressed Cloud Shell downloads were slow and repeatedly timed out. In the
32-worker attempt, a read timeout exhausted the 300-second retry budget for
`hw2/2701.html`; the program correctly rejected the incomplete run. This
failed attempt is retained separately from the completed measurements.

The same generated HTML files were uploaded to `hw2-gzip/` with gzip content
encoding. From the directory containing `files_12k`, the upload command was:

```bash
gcloud storage cp 'files_12k/*.html' \
  gs://thermal-circle-508221-m7-hw2/hw2-gzip/ \
  --gzip-local=html \
  --project=thermal-circle-508221-m7
```

The object names remain `0.html` through `11999.html`; decompression preserves
the original HTML. A Cloud Shell check downloaded `0.html` as 1,576 compressed
bytes and confirmed that the normal Python client download returned the same
97,586-byte HTML as explicit gzip decompression. The raw compressed request
took 0.19 seconds and the normal decoded request took 0.11 seconds.

The completed Cloud Shell command was:

```bash
python3 -u analyze.py \
  --bucket thermal-circle-508221-m7-hw2 \
  --prefix hw2-gzip/ \
  --expected-nodes 12000 \
  --download-workers 32 \
  --convergence both \
  --verbose-pr
```

Low CPU usage during the earlier download phase, network read timeouts, and
successful downloads after reducing transferred bytes are consistent with a
network bottleneck in that Cloud Shell session. These observations do not
establish a particular bandwidth quota or prove provider throttling. Increasing
parallelism alone did not solve the problem. Compression greatly reduces the
repeated filler text in the generated files.

Cloud Shell used different object encoding from the laptop and VM, so these
end-to-end times are not a controlled comparison of network performance.
The graph algorithms and logical dataset were the same. Closeness took the
most computation time; differences in processor performance, available CPU
resources, and Python versions can affect it. The laptop was fastest for this
stage. Downloads on the laptop and the VM took nearly the same time.

### Saved evidence and VM cleanup

- [Laptop completed output](results/laptop-parallel-bucket-run.txt), [environment](results/laptop-parallel-environment.txt), [packages](results/laptop-parallel-packages.txt), and [tests](results/laptop-parallel-tests.txt).
- [Cloud Shell completed output](results/cloudshell-gzip-bucket-run.txt), [environment](results/cloudshell-gzip-environment.txt), [packages](results/cloudshell-packages.txt), and [tests](results/cloudshell-tests.txt).
- [Cloud Shell gzip check](results/cloudshell-gzip-check.txt) and [failed uncompressed attempt](results/cloudshell-32-failed-01.txt).
- [VM completed output](results/vm-parallel-bucket-run.txt), [environment](results/vm-environment.txt), [packages](results/vm-packages.txt), and [tests](results/vm-tests.txt).
- [Bucket configuration](results/bucket-configuration.json) and [public-read IAM policy](results/bucket-iam-policy.json).

The VM was `hw2-vm`, an `e2-medium` in `us-central1-a`, with Debian 12 and a
10 GB standard persistent boot disk. After the results were copied to the
laptop, it was deleted with:

```bash
gcloud compute instances delete hw2-vm \
  --project=thermal-circle-508221-m7 \
  --zone=us-central1-a \
  --delete-disks=boot \
  --quiet
```

The [saved VM configuration](results/vm-configuration.yaml) records the machine
before deletion. The [deletion output](results/vm-deletion.txt) confirms deletion;
subsequent [instance](results/vm-after-deletion.json) and
[disk](results/vm-disks-after-deletion.json) queries both returned empty lists.
The public bucket remains available for grading.

## Earlier sequential laptop baseline

This recorded run used sequential downloads, default listing responses, and
default network retries. It is a sequential baseline, not a measurement of the
optional parallel downloader. The graph algorithms are unchanged.

The complete bucket run used Python 3.13.7 on an Apple M4 Pro Mac with 24 GiB
of memory. It loaded all 12,000 pages from the public bucket.

| Stage | Time (seconds) |
| --- | ---: |
| Read bucket files and construct graph | 1943.12 |
| Link statistics | 0.001 |
| PageRank | 0.32 |
| Closeness | 126.10 |
| Total | 2069.55 |

| Rank | Page | PageRank |
| --- | --- | ---: |
| 1 | `5207.html` | 0.00019553 |
| 2 | `7443.html` | 0.00018286 |
| 3 | `7400.html` | 0.00017964 |
| 4 | `950.html` | 0.00017441 |
| 5 | `369.html` | 0.00017332 |

The highest outward closeness score is **0.50464735**, for **10376.html**.

Saved measurements:

- [Complete laptop bucket output](results/laptop-bucket-run.txt)
- [Laptop test output](results/laptop-tests.txt)
- [Laptop environment](results/laptop-environment.txt)
- [Installed package versions](results/laptop-packages.txt)
