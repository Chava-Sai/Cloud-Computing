"""Laptop Pub/Sub subscriber using keyless service account impersonation."""

import argparse
import json
import subprocess
import sys
from datetime import datetime, timedelta

from google.api_core.exceptions import NotFound, PreconditionFailed
from google.auth.credentials import Credentials
from google.cloud import pubsub_v1, storage


class GcloudImpersonatedCredentials(Credentials):
    """Refresh short-lived SA tokens with the user's gcloud CLI login."""

    def __init__(self, service_account):
        super().__init__()
        self.service_account = service_account

    def refresh(self, request):
        result = subprocess.run(
            [
                "gcloud", "auth", "print-access-token",
                f"--impersonate-service-account={self.service_account}",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        self.token = result.stdout.strip()
        if not self.token:
            raise RuntimeError("gcloud returned an empty impersonated token")
        # The default token lasts one hour; refresh well before expiry.
        self.expiry = datetime.utcnow() + timedelta(minutes=45)


def append_once(bucket, object_name, event, message_id):
    """Append one JSON line with generation checks and redelivery deduplication."""
    record = {"pubsub_message_id": message_id, **event}
    line = json.dumps(record, sort_keys=True, ensure_ascii=True) + "\n"
    for _ in range(8):
        blob = bucket.get_blob(object_name)
        if blob is None:
            current = b""
            generation = 0
        else:
            generation = blob.generation
            try:
                current = blob.download_as_bytes(if_generation_match=generation)
            except (NotFound, PreconditionFailed):
                continue
            if any(
                json.loads(existing).get("pubsub_message_id") == message_id
                for existing in current.decode("utf-8").splitlines() if existing
            ):
                return False
        target = bucket.blob(object_name)
        try:
            target.upload_from_string(
                current + line.encode("utf-8"),
                content_type="application/x-ndjson",
                if_generation_match=generation,
            )
            return True
        except PreconditionFailed:
            continue
    raise RuntimeError("Could not append after eight concurrent update retries")


def main():
    parser = argparse.ArgumentParser(description="Log forbidden requests on this laptop")
    parser.add_argument("--project", default="thermal-circle-508221-m7")
    parser.add_argument("--bucket", default="thermal-circle-508221-m7-hw2")
    parser.add_argument("--subscription", default="hw3-forbidden-local")
    parser.add_argument("--service-account", default="hw3-microservices@thermal-circle-508221-m7.iam.gserviceaccount.com")
    parser.add_argument("--output-object", default="forbidden/requests.jsonl")
    args = parser.parse_args()

    credentials = GcloudImpersonatedCredentials(args.service_account)
    credentials.refresh(None)
    subscriber = pubsub_v1.SubscriberClient(credentials=credentials)
    storage_client = storage.Client(project=args.project, credentials=credentials)
    bucket = storage_client.bucket(args.bucket)
    subscription_path = subscriber.subscription_path(args.project, args.subscription)

    def on_message(message):
        try:
            event = json.loads(message.data.decode("utf-8"))
            if not isinstance(event, dict):
                raise ValueError("Message payload must be a JSON object")
            added = append_once(bucket, args.output_object, event, message.message_id)
            if added:
                print(
                    f"DENIED: country={event.get('country', '?')} "
                    f"method={event.get('method', '?')} file={event.get('file', '?')} "
                    f"at={event.get('timestamp', '?')}",
                    flush=True,
                )
            message.ack()
        except Exception as exc:
            print(f"Could not process Pub/Sub message: {exc}", file=sys.stderr, flush=True)
            message.nack()

    print(f"Listening on {subscription_path}; appending to gs://{args.bucket}/{args.output_object}", flush=True)
    future = subscriber.subscribe(
        subscription_path,
        callback=on_message,
        flow_control=pubsub_v1.types.FlowControl(max_messages=1),
    )
    try:
        future.result()
    except KeyboardInterrupt:
        future.cancel()
        future.result()
    finally:
        subscriber.close()


if __name__ == "__main__":
    main()
