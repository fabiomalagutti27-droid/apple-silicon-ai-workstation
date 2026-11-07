#!/usr/bin/env python3
"""
Unit tests for core components of Apple Silicon AI Workstation.
Validates log pruner, template formats, and configuration integrity.
"""
import os
import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

# Add project root to sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from core.log_pruner import prune_compiler_log


class TestLogPruner(unittest.TestCase):
    def test_rust_error_pruning(self):
        raw_log = """
warning: unused variable: `temp`
  --> src/main.rs:14:9
   |
14 |     let temp = 42;
   |         ^^^^ help: if this is intentional, prefix it with an underscore: `_temp`

error[E0425]: cannot find value `dx` in this scope
  --> src/spatial.rs:88:17
   |
88 |     let step = dx * 2.0;
   |                ^^ not found in this scope

error: aborting due to 1 previous error; 1 warning emitted
        """
        pruned = prune_compiler_log(raw_log, max_lines=50)
        self.assertIn("error[E0425]", pruned)
        self.assertIn("src/spatial.rs:88:17", pruned)
        self.assertIn("dx", pruned)
        self.assertNotIn("warning: unused variable", pruned)

    def test_empty_log_handling(self):
        self.assertEqual(prune_compiler_log(""), "")
        self.assertEqual(prune_compiler_log("   \n\n  "), "")


class TestTemplateIntegrity(unittest.TestCase):
    def test_launchd_plist_templates_valid_xml(self):
        template_dir = REPO_ROOT / "configs" / "launchd"
        templates = list(template_dir.glob("*.plist.template"))
        self.assertGreater(len(templates), 0, "No launchd templates found!")
        for tmpl in templates:
            with open(tmpl, "r") as f:
                content = f.read()
            # Replace placeholder with dummy path to validate XML parsing
            dummy_xml = content.replace("__USER_HOME__", "/tmp/dummy")
            try:
                ET.fromstring(dummy_xml)
            except ET.ParseError as e:
                self.fail(f"XML parse error in {tmpl.name}: {e}")

    def test_llama_swap_template_syntax(self):
        cfg_path = REPO_ROOT / "configs" / "llama-swap.yaml.template"
        self.assertTrue(cfg_path.exists())
        with open(cfg_path, "r") as f:
            lines = f.readlines()
        self.assertTrue(any("listen:" in l for l in lines))
        self.assertTrue(any("groups:" in l for l in lines))


if __name__ == "__main__":
    unittest.main()
