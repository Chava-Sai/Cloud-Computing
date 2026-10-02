# Cloud Computing Homework 3

This project uses the Homework 2 bucket `gs://thermal-circle-508221-m7-hw2`.
The first service is a Python HTTP Cloud Run function. The second service is a
Python Pub/Sub subscriber that runs on the laptop. Both use the user-managed
service account `hw3-microservices@thermal-circle-508221-m7.iam.gserviceaccount.com`.

## Request behavior

| Request | Result |
| --- | --- |
| `GET /0.html` | 200 and the contents of `hw2/0.html` |
| `POST /` with JSON `{"file":"0.html"}` | 200 and the same contents |
| GET or POST for a missing file | 404, text and structured logs |
| PUT, DELETE, HEAD, OPTIONS, PATCH | 501, text and structured logs |
| TRACE, CONNECT | Function code returns 501 if called directly; Cloud Run rejects these methods before delivery (live endpoint: 405 and 400, respectively) |
| GET or POST with `X-country: Iran` (or any homework-forbidden country) | 400, plus a Pub/Sub notification |

The homework country list is a **simulation**, not a statement of current
export-control law. The first service trusts the caller-supplied `X-country`
header for demonstration only. The Homework 2 bucket remains publicly readable
from the prior assignment, so this demo does not make its files confidential.

## Resource configuration

Project: `thermal-circle-508221-m7`; region: `us-central1`.

The service account has `roles/storage.objectUser` on the Homework 2 bucket,
`roles/pubsub.publisher` on the `hw3-forbidden` topic, and
`roles/pubsub.subscriber` on the `hw3-forbidden-local` subscription. The human
user `saichava@bu.edu` has `roles/iam.serviceAccountTokenCreator` on the
service account to allow short-lived impersonation from the laptop.

## Deploy the first service

Run from this `HW-3` directory after `gcloud auth login` and setting the project:

```sh
gcloud functions deploy hw3-file-service \
  --gen2 \
  --runtime=python313 \
  --region=us-central1 \
  --source=first_service \
  --entry-point=serve_file \
  --trigger-http \
  --allow-unauthenticated \
  --service-account=hw3-microservices@thermal-circle-508221-m7.iam.gserviceaccount.com \
  --set-env-vars=PROJECT_ID=thermal-circle-508221-m7,BUCKET_NAME=thermal-circle-508221-m7-hw2,BUCKET_PREFIX=hw2/,TOPIC_ID=hw3-forbidden

gcloud functions describe hw3-file-service \
  --gen2 --region=us-central1 --format='value(serviceConfig.uri)'
```

Save the returned URL as `URL` in the shell, for example
`URL='https://YOUR-RETURNED-URL'`.

## Test with curl

```sh
curl -i "$URL/0.html"
curl -i -X POST "$URL/" -H 'Content-Type: application/json' -d '{"file":"0.html"}'
curl -i "$URL/does-not-exist.html"
curl -i -X PUT "$URL/0.html"
curl -i "$URL/0.html" -H 'X-country: Iran'
curl -i "$URL/0.html" -H 'X-country: North Korea'
```

For the 501 requirement, test PUT, DELETE, OPTIONS, and PATCH with
`curl -i -X METHOD`; use `curl -I "$URL/0.html"` for HEAD. Google documents
that Cloud Run does not deliver TRACE or CONNECT to services, so the deployed
function cannot turn them into 501 responses or application log entries:
https://docs.cloud.google.com/run/docs/known-issues#http_methods . Our live
tests returned 405 for TRACE and 400 for CONNECT on both the `run.app` and
`cloudfunctions.net` URLs. This is a documented platform limitation and an
unmet literal part of the homework specification.

## Run the laptop subscriber

This deliberately does **not** use `gcloud auth application-default login` or
a downloaded service account key. The program asks the authenticated `gcloud`
CLI to impersonate the service account. `gcloud` uses the user's Token Creator
grant to obtain a short-lived service account access token, which the Python
Google Cloud libraries use and refresh as needed.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r second_service/requirements.txt
.venv/bin/python second_service/forbidden_listener.py
```

Keep this terminal running. Send forbidden-country curl requests from another
terminal. The listener prints each denial to standard output and appends one
JSON line per Pub/Sub message to
`gs://thermal-circle-508221-m7-hw2/forbidden/requests.jsonl`.
It acknowledges messages only after the append succeeds. Message IDs prevent
duplicates after Pub/Sub redelivery; Cloud Storage generation preconditions
protect concurrent updates. View the file with:

```sh
gcloud storage cat gs://thermal-circle-508221-m7-hw2/forbidden/requests.jsonl
```

## Cloud Logging evidence

```sh
gcloud logging read \
  'resource.type="cloud_run_revision" AND resource.labels.service_name="hw3-file-service" AND (jsonPayload.event="file_not_found" OR jsonPayload.event="unsupported_method" OR jsonPayload.event="forbidden_country")' \
  --project=thermal-circle-508221-m7 --limit=30 --format=json
```

The function prints a plain text line and a single-line JSON log entry for
each erroneous request. Cloud Run forwards these to Cloud Logging as
`textPayload` and `jsonPayload`, respectively.

## Browser demonstration

Navigate directly to `$URL/0.html` for 200 and to
`$URL/does-not-exist.html` for 404. For POST, 400, and 501, use the browser's
Developer Tools Console to run `fetch` requests; capture the Console showing
both the request and returned status. The browser address bar only sends GET.
The final report includes the exact snippets and screenshots.

## Supplied HTTP client

The professor-supplied `http-client` is a macOS Apple Silicon executable with
**no filename extension**. Keep its original name. Set the executable bit with
`chmod u+x ~/Downloads/http-client`. The verified flags for this assignment are:

```sh
HOST="${URL#https://}"
~/Downloads/http-client -d "$HOST" -b none -w none -n 100 -i 11999 -p 443 -s -v
```

Use the host from the Cloud Run `serviceConfig.uri` URL, with no path or trailing
slash. `-b none -w none` makes the client request paths such as `/2857.html`;
`-i 11999` selects Homework 2 files numbered from `0.html` to `11999.html`.
The client adds `X-country` itself. Capture its final result for the report.
