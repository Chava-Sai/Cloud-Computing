"""Test the VM listener's acknowledgement and stdout behavior."""

import io
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "second_service"))
from forbidden_listener import process_message  # noqa: E402


class ListenerTests(unittest.TestCase):
    def test_prints_denial_then_acknowledges(self):
        message = Mock(data=json.dumps({
            "country": "iran", "method": "GET", "file": "0.html", "timestamp": "now"
        }).encode("utf-8"))
        output = io.StringIO()
        process_message(message, output=output)
        self.assertIn("DENIED: country=iran method=GET file=0.html", output.getvalue())
        message.ack.assert_called_once()
        message.nack.assert_not_called()

    def test_bad_payload_is_not_acknowledged(self):
        message = Mock(data=b"not json")
        errors = io.StringIO()
        process_message(message, errors=errors)
        self.assertIn("Could not process Pub/Sub message", errors.getvalue())
        message.nack.assert_called_once()
        message.ack.assert_not_called()


if __name__ == "__main__":
    unittest.main()
