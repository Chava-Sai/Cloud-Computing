"""HW4 file service using Python's standard-library HTTP server."""

import argparse
import json
import mimetypes
import os
import posixpath
import sys
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlsplit

from google.api_core.exceptions import NotFound


FORBIDDEN_COUNTRIES = {
    "north korea", "iran", "cuba", "myanmar", "iraq", "libya",
    "sudan", "zimbabwe", "syria",
}
COUNTRY_CODES = {
    "kp": "north korea", "ir": "iran", "cu": "cuba", "mm": "myanmar",
    "iq": "iraq", "ly": "libya", "sd": "sudan", "zw": "zimbabwe",
    "sy": "syria",
}


def normalized_country(value):
    name = " ".join(value.casefold().replace("-", " ").replace("_", " ").split())
    return COUNTRY_CODES.get(name, name)


def safe_filename(value, prefix):
    """Accept only bucket-relative file names, never traversal or other objects."""
    if not isinstance(value, str):
        return ""
    value = unquote(value).strip().lstrip("/")
    if value.startswith(prefix):
        value = value[len(prefix):]
    if not value or "\\" in value or "\x00" in value:
        return ""
    if posixpath.normpath(value) != value:
        return ""
    if any(part in ("", ".", "..") for part in value.split("/")):
        return ""
    return value


class FileService:
    def __init__(self, bucket, prefix, publisher, topic_path, cloud_logger):
        self.bucket = bucket
        self.prefix = prefix.strip("/") + "/"
        self.publisher = publisher
        self.topic_path = topic_path
        self.cloud_logger = cloud_logger

    def log_event(self, severity, event, status, method, path, message, **extra):
        record = {
            "event": event,
            "status": status,
            "method": method,
            "path": path,
            "message": message,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **extra,
        }
        try:
            self.cloud_logger.log_struct(record, severity=severity)
        except Exception as exc:
            # Keep serving requests if Logging is briefly unavailable. The
            # fallback stays visible in the service's systemd journal.
            print(json.dumps({"log_failure": str(exc), **record}), file=sys.stderr, flush=True)


class FileRequestHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    @property
    def app(self):
        return self.server.app

    def reply(self, status, body, content_type="text/plain; charset=utf-8", *, head=False):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        if not head:
            self.wfile.write(body)
        self.close_connection = True

    def requested_filename(self):
        if self.command == "GET":
            value = urlsplit(self.path).path.lstrip("/")
        else:
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                return ""
            if length < 0 or length > 4096:
                return ""
            raw = self.rfile.read(length)
            media_type = self.headers.get("Content-Type", "").split(";", 1)[0].lower()
            try:
                body = raw.decode("utf-8")
                if media_type == "application/json":
                    payload = json.loads(body)
                    value = payload.get("file", "") if isinstance(payload, dict) else ""
                elif media_type == "application/x-www-form-urlencoded":
                    value = parse_qs(body).get("file", [""])[0]
                else:
                    value = body
            except (UnicodeDecodeError, json.JSONDecodeError):
                return ""
        return safe_filename(value, self.app.prefix)

    def serve_file(self):
        path = urlsplit(self.path).path
        name = self.requested_filename()
        country = normalized_country(self.headers.get("X-country", ""))

        if country in FORBIDDEN_COUNTRIES:
            event = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "country": country,
                "file": name,
                "method": self.command,
                "client_ip": self.client_address[0],
            }
            self.app.log_event(
                "CRITICAL", "forbidden_country", 400, self.command, path,
                "Permission denied by homework country policy", country=country, file=name,
            )
            try:
                self.app.publisher.publish(
                    self.app.topic_path, json.dumps(event).encode("utf-8")
                ).result(timeout=10)
            except Exception as exc:
                self.app.log_event(
                    "ERROR", "publish_failed", 503, self.command, path,
                    "Forbidden request could not be forwarded", error=str(exc),
                )
                self.reply(503, b"Notification unavailable\n")
                return
            self.reply(400, b"Permission denied\n")
            return

        if not name:
            self.app.log_event(
                "WARNING", "file_not_found", 404, self.command, path,
                "File not found", file=name,
            )
            self.reply(404, b"File not found\n")
            return

        blob = self.app.bucket.blob(self.app.prefix + name)
        try:
            data = blob.download_as_bytes(timeout=30)
        except NotFound:
            self.app.log_event(
                "WARNING", "file_not_found", 404, self.command, path,
                "File not found", file=name,
            )
            self.reply(404, b"File not found\n")
            return
        except Exception as exc:
            self.app.log_event(
                "ERROR", "storage_failed", 503, self.command, path,
                "Cloud Storage request failed", error=str(exc), file=name,
            )
            self.reply(503, b"Storage unavailable\n")
            return

        content_type = mimetypes.guess_type(name)[0] or "application/octet-stream"
        self.reply(200, data, content_type)

    def unsupported_method(self):
        path = urlsplit(self.path).path
        self.app.log_event(
            "ERROR", "unsupported_method", 501, self.command, path,
            f"HTTP method {self.command} is not implemented",
        )
        self.reply(
            501, f"HTTP method {self.command} is not implemented\n".encode("utf-8"),
            head=self.command == "HEAD",
        )

    do_GET = serve_file
    do_POST = serve_file
    do_PUT = unsupported_method
    do_DELETE = unsupported_method
    do_HEAD = unsupported_method
    do_CONNECT = unsupported_method
    do_OPTIONS = unsupported_method
    do_TRACE = unsupported_method
    do_PATCH = unsupported_method


class FileHTTPServer(ThreadingHTTPServer):
    request_queue_size = 128
    daemon_threads = True

    def __init__(self, address, app):
        self.app = app
        super().__init__(address, FileRequestHandler)


def main():
    parser = argparse.ArgumentParser(description="HW4 Cloud Storage HTTP service")
    parser.add_argument("--project", default=os.environ.get("PROJECT_ID", "thermal-circle-508221-m7"))
    parser.add_argument("--bucket", default=os.environ.get("BUCKET_NAME", "thermal-circle-508221-m7-hw2"))
    parser.add_argument("--prefix", default=os.environ.get("BUCKET_PREFIX", "hw2/"))
    parser.add_argument("--topic", default=os.environ.get("TOPIC_ID", "hw4-forbidden"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8080")))
    args = parser.parse_args()

    from google.cloud import logging_v2, pubsub_v1, storage

    storage_client = storage.Client(project=args.project)
    publisher = pubsub_v1.PublisherClient()
    cloud_logger = logging_v2.Client(project=args.project).logger("hw4-file-service")
    app = FileService(
        bucket=storage_client.bucket(args.bucket),
        prefix=args.prefix,
        publisher=publisher,
        topic_path=publisher.topic_path(args.project, args.topic),
        cloud_logger=cloud_logger,
    )
    server = FileHTTPServer(("0.0.0.0", args.port), app)
    print(f"Serving gs://{args.bucket}/{app.prefix} on port {args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
