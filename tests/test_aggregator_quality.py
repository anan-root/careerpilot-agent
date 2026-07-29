import unittest

from crawlers.aggregator import _deduplicate_with_report


class AggregatorQualityTest(unittest.TestCase):
    def test_deduplicate_with_report_counts_reasons(self):
        jobs = [
            {"platform": "boss", "job_id": "1", "company": "A", "title": "RAG", "location": "上海"},
            {"platform": "boss", "job_id": "1", "company": "A", "title": "RAG", "location": "上海"},
            {"platform": "boss", "company": "B", "title": "AI", "location": "上海", "salary": "12-18K"},
            {"platform": "boss", "company": "B", "title": "AI", "location": "上海", "salary": "12-18K"},
        ]

        unique, report = _deduplicate_with_report(jobs)

        self.assertEqual(len(unique), 2)
        self.assertEqual(report["dropped"], 2)
        self.assertEqual(report["reason_counts"]["same_platform_job_id"], 1)
        self.assertEqual(report["reason_counts"]["same_platform_fingerprint"], 1)


if __name__ == "__main__":
    unittest.main()
