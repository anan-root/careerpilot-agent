import unittest

from match_dashboard import build_match_dashboard


class MatchDashboardTest(unittest.TestCase):
    def test_build_match_dashboard_summarizes_ranked_jobs(self):
        jobs = [
            {
                "platform": "boss",
                "company": "示例科技",
                "title": "RAG 工程师",
                "location": "上海",
                "salary": "12-18K",
                "field_quality_score": 90,
                "resume_match": {
                    "score": 82,
                    "matched_keywords": ["Python", "RAG"],
                    "missing_keywords": ["LangGraph"],
                },
                "action_status_tags": ["收藏"],
            },
            {
                "platform": "zhilian",
                "company": "样例智能",
                "title": "AI 应用开发",
                "field_quality_score": 70,
                "resume_match": {
                    "score": 58,
                    "matched_keywords": ["FastAPI"],
                    "missing_keywords": ["Docker"],
                },
            },
        ]

        dashboard = build_match_dashboard(jobs)

        self.assertEqual(dashboard["total"], 2)
        self.assertEqual(dashboard["evaluated_count"], 2)
        self.assertEqual(dashboard["high_match_count"], 1)
        self.assertEqual(dashboard["platform_counts"]["boss"], 1)
        self.assertEqual(dashboard["level_counts"]["优先看"], 1)
        self.assertIn("LangGraph", dashboard["top_missing_keywords"])
        self.assertEqual(dashboard["action_summary"]["bookmarked"], 1)
        self.assertEqual(dashboard["top_jobs"][0]["company"], "示例科技")


if __name__ == "__main__":
    unittest.main()
