import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


muse = load_module("muse_console_for_hook_tests", ROOT / "muse-console.py")
hook = load_module("muse_hermes_hook_tests", ROOT / "muse-hermes-hook.py")


def write_skill(root: Path, name: str, body: str) -> Path:
    directory = root / "test" / name
    directory.mkdir(parents=True)
    (directory / "SKILL.md").write_text(
        "---\n"
        f"name: {name}\n"
        f"description: Use {name} for a test workflow\n"
        "metadata:\n"
        "  hermes:\n"
        "    category: test\n"
        "    tags: [test]\n"
        "---\n\n"
        f"# {name}\n\n{body}\n",
        encoding="utf-8",
    )
    return directory


class MuseHermesHookTests(unittest.TestCase):
    def test_route_catalog_reuses_cache_and_refreshes_new_skill(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "skills"
            state = Path(temp) / "state"
            write_skill(root, "first-skill", "Read the input and verify the result.")

            records, errors, refreshed = muse.route_catalog(state, [root])
            self.assertEqual(errors, [])
            self.assertTrue(refreshed)
            self.assertEqual([item.name for item in records], ["first-skill"])

            records, errors, refreshed = muse.route_catalog(state, [root])
            self.assertEqual(errors, [])
            self.assertFalse(refreshed)
            self.assertEqual([item.name for item in records], ["first-skill"])

            write_skill(root, "second-skill", "Use this for a second workflow.")
            records, errors, refreshed = muse.route_catalog(state, [root])
            self.assertEqual(errors, [])
            self.assertTrue(refreshed)
            self.assertEqual({item.name for item in records}, {"first-skill", "second-skill"})

    def test_hook_context_contains_route_and_inspect_without_scripts(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "skills"
            state = Path(temp) / "state"
            directory = write_skill(root, "jellyfin-repair", "Use systemctl to restart Jellyfin.")
            (directory / "repair.py").write_text("print('repair')\n", encoding="utf-8")

            with patch.object(muse, "default_roots", return_value=[root]), patch.object(muse, "default_state_dir", return_value=state):
                context = hook.route_context("帮我修 jellyfin", muse)

            self.assertIn("[MUSE AUTO-ROUTE]", context)
            self.assertIn("route matches:", context)
            self.assertIn("inspect: jellyfin-repair", context)
            self.assertIn("systemctl", context)
            self.assertIn("Script contents omitted", context)
            self.assertNotIn("print('repair')", context)

    def test_hook_emits_one_json_object_for_command_payload(self):
        with patch.object(hook.sys, "stdin", type("Input", (), {"read": lambda self: json.dumps({"user_message": "/new"})})()):
            output = []
            with patch.object(hook, "print", side_effect=lambda value: output.append(value), create=True):
                self.assertEqual(hook.main(), 0)
            self.assertEqual(len(output), 1)
            self.assertIn("context", json.loads(output[0]))


if __name__ == "__main__":
    unittest.main()
