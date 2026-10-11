"""Check that synthetic fixtures can be reproduced byte for byte."""

import contextlib
import importlib.util
import io
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]


class InstanceGenerationTests(unittest.TestCase):
    def test_generator_reproduces_committed_instances(self):
        spec = importlib.util.spec_from_file_location(
            "generate_instances", ROOT / "scripts/generate_instances.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        generated = {}

        def capture_write(path, data):
            generated[path.relative_to(module.INSTANCE_DIR)] = data
            return len(data)

        # Capture the actual serialized bytes without touching committed data
        # or relying on the platform's temporary-directory permissions.
        with patch.object(Path, "mkdir"), patch.object(
                Path, "write_bytes", autospec=True, side_effect=capture_write):
            with contextlib.redirect_stdout(io.StringIO()):
                module.main()
        committed = sorted((ROOT / "instances").rglob("*.json"))
        self.assertEqual(len(committed), 10)
        self.assertEqual(len(generated), 10)
        for path in committed:
            relative = path.relative_to(ROOT / "instances")
            with self.subTest(instance=str(relative)):
                self.assertEqual(path.read_bytes(), generated[relative])


if __name__ == "__main__":
    unittest.main()
