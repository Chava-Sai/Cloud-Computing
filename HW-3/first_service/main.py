"""HTTP Cloud Run function for Homework 3."""

import json
import mimetypes
import os
import posixpath
from datetime import datetime, timezone

import functions_framework
from flask import Response
from google.api_core.exceptions import NotFound
from google.cloud import pubsub_v1, storage


PROJECT_ID = os.environ.get("PROJECT_ID", "thermal-circle-508221-m7")
BUCKET_NAME = os.environ.get("BUCKET_NAME", "thermal-circle-508221-m7-hw2")
BUCKET_PREFIX = os.environ.get("BUCKET_PREFIX", "hw2/").strip("/") + "/"
TOPIC_ID = os.environ.get("TOPIC_ID", "hw3-forbidden")

# This is the simulated policy specified by the homework, not legal advice.
FORBIDDEN_COUNTRIES = {
    "north korea", "iran", "cuba", "myanmar", "iraq", "libya",
    "sudan", "zimbabwe", "syria",
}
COUNTRY_CODES = {
    "kp": "north korea", "ir": "iran", "cu": "cuba", "mm": "myanmar",
    "iq": "iraq", "ly": "libya", "sd": "sudan", "zw": "zimbabwe",
    "sy": "syria",
}

_storage_client = None
_publisher = None


def storage_client():
    global _storage_client
    if _storage_client is None:
        _storage_client = storage.Client(project=PROJECT_ID)
    return _storage_client


def publisher_client():
    global _publisher
    if _publisher is None:
        _publisher = pubsub_v1.PublisherClient()
    return _publisher


def log_error(request, status, event, message, **extra):
    """Print both a text line and a Cloud Logging structured JSON line."""
    print(f"{status} {event}: {message}", flush=True)
    entry = {
        "severity": "WARNING" if status < 500 else "ERROR",
        "message": message,
        "event": event,
        "status": status,
        "method": request.method,
        "path": request.path,
        **extra,
    }
    trace_header = request.headers.get("X-Cloud-Trace-Context")
    if trace_header:
        trace_id = trace_header.split("/", 1)[0]
        entry["logging.googleapis.com/trace"] = (
            f"projects/{PROJECT_ID}/traces/{trace_id}"
        )
    print(json.dumps(entry, ensure_ascii=True, sort_keys=True), flush=True)


def requested_file(request):
    if request.method == "GET":
        name = request.path.lstrip("/")
    elif request.is_json:
        payload = request.get_json(silent=True)
        name = payload.get("file", "") if isinstance(payload, dict) else ""
    elif request.form:
        name = request.form.get("file", "")
    else:
        name = request.get_data(as_text=True).strip()

    if not isinstance(name, str):
        return ""
    name = name.strip().lstrip("/")
    if name.startswith(BUCKET_PREFIX):
        name = name[len(BUCKET_PREFIX):]
    # Files are addressed relative to hw2/, never as arbitrary bucket paths.
    if not name or name in (".", "..") or "\\" in name:
        return ""
    if posixpath.normpath(name) != name or any(p in ("", ".", "..") for p in name.split("/")):
        return ""
    return name


def normalized_country(value):
    country = " ".join(value.casefold().replace("-", " ").replace("_", " ").split())
    return COUNTRY_CODES.get(country, country)


@functions_framework.http
def serve_file(request):
    if request.method not in ("GET", "POST"):
        message = f"HTTP method {request.method} is not implemented"
        log_error(request, 501, "unsupported_method", message)
        return Response(message + "\n", status=501, mimetype="text/plain")

    name = requested_file(request)
    country = normalized_country(request.headers.get("X-country", ""))
    if country in FORBIDDEN_COUNTRIES:
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "country": country,
            "file": name,
            "method": request.method,
        }
        try:
            client = publisher_client()
            topic = client.topic_path(PROJECT_ID, TOPIC_ID)
            client.publish(topic, json.dumps(event).encode("utf-8")).result(timeout=10)
        except Exception as exc:
            log_error(request, 503, "publish_failed", "Forbidden request could not be forwarded", error=str(exc))
            return Response("Notification unavailable\n", status=503, mimetype="text/plain")
        log_error(request, 400, "forbidden_country", "Permission denied by homework country policy", country=country, file=name)
        return Response("Permission denied\n", status=400, mimetype="text/plain")

    if not name:
        log_error(request, 404, "file_not_found", "File not found", file=name)
        return Response("File not found\n", status=404, mimetype="text/plain")

    blob = storage_client().bucket(BUCKET_NAME).blob(BUCKET_PREFIX + name)
    try:
        data = blob.download_as_bytes()
    except NotFound:
        log_error(request, 404, "file_not_found", "File not found", file=name)
        return Response("File not found\n", status=404, mimetype="text/plain")

    content_type = blob.content_type or mimetypes.guess_type(name)[0] or "application/octet-stream"
    return Response(data, status=200, content_type=content_type)
