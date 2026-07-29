import unittest

from job_schema import CANONICAL_JOB_FIELDS, apply_job_schema, assess_field_quality


class JobSchemaTest(unittest.TestCase):
    def test_apply_job_schema_adds_defaults_and_quality(self):
        job = {
            "platform": "boss",
            "title": "AI Agent 工程师",
            "company": "测试公司",
            "salary": "15-25K",
            "requirements": "熟悉 Python、RAG、Agent 工程化",
        }

        result = apply_job_schema(job)

        for field in CANONICAL_JOB_FIELDS:
            self.assertIn(field, result)
        self.assertEqual(result["job_schema_version"], "job_schema_v1")
        self.assertIn("field_quality_score", result)
        self.assertIn("location", result["field_quality_missing"])

    def test_assess_field_quality_ignores_unknown_values(self):
        job = {
            "platform": "zhilian",
            "job_id": "job-1",
            "title": "RAG 工程师",
            "company": "测试公司",
            "location": "上海",
            "salary": "未知",
            "experience": "列表页未提供",
            "degree": "本科",
            "description": "负责 RAG 检索链路",
            "skills": "Python,RAG",
            "welfare": "双休",
        }

        quality = assess_field_quality(job)

        self.assertIn("salary", quality["missing"])
        self.assertIn("experience", quality["missing"])
        self.assertIn("degree", quality["filled"])
        self.assertGreaterEqual(quality["score"], 70)


if __name__ == "__main__":
    unittest.main()
