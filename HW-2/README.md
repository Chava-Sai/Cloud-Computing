# CS528 HW2 — Cloud Storage + Hand-Written Graph Analysis (PageRank & Closeness)

This project generates exactly 12,000 linked HTML files, stores them in a **Google
Cloud Storage** bucket in **us-central1**, and runs a **single-threaded**
Python program that reads them back from the bucket and computes link
statistics, PageRank (top 5), and the node with the best closeness centrality.

**No graph libraries are used** (no networkx, igraph, graph-tool, networkit,
etc.). All parsing, the graph representation, PageRank, and closeness
centrality are implemented from scratch in `graphlib_hw.py`. The only
third-party package is `google-cloud-storage`, used solely to read/write bucket
objects.

---

## Repository layout

| File | Purpose |
|------|---------|
| `generate.py` | The provided generator logic (formatting/comments added). Makes `0.html..(n-1).html`. |
| `graphlib_hw.py` | All from-scratch graph code: parsing, graph build, stats, PageRank, closeness. |
| `analyze.py` | Main program. Reads from a GCS bucket (or a local dir), prints all results. |
| `upload_to_gcs.py` | Convenience uploader (or use `gcloud storage cp` / `gsutil cp`). |
| `test_pagerank.py` | Correctness tests for PageRank on small hand-built graphs (graph-independent). |
| `test_closeness.py` | Correctness tests for closeness centrality (graph-independent). |
| `test_regressions.py` | Full unittest suite, exact PageRank values, input checks, and independent closeness oracle. |
| `requirements.txt` | `google-cloud-storage` only. |

---

## Parameters

`generate.py`
- `-n / --num_files` : number of files to generate (use **12000**).
- `-m / --max_refs`  : max references per file (use **325**). Each file gets a
  random number of `<a HREF="X.html">` links, `X` chosen uniformly in
  `[0, num_files)` (self-links and duplicate links are possible; some files may
  have 0 links = *dangling* nodes). The supplied loop emits **0 to 323**
  links when `-m 325` is used; do not change that loop to force 325 links.

`analyze.py`
- `--bucket <name>`   : GCS bucket to read from, e.g. `bu-cs528-you_bu_edu`.
- `--prefix <p>`      : object prefix inside the bucket, e.g. `hw2/`.
- `--local <dir>`     : read from a local directory instead of GCS (for testing).
- `--damping <d>`     : PageRank damping factor (default `0.85`).
- `--threshold <pct>` : convergence threshold in percent (default `0.5`).
- `--skip-closeness`  : skip the (slowest) closeness step.
- `--convergence <sum|l1|both>` : stopping rule; default `both` checks scalar total and rank movement.
- `--authenticated` : use Google credentials instead of the default anonymous public reader.
- `--expected-nodes <n>` : validate dataset size; use `12000` for submitted runs.
- `--verbose-pr`      : print each PageRank iteration.

Exactly one of `--bucket` or `--local` is required.

---

## Quickstart

### 0. Prerequisites
```bash
# Python 3.10–3.14 and the Google Cloud SDK installed & initialized:
gcloud init
gcloud auth login
gcloud auth application-default login      # uploader / --authenticated only
python3 -m pip install -r requirements.txt
```

### 1. Generate the 12K files
```bash
mkdir -p files_12k && cd files_12k
python3 ../generate.py -n 12000 -m 325
cd ..
```
> The generator uses `random.seed(0)`, so the graph — and therefore every
> result below — is **reproducible**.

### 2. Create the bucket (us-central1) and set permissions
See "Bucket setup" below. Then upload:
```bash
# Option A: gcloud
gcloud storage cp files_12k/*.html gs://bu-cs528-you_bu_edu/hw2/

# Option B: gsutil
gsutil -m cp files_12k/*.html gs://bu-cs528-you_bu_edu/hw2/

# Option C: the included uploader
python3 upload_to_gcs.py --bucket bu-cs528-you_bu_edu --local files_12k --prefix hw2/
```

### 3. Run the analysis (reads from the bucket)
```bash
python3 analyze.py --bucket bu-cs528-you_bu_edu --prefix hw2/
```

### 4. Run the tests (independent of the random 12K graph)
```bash
python3 -m unittest discover -v
# The two original suites can also be run individually.
python3 test_pagerank.py
python3 test_closeness.py
```

You can also run the analysis directly against local files without touching the
cloud (useful for a quick check; needs no GCS SDK):
```bash
python3 analyze.py --local files_12k
```

---

## Bucket setup (us-central1, world-readable)

```bash
# 1. Point gcloud at your project
gcloud config set project <YOUR_PROJECT_ID>

# 2. Create a STANDARD bucket in us-central1 with uniform bucket-level access
gcloud storage buckets create gs://bu-cs528-you_bu_edu \
    --location=us-central1 \
    --default-storage-class=STANDARD \
    --uniform-bucket-level-access

# 3. Make the bucket contents world-readable so the TFs can test against it.
#    With uniform bucket-level access, grant the objectViewer role to allUsers:
gcloud storage buckets add-iam-policy-binding gs://bu-cs528-you_bu_edu \
    --member=allUsers --role=roles/storage.objectViewer
```

Equivalent with the classic tools:
```bash
gsutil mb -l us-central1 -c standard gs://bu-cs528-you_bu_edu
gsutil iam ch allUsers:objectViewer gs://bu-cs528-you_bu_edu
```

To verify the objects are publicly readable:
```bash
curl -s https://storage.googleapis.com/bu-cs528-you_bu_edu/hw2/0.html | head
```

Keep public access available through grading. Only after grading, remove it with:
```bash
gcloud storage buckets remove-iam-policy-binding gs://bu-cs528-you_bu_edu \
    --member=allUsers --role=roles/storage.objectViewer
```

---

## Running on a VM (e2-medium)

```bash
# Create the VM in us-central1 (same region as the bucket)
gcloud compute instances create hw2-vm \
    --zone=us-central1-a \
    --machine-type=e2-medium \
    --image-family=debian-12 --image-project=debian-cloud

# SSH in
gcloud compute ssh hw2-vm --zone=us-central1-a

# On the VM: install Python deps and clone the repo
sudo apt-get update && sudo apt-get install -y python3-pip python3-venv git
git clone <YOUR_GITHUB_URL> && cd <repo>
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt

# Run anonymously against the public bucket
python3 analyze.py --bucket bu-cs528-you_bu_edu --prefix hw2/
```

**Delete the VM when finished** (otherwise it keeps consuming budget):
```bash
gcloud compute instances delete hw2-vm --zone=us-central1-a
```

---

## What the program computes (implementation notes)

**Graph model.** Each `i.html` is a node. Every `<a HREF="j.html">` is a
directed edge `i -> j`. The generator can emit the same target multiple times
in a file and can emit self-links; we preserve this as a directed
**multigraph**. `C(i)` (out-degree used by PageRank) is the number of link
*slots* in file `i` (duplicates counted).

**Link statistics.** Nine values for incoming counts and nine for outgoing
counts: average, median, max, min, and five quintile upper endpoints
(P20/P40/P60/P80/P100, linearly interpolated). P100 repeats the maximum.
This explicitly defines our interpretation of the professor's five quintile
values; the four interior cut points alone would provide only eight numbers.

**PageRank.** The assignment's link contribution formula, iterated:
```
PR(A) = (1 - d)/n + d * ( PR(T1)/C(T1) + ... + PR(Tn)/C(Tn) ),  d = 0.85
```
Dangling nodes (`C = 0`) have their mass redistributed uniformly each iteration.
This is an explicit extension for zero-outdegree nodes; the assignment's
printed formula does not specify dangling-node handling.

**Stopping rule.** `--convergence sum` follows the literal prompt:
`100 * abs(sum(new) - sum(old)) / sum(old) <= 0.5`.
Since dangling redistribution preserves a total of 1, this normally stops after
one iteration, before the individual scores stabilize. `--convergence l1`
checks `100 * sum(abs(new[i]-old[i])) / sum(new) <= 0.5` instead.
The default `--convergence both` requires both criteria. This is a documented
additional safeguard, not an instructor-confirmed interpretation. Report the
mode you run; ask the instructor if they require stopping at the first scalar
sum match. `--verbose-pr` prints both measurements. Hitting the iteration limit
raises an error instead of incorrectly reporting convergence.

**Closeness centrality.** Directed outward closeness: shortest paths from a
page to other pages, using hand-written BFS. On the dense 12K graph almost every
node reaches every other node at distance ≈ 2, so we use a level-synchronous
BFS in which each node's neighbor set is a Python big-integer **bitmask**;
frontier expansion becomes a fast integer OR. This is a single-threaded,
library-free optimization. Both BFS implementations are checked against an
independent hand-written Floyd-Warshall oracle on all 512 three-node directed
graphs. Performance must be measured on each required environment. We use Wasserman–Faust normalization so nodes are compared fairly:
```
C(u) = ( reached / (N-1) ) * ( reached / sum_of_distances )
```

**Single-threaded.** No threads, processes, or async. The code is deliberately
sequential per the assignment.


## Evidence still needed before submission

The existing `HW2_Report.pdf` is an unfinished draft with stale implementation
notes and sample timings. Do not submit it unchanged. Use one repository for
all homework, with this code in an `HW-2/` subdirectory, as the professor stated.
This workspace is not yet connected to a Git repository.

For each environment, run the **same code, same bucket and same prefix**, with
closeness enabled. A `--local` run does not satisfy the laptop bucket timing.
After cloning your existing homework repository and entering its HW-2 folder:

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
mkdir -p results
python3 -m unittest discover -v > results/tests.txt 2>&1
python3 --version > results/environment.txt
uname -a >> results/environment.txt
set -o pipefail
python3 -u analyze.py --bucket YOUR_BUCKET --prefix hw2/ --expected-nodes 12000 --verbose-pr --convergence both | tee results/laptop.txt
# Repeat in Cloud Shell with results/cloudshell.txt and on the e2-medium VM
# with results/vm.txt. Record CPU details, Python/dependency versions and region.
```

Cloud Shell: activate the terminal in Google Cloud Console, clone the existing
homework repository, enter HW-2, then run the same environment setup and command
above. Do not assume its region or CPU performance; record what you observe.

Verify public **listing and reading**, not just a single object. The default
anonymous analysis run checks both without requiring the graders' credentials.
`allUsers` + `roles/storage.objectViewer` grants object listing and reading:
https://docs.cloud.google.com/storage/docs/access-control/making-data-public
Uniform bucket-level access uses IAM instead of per-object ACLs; document this.
Public access prevention must not block the intended public homework bucket.

Record actual elapsed times for loading/building, statistics, PageRank,
closeness and total. Explain the observed differences using network round-trip
latency, bucket proximity, single-core CPU performance and machine load; do not
claim Cloud Shell is necessarily in us-central1 or always slower than a laptop.

Save the actual Billing console screenshot with the homework project and date
range selected, report the displayed cost and credit treatment, and note the
capture time (billing can arrive later). Do not estimate a total and label it
as measured spend. Save VM details and execution logs before deleting the VM;
record the deletion and verify it no longer exists. Leave the bucket available
for grading. Finally, verify the submitted repository URL with `git clone` from
an account that has the same access as the graders.
