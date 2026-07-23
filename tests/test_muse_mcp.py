import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


MODULE_PATH = Path(__file__).resolve().parents[1] / "muse-mcp-server.py"
SPEC = importlib.util.spec_from_file_location("muse_mcp_server", MODULE_PATH)
muse_mcp = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(muse_mcp)


class MuseMcpTests(unittest.TestCase):
    def test_default_path_is_approved_activation_directory(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp) / "hermes"
            with patch.dict(os.environ, {"HERMES_HOME": str(home)}):
                approved = home / ".muse" / "active" / "current"
                self.assertEqual(muse_mcp.default_skills_dir(), approved)
                self.assertTrue(muse_mcp.is_approved_export(approved))
                self.assertFalse(muse_mcp.is_approved_export(home / "skills"))

    def test_non_string_tags_are_normalized_before_prompt_rendering(self):
        with tempfile.TemporaryDirectory() as temp:
            marker = Path(temp) / "SKILL.md"
            marker.write_text(
                "---\n"
                "name: mixed\n"
                "description: A mixed metadata test\n"
                "metadata:\n"
                "  hermes:\n"
                "    tags: [one, 2]\n"
                "trigger_keywords: [three, 4]\n"
                "---\n\nRead and verify.\n",
                encoding="utf-8",
            )
            parsed = muse_mcp.parse_skill_md(marker)
            self.assertEqual(parsed["tags"], ["one", "2"])
            self.assertEqual(parsed["trigger_keywords"], ["three", "4"])
            self.assertIn("one, 2", muse_mcp.build_prompt_text(parsed))


if __name__ == "__main__":
    unittest.main()
