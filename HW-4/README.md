# Cloud Computing Homework 4 — VM services

This directory adapts the Homework 3 services to Compute Engine VMs. The web
server uses Python `http.server`, reads files from the Homework 2 bucket, writes
structured Cloud Logging entries, and publishes simulated forbidden-country
requests to Pub/Sub. The second service subscribes on a separate VM and prints
denials to its standard output.

## Source files

- `first_service/server.py`: GET and POST file service, 404/501 responses,
  structured WARNING/ERROR/CRITICAL logs, and Pub/Sub notifications.
- `second_service/forbidden_listener.py`: VM version of the HW3 subscriber.
- `first_service/metrics.py`: one-second CPU, memory, and bandwidth samples for
  the stress-test graph.
- `startup_web.sh`, `startup_reporter.sh`: install the programs and enable
  `systemd` services automatically when the VMs boot.
- `create_vms.sh`: one-command creation of both service VMs and their supporting
  IAM, Pub/Sub, IP, and firewall resources.
- `stress_client.sh`, `run_stress.sh`: run the supplied HTTP client on a third
  VM at 1–4 concurrent processes and record 3-minute web VM resource samples.

## One-command deployment

Run from this directory in a Google Cloud Shell logged into an account allowed
to create VMs, service accounts, Pub/Sub resources, a static IP, a firewall rule,
and the listed IAM bindings:

```bash
PROJECT_ID=thermal-circle-508221-m7 bash create_vms.sh
```

Defaults: bucket `gs://${PROJECT_ID}-hw2`, prefix `hw2/`, zone
`us-central1-a`, web VM `f1-micro`, reporter VM `e2-micro`, and web port `8080`.
Set `BUCKET_NAME`, `BUCKET_PREFIX`, `REGION`, `ZONE`, `WEB_MACHINE_TYPE`, or
`REPORTER_MACHINE_TYPE` in the environment before invoking the script to change
those values. The script checks that `0.html` exists under the selected prefix.

The script creates two distinct VM service accounts:

| VM identity | Resource | Role |
| --- | --- | --- |
| `hw4-web` | Homework 2 bucket | Storage Object Viewer |
| `hw4-web` | `hw4-forbidden` topic | Pub/Sub Publisher |
| `hw4-web` | Project | Logs Writer |
| `hw4-reporter` | `hw4-forbidden-vm` subscription | Pub/Sub Subscriber |

The VM OAuth scope is `cloud-platform`; IAM grants only the listed permissions.
The reporter's denial messages are available from its `systemd` journal. The
web VM's reserved external IP is printed by `create_vms.sh`. It serves files at
`http://IP:8080/0.html`.

The script is safe to rerun when its resources already exist. An existing VM
keeps its currently installed code; to apply source changes, recreate that VM
after preserving any evidence or metrics files needed for the report.

## Local checks completed before deployment

The HTTP handler and subscriber have unit tests that use local fakes, without
creating cloud resources:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r first_service/requirements.txt
.venv/bin/python -m unittest discover -s tests -v
bash -n create_vms.sh startup_web.sh startup_reporter.sh
```

Live VM, Cloud Logging, Pub/Sub, client, stress-test, and billing evidence must
be collected after deployment. The report will use actual results from those
runs, not estimates presented as measured values.

## Client VM and stress test

Create the client VM separately with Ubuntu 24.04 LTS x86-64. The supplied
Linux `http-client` requires GLIBC 2.38 or newer; Debian 12 is too old. The
client needs no Google Cloud service account because it only calls the web VM.
Upload the professor's Linux binary to Cloud Shell, copy it to the client VM,
and make it executable. A 100-request functional check is:

```bash
gcloud compute ssh hw4-client --zone=us-central1-a \
  --command='~/http-client -d WEB_STATIC_IP -b none -w none -n 100 -i 11999 -p 8080 -t 20'
```

From this directory in Cloud Shell, run one client count at a time:

```bash
PROJECT_ID=thermal-circle-508221-m7 bash run_stress.sh 1
PROJECT_ID=thermal-circle-508221-m7 bash run_stress.sh 2
PROJECT_ID=thermal-circle-508221-m7 bash run_stress.sh 3
PROJECT_ID=thermal-circle-508221-m7 bash run_stress.sh 4
```

Each trial uses the supplied client without `-v`, runs for 180 seconds, and
saves a web VM metric CSV and text summary under `stress-results/`. The script
rejects client counts above four. It starts at most four client processes.
