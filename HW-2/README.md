# Homework 2: Cloud Storage and Graph Analysis

Chava-Sai | CS528 Cloud Computing

This program reads 12,000 linked HTML pages from Google Cloud Storage and
computes incoming and outgoing link statistics, PageRank, and directed
closeness centrality. Parsing and graph algorithms use Python's standard
library. The analysis runs sequentially and does not use graph libraries.

## Project details

| Setting | Value |
| --- | --- |
| Google Cloud project ID | `thermal-circle-508221-m7` |
| Bucket | `thermal-circle-508221-m7-hw2` |
| Region | `us-central1` |
| Object directory | `hw2/` |
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
  --convergence both \
  --verbose-pr
```

These commands work on the laptop, Cloud Shell, and a Linux VM with Python,
venv, pip, and Git installed. For the package versions used in the laptop run,
install `results/laptop-packages.txt` instead of `requirements.txt`.
Google Cloud credentials are not required to analyze the public bucket.

Object listing uses responses of at most 100 entries containing only names,
generations, and the next-page token. Keeping that token allows the client to
retrieve the entire directory. Downloads remain sequential. Network requests
use a 10-second connection timeout and a 60-second read-inactivity timeout,
with a 300-second retry budget for transient failures. An attempt already in
progress may finish after the retry budget. Progress is printed during listing
and after every 100 downloads; a failed download identifies its object name.

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
| `test_gcs_io.py` | SDK pagination and failed-download tests, with no network requests. |
| `requirements.txt` | Direct dependency: `google-cloud-storage`. |
| `results/` | Saved run output, test output, and environment details. |

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
| `--prefix PATH` | Directory prefix inside the bucket; this dataset uses `hw2/`. |
| `--local DIRECTORY` | Read local pages instead of the bucket. |
| `--expected-nodes N` | Reject a dataset with a different number of pages; use `12000`. |
| `--damping D` | PageRank damping factor; default `0.85`. |
| `--threshold PCT` | PageRank stopping threshold in percent; default `0.5`. |
| `--convergence sum` | Check the percentage change in the total PageRank. |
| `--convergence l1` | Check the total absolute movement of individual ranks. |
| `--convergence both` | Require both stopping checks; the default and the recorded run's mode. |
| `--verbose-pr` | Print total rank and both change measurements each iteration. |
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

Run all tests with `python3 -m unittest discover -v`. The suite contains 25
tests. The original 23 tests passed on both the laptop and Cloud Shell; the
expanded 25-test suite passed locally after the listing change. Tests are independent
of the generated 12,000-page graph.

PageRank checks include symmetric graphs, exact nonuniform scores from solved
equations, dangling nodes, duplicate links, and the difference between the two
stopping criteria. Closeness checks include paths, stars, isolated nodes, and
both BFS implementations compared with an independently implemented
Floyd-Warshall distance calculation on all 512 directed three-node graphs.
Additional tests check parsing, statistics, dataset validation, and anonymous
bucket loading.

## Recorded laptop results

This recorded run used the previous loading settings: default listing responses
and default network retries. The graph algorithms are unchanged.

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
