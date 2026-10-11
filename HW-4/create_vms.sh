#!/usr/bin/env bash
# From this directory: PROJECT_ID=your-project-id bash create_vms.sh
# Creates the HW4 web and reporter VMs plus their narrowly scoped identities.
set -euo pipefail

: "${PROJECT_ID:?Set PROJECT_ID, for example PROJECT_ID=thermal-circle-508221-m7}"
BUCKET_NAME="${BUCKET_NAME:-${PROJECT_ID}-hw2}"
BUCKET_PREFIX="${BUCKET_PREFIX:-hw2/}"
REGION="${REGION:-us-central1}"
ZONE="${ZONE:-us-central1-a}"
WEB_MACHINE_TYPE="${WEB_MACHINE_TYPE:-f1-micro}"
REPORTER_MACHINE_TYPE="${REPORTER_MACHINE_TYPE:-e2-micro}"

if [[ ! "$PROJECT_ID" =~ ^[a-z][a-z0-9-]+$ ]] ||
   [[ ! "$BUCKET_NAME" =~ ^[a-z0-9._-]+$ ]] ||
   [[ ! "$BUCKET_PREFIX" =~ ^[a-zA-Z0-9/_-]+$ ]] ||
   [[ ! "$REGION" =~ ^[a-z0-9-]+$ ]] ||
   [[ ! "$ZONE" =~ ^[a-z0-9-]+$ ]]; then
  echo "Invalid project, bucket, prefix, region, or zone value" >&2
  exit 2
fi

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
web_sa="hw4-web@${PROJECT_ID}.iam.gserviceaccount.com"
reporter_sa="hw4-reporter@${PROJECT_ID}.iam.gserviceaccount.com"
topic_id="hw4-forbidden"
subscription_id="hw4-forbidden-vm"
address_name="hw4-web-ip"
firewall_name="hw4-allow-web-8080"
web_vm="hw4-web"
reporter_vm="hw4-reporter"

gc() { gcloud --project="$PROJECT_ID" "$@"; }

echo "Checking project and Homework 2 bucket..."
gc projects describe "$PROJECT_ID" >/dev/null
gc storage buckets describe "gs://$BUCKET_NAME" >/dev/null
gc storage ls "gs://$BUCKET_NAME/${BUCKET_PREFIX%/}/0.html" >/dev/null

echo "Enabling the services used by the two VMs..."
gc services enable compute.googleapis.com iam.googleapis.com pubsub.googleapis.com \
  logging.googleapis.com --quiet >/dev/null

echo "Creating dedicated VM service accounts..."
if ! gc iam service-accounts describe "$web_sa" >/dev/null 2>&1; then
  gc iam service-accounts create hw4-web --display-name="HW4 web VM" --quiet
fi
if ! gc iam service-accounts describe "$reporter_sa" >/dev/null 2>&1; then
  gc iam service-accounts create hw4-reporter --display-name="HW4 reporter VM" --quiet
fi

echo "Creating the Pub/Sub channel..."
if ! gc pubsub topics describe "$topic_id" >/dev/null 2>&1; then
  gc pubsub topics create "$topic_id" --quiet
fi
if ! gc pubsub subscriptions describe "$subscription_id" >/dev/null 2>&1; then
  gc pubsub subscriptions create "$subscription_id" --topic="$topic_id" --quiet
fi

echo "Granting only the permissions each program uses..."
gc storage buckets add-iam-policy-binding "gs://$BUCKET_NAME" \
  --member="serviceAccount:$web_sa" --role=roles/storage.objectViewer --quiet >/dev/null
gc pubsub topics add-iam-policy-binding "$topic_id" \
  --member="serviceAccount:$web_sa" --role=roles/pubsub.publisher --quiet >/dev/null
gc projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:$web_sa" --role=roles/logging.logWriter \
  --condition=None --quiet >/dev/null
gc pubsub subscriptions add-iam-policy-binding "$subscription_id" \
  --member="serviceAccount:$reporter_sa" --role=roles/pubsub.subscriber --quiet >/dev/null

echo "Reserving a static external IP and opening only the web port..."
if ! gc compute addresses describe "$address_name" --region="$REGION" >/dev/null 2>&1; then
  gc compute addresses create "$address_name" --region="$REGION" --quiet
fi
web_ip="$(gc compute addresses describe "$address_name" --region="$REGION" --format='value(address)')"
if ! gc compute firewall-rules describe "$firewall_name" >/dev/null 2>&1; then
  gc compute firewall-rules create "$firewall_name" \
    --network=default --direction=INGRESS --allow=tcp:8080 \
    --source-ranges=0.0.0.0/0 --target-tags=hw4-web --quiet
fi

echo "Creating the web VM ($WEB_MACHINE_TYPE, $ZONE)..."
if ! gc compute instances describe "$web_vm" --zone="$ZONE" >/dev/null 2>&1; then
  gc compute instances create "$web_vm" \
    --zone="$ZONE" --machine-type="$WEB_MACHINE_TYPE" \
    --image-family=debian-12 --image-project=debian-cloud \
    --boot-disk-type=pd-standard --boot-disk-size=10GB \
    --address="$web_ip" --tags=hw4-web \
    --labels=homework=hw4,role=web \
    --service-account="$web_sa" --scopes=cloud-platform \
    --metadata="hw4-bucket=$BUCKET_NAME,hw4-prefix=$BUCKET_PREFIX,hw4-topic=$topic_id" \
    --metadata-from-file="startup-script=$script_dir/startup_web.sh,hw4-server-py=$script_dir/first_service/server.py,hw4-server-requirements=$script_dir/first_service/requirements.txt,hw4-metrics-py=$script_dir/first_service/metrics.py" \
    --quiet
else
  echo "Web VM already exists; leaving its running code unchanged."
fi

echo "Creating the reporter VM ($REPORTER_MACHINE_TYPE, $ZONE)..."
if ! gc compute instances describe "$reporter_vm" --zone="$ZONE" >/dev/null 2>&1; then
  gc compute instances create "$reporter_vm" \
    --zone="$ZONE" --machine-type="$REPORTER_MACHINE_TYPE" \
    --image-family=debian-12 --image-project=debian-cloud \
    --boot-disk-type=pd-standard --boot-disk-size=10GB \
    --labels=homework=hw4,role=reporter \
    --service-account="$reporter_sa" --scopes=cloud-platform \
    --metadata="hw4-subscription=$subscription_id" \
    --metadata-from-file="startup-script=$script_dir/startup_reporter.sh,hw4-listener-py=$script_dir/second_service/forbidden_listener.py,hw4-listener-requirements=$script_dir/second_service/requirements.txt" \
    --quiet
else
  echo "Reporter VM already exists; leaving its running code unchanged."
fi

echo "Web address: http://$web_ip:8080/0.html"
echo "VMs: $web_vm and $reporter_vm in $ZONE"
echo "The startup scripts install dependencies and start both services automatically."
