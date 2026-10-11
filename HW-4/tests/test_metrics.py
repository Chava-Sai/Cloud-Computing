"""Check the Linux counter parser with representative /proc data."""

import importlib.util
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "first_service" / "metrics.py"
spec = importlib.util.spec_from_file_location("hw4_metrics", MODULE_PATH)
metrics = importlib.util.module_from_spec(spec)
spec.loader.exec_module(metrics)


class MetricsTests(unittest.TestCase):
    def test_proc_counters(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "net").mkdir()
            (root / "stat").write_text("cpu  100 20 30 400 50 0 0 0 0 0\n")
            (root / "meminfo").write_text("MemTotal: 614400 kB\nMemAvailable: 204800 kB\n")
            (root / "net/dev").write_text(
                "Inter-| Receive | Transmit\n face |bytes packets errs drop fifo frame compressed multicast |bytes packets errs drop fifo colls carrier compressed\n"
                "    lo: 100 0 0 0 0 0 0 0 100 0 0 0 0 0 0 0\n"
                "  ens4: 8000 0 0 0 0 0 0 0 12000 0 0 0 0 0 0 0\n"
            )
            original = metrics.PROC_ROOT
            metrics.PROC_ROOT = root
            try:
                self.assertEqual(metrics.cpu_counters(), (600, 450))
                self.assertEqual(metrics.memory_bytes(), (614400 * 1024, 409600 * 1024))
                self.assertEqual(metrics.network_bytes(), (8000, 12000))
            finally:
                metrics.PROC_ROOT = original


if __name__ == "__main__":
    unittest.main()
