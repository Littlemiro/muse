import importlib.util
import unittest
from pathlib import Path

import yaml


MODULE_PATH = Path(__file__).resolve().parents[1] / "muse-enforce.py"
SPEC = importlib.util.spec_from_file_location("muse_enforce", MODULE_PATH)
muse_enforce = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(muse_enforce)


class MuseEnforceTests(unittest.TestCase):
    def test_frontmatter_serializer_roundtrips_nested_metadata(self):
        value = {
            "name": "demo",
            "description": "Use demo: safely",
            "metadata": {"hermes": {"tags": ["one", "two"], "enabled": True}},
        }
        serialized = muse_enforce.dict_to_yaml(value)
        body = serialized.removeprefix("---\n").removesuffix("\n---")
        self.assertEqual(yaml.safe_load(body), value)


if __name__ == "__main__":
    unittest.main()
