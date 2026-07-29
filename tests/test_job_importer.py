import unittest
from unittest.mock import patch

from job_importer import (
    build_job_from_url,
    build_manual_job,
    detect_platform_from_url,
    extract_text_from_html,
    parse_manual_job_text,
)


class JobImporterTest(unittest.TestCase):
    def test_parse_manual_job_text_builds_canonical_job(self):
        text = """
职位名称：AI 应用开发工程师
公司名称：示例科技
工作地点：上海
薪资：12-18K
任职要求：
熟悉 Python、RAG、FastAPI，接受应届生，本科及以上。
福利待遇：双休，五险一金
"""

        job = parse_manual_job_text(text, source_url="https://example.com/jobs/1")

        self.assertEqual(job["platform"], "manual")
        self.assertEqual(job["title"], "AI 应用开发工程师")
        self.assertEqual(job["company"], "示例科技")
        self.assertEqual(job["location"], "上海")
        self.assertEqual(job["salary"], "12-18K")
        self.assertEqual(job["source_url"], "https://example.com/jobs/1")
        self.assertEqual(job["crawl_status"], "manual_import")
        self.assertEqual(job["job_schema_version"], "job_schema_v1")
        self.assertIn("RAG", job["skills"])
        self.assertGreaterEqual(job["field_quality_score"], 70)

    def test_build_manual_job_prefers_structured_fields(self):
        job = build_manual_job(
            title="RAG 后端开发",
            company="目标公司",
            location="杭州",
            salary="15-25K",
            jd_text="职位名称：其他岗位\n任职要求：熟悉 Python、向量检索。",
            url="https://example.com/job/rag",
        )

        self.assertEqual(job["title"], "RAG 后端开发")
        self.assertEqual(job["company"], "目标公司")
        self.assertEqual(job["location"], "杭州")
        self.assertEqual(job["salary"], "15-25K")
        self.assertEqual(job["url"], "https://example.com/job/rag")
        self.assertTrue(job["job_id"].startswith("manual_"))
        self.assertIn("向量检索", job["full_jd"])

    def test_detect_platform_from_common_urls(self):
        cases = {
            "https://www.zhipin.com/job_detail/abc.html": "boss",
            "https://jobs.zhaopin.com/CC123.htm": "zhilian",
            "https://jobs.51job.com/shanghai/123.html": "51job",
            "https://www.liepin.com/job/123.shtml": "liepin",
        }

        for url, platform in cases.items():
            with self.subTest(url=url):
                self.assertEqual(detect_platform_from_url(url), platform)

    def test_extract_text_from_html_reads_meta_and_visible_body(self):
        html = """
<html>
  <head>
    <title>AI 应用开发工程师</title>
    <meta name="description" content="示例科技招聘 Python RAG 工程师">
    <script>hidden()</script>
  </head>
  <body>
    <h1>AI 应用开发工程师</h1>
    <main>工作地点：上海\n薪资：12-18K\n任职要求：熟悉 Python、RAG。</main>
  </body>
</html>
"""

        text = extract_text_from_html(html)

        self.assertIn("AI 应用开发工程师", text)
        self.assertIn("示例科技招聘 Python RAG 工程师", text)
        self.assertIn("工作地点：上海", text)
        self.assertNotIn("hidden", text)

    def test_build_job_from_url_uses_fetched_html_text(self):
        class Response:
            text = """
<html><body>
<h1>AI 应用开发工程师</h1>
<p>公司名称：示例科技</p>
<p>工作地点：上海</p>
<p>薪资：12-18K</p>
<p>任职要求：熟悉 Python、RAG、FastAPI。</p>
</body></html>
"""

            def raise_for_status(self):
                return None

        with patch("job_importer.requests.get", return_value=Response()):
            job = build_job_from_url("https://www.zhipin.com/job_detail/2.html")

        self.assertEqual(job["platform"], "boss")
        self.assertEqual(job["title"], "AI 应用开发工程师")
        self.assertEqual(job["company"], "示例科技")
        self.assertEqual(job["location"], "上海")
        self.assertEqual(job["salary"], "12-18K")
        self.assertEqual(job["detail_status"], "url_fetched")
        self.assertIn("FastAPI", job["skills"])

    def test_imported_text_infers_platform_company_and_title(self):
        job = build_manual_job(
            url="https://jobs.zhaopin.com/CC123.htm",
            jd_text="""
AI 应用开发工程师_示例科技招聘信息-智联招聘
12K-18K
上海
任职要求：熟悉 Python、RAG。
""",
        )

        self.assertEqual(job["platform"], "zhilian")
        self.assertEqual(job["title"], "AI 应用开发工程师")
        self.assertEqual(job["company"], "示例科技")
        self.assertEqual(job["location"], "上海")
        self.assertEqual(job["salary"], "12K-18K")

    def test_user_structured_fields_override_platform_inference(self):
        job = build_manual_job(
            title="用户填写岗位",
            company="用户填写公司",
            url="https://www.liepin.com/job/123.shtml",
            jd_text="AI 应用开发工程师\n示例科技\n上海\n12-18K",
        )

        self.assertEqual(job["platform"], "liepin")
        self.assertEqual(job["title"], "用户填写岗位")
        self.assertEqual(job["company"], "用户填写公司")


if __name__ == "__main__":
    unittest.main()
