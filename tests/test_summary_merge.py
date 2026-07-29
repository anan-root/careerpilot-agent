import unittest

from search_summary import merge_duplicate_summaries, merge_invalid_job_summaries, merge_job_quality_summaries


class SummaryMergeTest(unittest.TestCase):
    def test_merge_invalid_job_summaries(self):
        merged = merge_invalid_job_summaries([
            {"search_invalid_jobs": {"total": 1, "reason_counts": {"缺少岗位名称": 1}, "platform_counts": {"boss": 1}}},
            {"search_invalid_jobs": {"total": 2, "reason_counts": {"岗位信息过少": 2}, "platform_counts": {"zhilian": 2}}},
        ])

        self.assertEqual(merged["total"], 3)
        self.assertEqual(merged["reason_counts"]["岗位信息过少"], 2)
        self.assertEqual(merged["platform_counts"]["boss"], 1)

    def test_merge_duplicate_summaries(self):
        merged = merge_duplicate_summaries([
            {"search_duplicate_summary": {"input": 4, "kept": 3, "dropped": 1, "reason_counts": {"same_platform_job_id": 1}}},
            {"search_duplicate_summary": {"input": 5, "kept": 4, "dropped": 1, "reason_counts": {"same_platform_fingerprint": 1}}},
        ])

        self.assertEqual(merged["input"], 9)
        self.assertEqual(merged["kept"], 7)
        self.assertEqual(merged["dropped"], 2)

    def test_merge_job_quality_summaries_uses_weighted_average(self):
        merged = merge_job_quality_summaries([
            {"search_job_quality": {"total": 2, "avg_confidence": 80, "label_counts": {"高": 2}, "avg_field_confidence": {"title": 90}}},
            {"search_job_quality": {"total": 1, "avg_confidence": 50, "label_counts": {"低": 1}, "avg_field_confidence": {"title": 60}}},
        ])

        self.assertEqual(merged["total"], 3)
        self.assertEqual(merged["avg_confidence"], 70.0)
        self.assertEqual(merged["avg_field_confidence"]["title"], 80.0)


if __name__ == "__main__":
    unittest.main()
