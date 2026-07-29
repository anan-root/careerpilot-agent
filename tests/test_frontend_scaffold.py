import json
import unittest
from pathlib import Path


class FrontendScaffoldTest(unittest.TestCase):
    def test_frontend_package_has_vite_scripts(self):
        package = json.loads(Path("frontend/package.json").read_text(encoding="utf-8"))

        self.assertEqual(package["scripts"]["dev"], "vite --host 127.0.0.1 --port 5173")
        self.assertEqual(package["scripts"]["build"], "vite build")
        self.assertTrue(Path("frontend/vite.config.js").exists())
        self.assertIn("vue", package["dependencies"])

    def test_frontend_calls_core_api_endpoints(self):
        text = Path("frontend/src/App.vue").read_text(encoding="utf-8")

        for endpoint in ("/meta/platforms", "/jobs/search", "/jobs/import", "/jobs/match"):
            with self.subTest(endpoint=endpoint):
                self.assertIn(endpoint, text)


if __name__ == "__main__":
    unittest.main()
