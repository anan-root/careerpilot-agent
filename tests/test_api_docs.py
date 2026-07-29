import unittest
from pathlib import Path


PUBLIC_ENDPOINTS = (
    "/health",
    "/meta/capabilities",
    "/meta/platforms",
    "/jobs/search",
    "/jobs/import",
    "/jobs",
    "/jobs/match",
    "/jobs/bookmark",
    "/jobs/feedback",
    "/jobs/application",
    "/jobs/actions",
)


class ApiDocsTest(unittest.TestCase):
    def test_api_reference_mentions_public_endpoints(self):
        text = Path("docs/API_REFERENCE.md").read_text(encoding="utf-8")

        for endpoint in PUBLIC_ENDPOINTS:
            with self.subTest(endpoint=endpoint):
                self.assertIn(endpoint, text)

    def test_frontend_plan_mentions_core_pages(self):
        text = Path("docs/FRONTEND_PRODUCT_PLAN.md").read_text(encoding="utf-8")

        for title in ("岗位收件箱", "简历匹配看板", "岗位详情", "求职行动记录"):
            with self.subTest(title=title):
                self.assertIn(title, text)

    def test_readme_mentions_runnable_product_surfaces(self):
        text = Path("README.md").read_text(encoding="utf-8")

        for item in (
            "Streamlit 求职工作台",
            "FastAPI 本地接口",
            "Vite + Vue 独立 Web 前端",
            "Chrome / Edge 插件",
            "POST http://127.0.0.1:8000/jobs/search",
            "http://127.0.0.1:5173",
        ):
            with self.subTest(item=item):
                self.assertIn(item, text)


if __name__ == "__main__":
    unittest.main()
