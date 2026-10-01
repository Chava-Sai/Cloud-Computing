import importlib.util
import json
from pathlib import Path
from unittest.mock import Mock

import pytest
from flask import Flask
from google.api_core.exceptions import NotFound


ROOT = Path(__file__).resolve().parents[1]


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def first():
    module = load_module("first_service", ROOT / "first_service" / "main.py")
    blob = Mock(content_type="text/html")
    blob.download_as_bytes.return_value = b"<h1>sample</h1>"
    bucket = Mock()
    bucket.blob.return_value = blob
    storage_client = Mock()
    storage_client.bucket.return_value = bucket
    module._storage_client = storage_client
    publisher = Mock()
    publisher.topic_path.return_value = "projects/test/topics/test"
    publisher.publish.return_value.result.return_value = "message-1"
    module._publisher = publisher
    return module, blob, bucket, publisher


def invoke(module, method, path, **kwargs):
    app = Flask(__name__)
    with app.test_request_context(path, method=method, **kwargs):
        from flask import request
        return module.serve_file(request)


def test_get_and_post_return_existing_file(first):
    module, blob, bucket, _ = first
    get_result = invoke(module, "GET", "/0.html")
    post_result = invoke(module, "POST", "/", json={"file": "1.html"})
    assert (get_result.status_code, get_result.data) == (200, b"<h1>sample</h1>")
    assert (post_result.status_code, post_result.data) == (200, b"<h1>sample</h1>")
    assert [call.args[0] for call in bucket.blob.call_args_list] == ["hw2/0.html", "hw2/1.html"]


def test_missing_file_and_all_unsupported_methods(first):
    module, blob, _, _ = first
    blob.download_as_bytes.side_effect = NotFound("missing")
    assert invoke(module, "GET", "/missing.html").status_code == 404
    for method in ("PUT", "DELETE", "HEAD", "CONNECT", "OPTIONS", "TRACE", "PATCH"):
        assert invoke(module, method, "/0.html").status_code == 501


def test_forbidden_country_publishes_before_denial(first):
    module, blob, _, publisher = first
    result = invoke(module, "GET", "/0.html", headers={"X-country": "Iran"})
    assert result.status_code == 400
    assert blob.download_as_bytes.call_count == 0
    payload = json.loads(publisher.publish.call_args.args[1])
    assert payload["country"] == "iran"
    assert payload["file"] == "0.html"


def test_append_is_idempotent():
    module = load_module("second_service", ROOT / "second_service" / "forbidden_listener.py")
    contents = {"data": b"", "generation": 0}

    class FakeBlob:
        def __init__(self):
            self.generation = contents["generation"]

        def download_as_bytes(self, **kwargs):
            return contents["data"]

        def upload_from_string(self, data, **kwargs):
            assert kwargs["if_generation_match"] == contents["generation"]
            contents["data"] = data
            contents["generation"] += 1

    class FakeBucket:
        def get_blob(self, name):
            return FakeBlob() if contents["generation"] else None

        def blob(self, name):
            return FakeBlob()

    event = {"country": "iran", "file": "0.html", "method": "GET"}
    assert module.append_once(FakeBucket(), "forbidden/requests.jsonl", event, "id-1")
    assert not module.append_once(FakeBucket(), "forbidden/requests.jsonl", event, "id-1")
    assert len(contents["data"].splitlines()) == 1
