"""Exercise the real HTTP handler without contacting Google Cloud."""

import http.client
import json
import sys
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock

from google.api_core.exceptions import NotFound

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "first_service"))
from server import FileHTTPServer, FileService  # noqa: E402


class FakeBlob:
    def __init__(self, name):
        self.name = name

    def download_as_bytes(self, **_kwargs):
        if self.name == "hw2/0.html":
            return b"<h1>HW2 file</h1>"
        raise NotFound("missing")


class FakeBucket:
    def blob(self, name):
        return FakeBlob(name)


class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.publisher = Mock()
        cls.publisher.publish.return_value.result.return_value = "message-1"
        cls.logger = Mock()
        app = FileService(FakeBucket(), "hw2/", cls.publisher, "projects/test/topics/test", cls.logger)
        cls.server = FileHTTPServer(("127.0.0.1", 0), app)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=3)

    def setUp(self):
        self.logger.reset_mock()
        self.publisher.reset_mock()
        self.publisher.publish.return_value.result.return_value = "message-1"

    def request(self, method, path, body=None, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        try:
            conn.request(method, path, body=body, headers=headers or {})
            response = conn.getresponse()
            return response.status, response.read(), dict(response.getheaders())
        finally:
            conn.close()

    def test_get_and_post_serve_bucket_file(self):
        status, body, _ = self.request("GET", "/0.html")
        self.assertEqual((status, body), (200, b"<h1>HW2 file</h1>"))
        status, body, _ = self.request(
            "POST", "/", json.dumps({"file": "0.html"}),
            {"Content-Type": "application/json"},
        )
        self.assertEqual((status, body), (200, b"<h1>HW2 file</h1>"))

    def test_missing_file_has_warning_log(self):
        status, _, _ = self.request("GET", "/missing.html")
        self.assertEqual(status, 404)
        record = self.logger.log_struct.call_args
        self.assertEqual(record.kwargs["severity"], "WARNING")
        self.assertEqual(record.args[0]["event"], "file_not_found")

    def test_every_other_method_has_error_log(self):
        for method in ("PUT", "DELETE", "HEAD", "CONNECT", "OPTIONS", "TRACE", "PATCH"):
            with self.subTest(method=method):
                self.logger.reset_mock()
                status, body, _ = self.request(method, "/0.html")
                self.assertEqual(status, 501)
                if method == "HEAD":
                    self.assertEqual(body, b"")
                self.assertEqual(self.logger.log_struct.call_args.kwargs["severity"], "ERROR")

    def test_forbidden_country_has_critical_log_and_notification(self):
        status, body, _ = self.request("GET", "/0.html", headers={"X-country": "Iran"})
        self.assertEqual((status, body), (400, b"Permission denied\n"))
        self.assertEqual(self.logger.log_struct.call_args.kwargs["severity"], "CRITICAL")
        payload = json.loads(self.publisher.publish.call_args.args[1])
        self.assertEqual((payload["country"], payload["file"]), ("iran", "0.html"))

    def test_path_traversal_does_not_leave_bucket_prefix(self):
        status, _, _ = self.request("GET", "/%2e%2e/secret")
        self.assertEqual(status, 404)


if __name__ == "__main__":
    unittest.main()
