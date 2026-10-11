"""HW4 VM adaptation of the HW3 Pub/Sub forbidden-country listener."""

import argparse
import json
import os
import sys
from concurrent.futures import CancelledError


def process_message(message, output=None, errors=None):
    """Print a denial and acknowledge only after it reaches stdout."""
    output = output or sys.stdout
    errors = errors or sys.stderr
    try:
        event = json.loads(message.data.decode("utf-8"))
        if not isinstance(event, dict):
            raise ValueError("Message payload must be a JSON object")
        print(
            f"DENIED: country={event.get('country', '?')} "
            f"method={event.get('method', '?')} file={event.get('file', '?')} "
            f"at={event.get('timestamp', '?')}",
            file=output,
            flush=True,
        )
        message.ack()
    except Exception as exc:
        print(f"Could not process Pub/Sub message: {exc}", file=errors, flush=True)
        message.nack()


def main():
    parser = argparse.ArgumentParser(description="Print forbidden file requests on VM3")
    parser.add_argument("--project", default=os.environ.get("PROJECT_ID", "thermal-circle-508221-m7"))
    parser.add_argument("--subscription", default=os.environ.get("SUBSCRIPTION_ID", "hw4-forbidden-vm"))
    args = parser.parse_args()

    # On Compute Engine, SubscriberClient uses the attached VM service account.
    # No user login or long-lived service account key is needed.
    from google.cloud import pubsub_v1

    subscriber = pubsub_v1.SubscriberClient()
    subscription_path = subscriber.subscription_path(args.project, args.subscription)
    future = subscriber.subscribe(
        subscription_path,
        callback=process_message,
        flow_control=pubsub_v1.types.FlowControl(max_messages=10),
    )
    print(f"Listening on {subscription_path}", flush=True)
    try:
        future.result()
    except KeyboardInterrupt:
        future.cancel()
        try:
            future.result(timeout=10)
        except CancelledError:
            pass
    finally:
        subscriber.close()


if __name__ == "__main__":
    main()
