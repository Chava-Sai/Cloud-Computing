"""Sample VM CPU, memory, and network use for the HW4 stress-test graph.

Run on the web VM during each client-count trial. This uses only Linux /proc
files, so sampling adds very little load to an f1-micro instance.
"""

import argparse
import csv
import time
from datetime import datetime, timezone
from pathlib import Path

PROC_ROOT = Path("/proc")


def cpu_counters():
    fields = (PROC_ROOT / "stat").read_text().splitlines()[0].split()[1:]
    values = [int(value) for value in fields]
    idle = values[3] + values[4]
    return sum(values), idle


def memory_bytes():
    values = {}
    for line in (PROC_ROOT / "meminfo").read_text().splitlines():
        key, raw = line.split(":", 1)
        if key in ("MemTotal", "MemAvailable"):
            values[key] = int(raw.strip().split()[0]) * 1024
    return values["MemTotal"], values["MemTotal"] - values["MemAvailable"]


def network_bytes():
    receive = transmit = 0
    for line in (PROC_ROOT / "net/dev").read_text().splitlines()[2:]:
        interface, counters = line.split(":", 1)
        if interface.strip() == "lo":
            continue
        fields = counters.split()
        receive += int(fields[0])
        transmit += int(fields[8])
    return receive, transmit


def sample(seconds, interval, output):
    previous_cpu = cpu_counters()
    previous_network = network_bytes()
    previous_time = time.monotonic()
    deadline = previous_time + seconds
    with open(output, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=(
            "timestamp_utc", "cpu_percent", "memory_used_mib", "memory_percent",
            "rx_mbps", "tx_mbps", "total_mbps",
        ))
        writer.writeheader()
        while time.monotonic() < deadline:
            time.sleep(min(interval, max(0, deadline - time.monotonic())))
            current_time = time.monotonic()
            current_cpu = cpu_counters()
            current_network = network_bytes()
            total_memory, used_memory = memory_bytes()
            elapsed = current_time - previous_time
            total_ticks = current_cpu[0] - previous_cpu[0]
            idle_ticks = current_cpu[1] - previous_cpu[1]
            cpu_percent = 100 * (1 - idle_ticks / total_ticks) if total_ticks else 0
            rx_mbps = 8 * (current_network[0] - previous_network[0]) / elapsed / 1_000_000
            tx_mbps = 8 * (current_network[1] - previous_network[1]) / elapsed / 1_000_000
            writer.writerow({
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "cpu_percent": round(cpu_percent, 2),
                "memory_used_mib": round(used_memory / 2**20, 2),
                "memory_percent": round(100 * used_memory / total_memory, 2),
                "rx_mbps": round(rx_mbps, 4),
                "tx_mbps": round(tx_mbps, 4),
                "total_mbps": round(rx_mbps + tx_mbps, 4),
            })
            handle.flush()
            previous_cpu, previous_network, previous_time = (
                current_cpu, current_network, current_time
            )


def main():
    parser = argparse.ArgumentParser(description="Record web VM resource use as CSV")
    parser.add_argument("--seconds", type=int, default=180)
    parser.add_argument("--interval", type=float, default=1.0)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    if args.seconds <= 0 or args.interval <= 0:
        parser.error("seconds and interval must be positive")
    if not (PROC_ROOT / "stat").exists():
        parser.error("this sampler must run on Linux, where /proc/stat exists")
    sample(args.seconds, args.interval, args.output)


if __name__ == "__main__":
    main()
