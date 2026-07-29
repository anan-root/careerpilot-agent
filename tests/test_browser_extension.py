import json
import unittest
from pathlib import Path


class BrowserExtensionTest(unittest.TestCase):
    def test_manifest_has_required_mv3_fields(self):
        manifest = json.loads(Path("browser_extension/manifest.json").read_text(encoding="utf-8"))

        self.assertEqual(manifest["manifest_version"], 3)
        self.assertIn("activeTab", manifest["permissions"])
        self.assertIn("scripting", manifest["permissions"])
        self.assertEqual(manifest["action"]["default_popup"], "popup.html")
        self.assertIn("http://127.0.0.1:8000/*", manifest["host_permissions"])

    def test_popup_files_exist_and_call_local_api(self):
        html = Path("browser_extension/popup.html").read_text(encoding="utf-8")
        js = Path("browser_extension/popup.js").read_text(encoding="utf-8")

        self.assertIn("popup.js", html)
        self.assertIn("/jobs/import", js)
        self.assertIn("/jobs/bookmark", js)
        self.assertIn("chrome.scripting.executeScript", js)


if __name__ == "__main__":
    unittest.main()
