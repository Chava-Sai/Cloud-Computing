#!/usr/bin/env bash
# Run 1-4 copies of the provided client for one timed trial on the client VM.
set -euo pipefail

clients="${1:?client count required}"
duration="${2:?duration required}"
web_ip="${3:?web IP required}"
run_id="${4:?run ID required}"

if [[ ! "$clients" =~ ^[1-4]$ ]] || [[ ! "$duration" =~ ^[1-9][0-9]*$ ]] ||
   [[ ! "$web_ip" =~ ^[0-9.]+$ ]] || [[ ! "$run_id" =~ ^[A-Za-z0-9-]+$ ]]; then
  echo "Invalid trial arguments" >&2
  exit 2
fi
if [[ ! -x "$HOME/http-client" ]]; then
  echo "The provided http-client is missing or not executable" >&2
  exit 2
fi

result_dir="$HOME/hw4-stress/$run_id"
mkdir -p "$result_dir"
deadline=$(($(date +%s) + duration))
echo "Trial $run_id: $clients concurrent client processes for $duration seconds"

for ((worker = 1; worker <= clients; worker++)); do
  (
    batches=0
    failed_batches=0
    log_file="$result_dir/client-$worker.log"
    while (( $(date +%s) < deadline )); do
      # Twenty requests per batch keeps the trial responsive if the server stalls.
      # -t limits each request; timeout limits the entire batch. Never use -v here.
      if timeout 30s "$HOME/http-client" -d "$web_ip" -b none -w none \
          -n 20 -i 11999 -p 8080 -t 10 >>"$log_file" 2>&1; then
        :
      else
        failed_batches=$((failed_batches + 1))
      fi
      batches=$((batches + 1))
    done
    printf 'worker=%d batches=%d failed_batches=%d\n' \
      "$worker" "$batches" "$failed_batches" >"$result_dir/worker-$worker.txt"
  ) &
done
wait

for ((worker = 1; worker <= clients; worker++)); do
  cat "$result_dir/worker-$worker.txt"
  if [[ -s "$result_dir/client-$worker.log" ]]; then
    echo "client-$worker output (last 5 lines):"
    tail -n 5 "$result_dir/client-$worker.log"
  fi
done
