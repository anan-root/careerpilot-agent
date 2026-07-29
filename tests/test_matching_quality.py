import unittest

from agents.ranking_agent import decide_job
from agents.resume_matcher import rank_jobs_for_resume


class MatchingQualityTest(unittest.TestCase):
    def test_resume_match_caps_sparse_job_score(self):
        resume = "Python RAG FastAPI 项目经验，负责 Agent 应用开发。"
        sparse_job = {
            "platform": "manual",
            "job_id": "manual_sparse",
            "title": "Python RAG FastAPI Agent 工程师",
            "company": "测试公司",
            "field_quality_score": 30,
        }

        ranked = rank_jobs_for_resume(resume, [sparse_job], top_n=None)

        self.assertLessEqual(ranked[0]["resume_match"]["score"], 68)
        self.assertEqual(ranked[0]["resume_match"]["field_quality_score"], 30)

    def test_decision_adds_quality_message_for_sparse_job(self):
        job = {
            "platform": "manual",
            "job_id": "manual_sparse",
            "title": "AI 应用开发工程师",
            "company": "测试公司",
            "field_quality_score": 30,
        }

        decision = decide_job(job, {"skills": ["Python", "RAG"], "projects": []})

        self.assertIn("岗位信息不足，推荐结论需要人工确认", decision["risks"])


if __name__ == "__main__":
    unittest.main()
