import unittest

from job_quality import apply_quality_control, filter_invalid_jobs, summarize_job_quality


class JobQualityTest(unittest.TestCase):
    def test_apply_quality_control_marks_confidence(self):
        job = {
            "platform": "boss",
            "title": "RAG 工程师",
            "company": "示例科技",
            "location": "上海",
            "salary": "12-18K",
            "requirements": "熟悉 Python、RAG、FastAPI。",
            "source_url": "https://example.com/job/1",
        }

        result = apply_quality_control(job)

        self.assertFalse(result["job_quality_invalid"])
        self.assertIn("title", result["field_confidence"])
        self.assertIn(result["job_quality_label"], {"中", "高"})

    def test_filter_invalid_jobs_returns_reason_summary(self):
        jobs = [
            {"platform": "boss", "title": "登录后查看", "company": "示例科技"},
            {"platform": "zhilian", "title": "AI 应用开发", "company": "示例科技", "salary": "12-18K"},
        ]

        valid, summary = filter_invalid_jobs(jobs)

        self.assertEqual(len(valid), 1)
        self.assertEqual(summary["total"], 1)
        self.assertEqual(summary["reason_counts"]["岗位名称像页面提示"], 1)

    def test_summarize_job_quality_aggregates_labels(self):
        jobs = [
            {
                "title": "AI 应用开发",
                "company": "示例科技",
                "location": "上海",
                "salary": "12-18K",
                "requirements": "Python RAG",
                "source_url": "https://example.com/1",
            },
            {"title": "AI 应用开发", "company": "示例科技", "salary": "12-18K"},
        ]

        summary = summarize_job_quality(jobs)

        self.assertEqual(summary["total"], 2)
        self.assertGreater(summary["avg_confidence"], 0)
        self.assertIn("avg_field_confidence", summary)


if __name__ == "__main__":
    unittest.main()
