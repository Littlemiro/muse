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

    def test_enforce_does_not_invent_provenance_or_routing_metadata(self):
        with self.subTest("dry run report does not mutate source metadata"):
            import tempfile

            with tempfile.TemporaryDirectory() as temp:
                skill_dir = Path(temp) / "research" / "demo"
                skill_dir.mkdir(parents=True)
                marker = skill_dir / "SKILL.md"
                original = "---\nname: demo\ndescription: A demo workflow\n---\n\n# Demo\n"
                marker.write_text(original, encoding="utf-8")
                muse_enforce.enforce(Path(temp), dry_run=True)
                self.assertEqual(marker.read_text(encoding="utf-8"), original)

                muse_enforce.enforce(Path(temp), dry_run=False)
                updated = yaml.safe_load(marker.read_text(encoding="utf-8").split("---")[1])
                self.assertNotIn("author", updated)
                self.assertNotIn("license", updated)
                self.assertNotIn("platforms", updated)
                self.assertNotIn("trigger_keywords", updated)

    def test_enforce_skips_archived_skill_directories(self):
        import tempfile

        with tempfile.TemporaryDirectory() as temp:
            archive_dir = Path(temp) / ".archive" / "research" / "old"
            archive_dir.mkdir(parents=True)
            marker = archive_dir / "SKILL.md"
            original = "---\nname: old\ndescription: A historical skill\n---\n\n# Old\n"
            marker.write_text(original, encoding="utf-8")
            muse_enforce.enforce(Path(temp), dry_run=False)
            self.assertEqual(marker.read_text(encoding="utf-8"), original)


if __name__ == "__main__":
    unittest.main()
