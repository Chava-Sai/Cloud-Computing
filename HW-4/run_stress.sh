#!/usr/bin/env bash
# From Cloud Shell: PROJECT_ID=your-project bash run_stress.sh 1 (then 2, 3, 4).
set -euo pipefail

: "${PROJECT_ID:?Set PROJECT_ID}"
clients="${1:?Provide one client count, 1 through 4}"
if [[ ! "$clients" =~ ^[1-4]$ ]]; then
  echo "Client count must be 1, 2, 3, or 4" >&2
  exit 2
fi

zone="${ZONE:-us-central1-a}"
region="${REGION:-us-central1}"
duration=180
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
run_id="$(date -u +%Y%m%dT%H%M%SZ)-c$clients"
result_dir="$script_dir/stress-results/$run_id"
remote_csv="/tmp/hw4-$run_id.csv"
mkdir -p "$result_dir"

gc() { gcloud --project="$PROJECT_ID" "$@"; }
web_ip="$(gc compute addresses describe hw4-web-ip --region="$region" --format='value(address)')"
echo "Trial $run_id; web IP $web_ip; start $(date -u +%FT%TZ)"

# Stage the client script before starting the 3-minute measurement.
gc compute scp "$script_dir/stress_client.sh" hw4-client:~/hw4_stress_client.sh --zone="$zone"
gc compute ssh hw4-client --zone="$zone" --command='chmod +x ~/hw4_stress_client.sh'

# Detach the lightweight /proc sampler on the web VM.
gc compute ssh hw4-web --zone="$zone" --command="nohup python3 /opt/hw4/first_service/metrics.py --seconds=$duration --interval=1 --output=$remote_csv >/tmp/hw4-$run_id.log 2>&1 </dev/null &"
sleep 2
gc compute ssh hw4-web --zone="$zone" --command="test -s $remote_csv"

# This script enforces the four-client ceiling and omits -v during load.
gc compute ssh hw4-client --zone="$zone" \
  --command="bash ~/hw4_stress_client.sh $clients $duration $web_ip $run_id" \
  | tee "$result_dir/client-summary.txt"

gc compute scp "hw4-web:$remote_csv" "$result_dir/metrics.csv" --zone="$zone"
python3 - "$result_dir/metrics.csv" <<'PY' | tee "$result_dir/metrics-summary.txt"
import csv
import statistics
import sys

with open(sys.argv[1], encoding="utf-8", newline="") as handle:
    rows = list(csv.DictReader(handle))
if len(rows) < 150:
    raise SystemExit(f"Only {len(rows)} metric samples; expected about 180")
print(f"Metric samples: {len(rows)}")
for key, label, unit in (
    ("cpu_percent", "CPU", "%"),
    ("memory_used_mib", "Memory", "MiB"),
    ("rx_mbps", "Receive bandwidth", "Mbps"),
    ("tx_mbps", "Transmit bandwidth", "Mbps"),
    ("total_mbps", "Total bandwidth", "Mbps"),
):
    values = [float(row[key]) for row in rows]
    print(f"{label}: mean={statistics.mean(values):.3f}{unit} peak={max(values):.3f}{unit}")
PY

echo "Trial finished $(date -u +%FT%TZ)"
echo "Saved metric CSV: $result_dir/metrics.csv"
