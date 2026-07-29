import unittest

from job_actions import annotate_jobs_with_actions, build_action_context, summarize_action_context


class JobActionsTest(unittest.TestCase):
    def test_annotate_jobs_with_actions_marks_bookmark_and_application(self):
        jobs = [{"platform": "manual", "job_id": "1", "company": "示例科技", "title": "AI 应用", "resume_match": {"score": 70}}]
        feedback = [{"platform": "manual", "job_id": "1", "company": "示例科技", "title": "AI 应用", "status": "收藏"}]
        applications = [{"platform": "manual", "job_id": "1", "company": "示例科技", "title": "AI 应用", "status": "已投递"}]

        annotated = annotate_jobs_with_actions(jobs, feedback=feedback, applications=applications, adjust_scores=True)

        self.assertTrue(annotated[0]["action_bookmarked"])
        self.assertIn("收藏", annotated[0]["action_status_tags"])
        self.assertIn("已投递", annotated[0]["action_status_tags"])
        self.assertGreater(annotated[0]["resume_match"]["score"], 70)

    def test_negative_feedback_caps_score_by_company(self):
        jobs = [{"platform": "boss", "company": "示例科技", "title": "RAG", "resume_match": {"score": 88}}]
        feedback = [{"company": "示例科技", "status": "不合适"}]

        annotated = annotate_jobs_with_actions(jobs, feedback=feedback, applications=[], adjust_scores=True)

        self.assertTrue(annotated[0]["action_negative"])
        self.assertLessEqual(annotated[0]["resume_match"]["score"], 55)

    def test_summarize_action_context_counts_tags(self):
        context = build_action_context(
            feedback=[{"company": "A", "title": "T", "status": "收藏"}],
            applications=[],
        )
        jobs = annotate_jobs_with_actions([{"company": "A", "title": "T"}], context=context)

        summary = summarize_action_context(jobs)

        self.assertEqual(summary["bookmarked"], 1)


if __name__ == "__main__":
    unittest.main()
