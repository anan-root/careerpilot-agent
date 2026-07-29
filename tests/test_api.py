import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

import db
import memory.store as memory_store
from api import app


class ApiTest(unittest.TestCase):
    def test_import_job_and_list_jobs_use_temp_database(self):
        old_db_path = db.DB_PATH
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                db.DB_PATH = Path(temp_dir) / "jobs.db"
                db.init_db()
                client = TestClient(app)

                response = client.post(
                    "/jobs/import",
                    json={
                        "title": "AI 应用开发工程师",
                        "company": "示例科技",
                        "location": "上海",
                        "salary": "12-18K",
                        "jd_text": "任职要求：熟悉 Python、RAG、FastAPI。",
                    },
                )
                listed = client.get("/jobs")

                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(response.json()["job"]["platform"], "manual")
                self.assertEqual(listed.status_code, 200, listed.text)
                self.assertEqual(listed.json()["total"], 1)
                self.assertEqual(listed.json()["items"][0]["title"], "AI 应用开发工程师")
        finally:
            db.DB_PATH = old_db_path

    def test_capabilities_lists_public_endpoints(self):
        client = TestClient(app)

        response = client.get("/meta/capabilities")

        self.assertEqual(response.status_code, 200, response.text)
        endpoints = response.json()["endpoints"]
        self.assertEqual(endpoints["search_jobs"], "POST /jobs/search")
        self.assertEqual(endpoints["match_jobs"], "POST /jobs/match")
        self.assertEqual(endpoints["bookmark_job"], "POST /jobs/bookmark")

    def test_platform_metadata_lists_default_platforms(self):
        client = TestClient(app)

        response = client.get("/meta/platforms")

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["default"], ["boss", "zhilian", "51job"])
        codes = [item["code"] for item in payload["items"]]
        self.assertIn("liepin", codes)
        self.assertIn("lagou", codes)

    @patch("api.get_last_search_summary", return_value={"search_final_total": 1})
    @patch("api.collect_all_jobs")
    def test_search_jobs_calls_platform_aggregator(self, collect_all_jobs, get_last_search_summary):
        collect_all_jobs.return_value = [
            {
                "platform": "boss",
                "job_id": "job-1",
                "title": "AI 应用开发",
                "company": "示例科技",
            }
        ]
        client = TestClient(app)

        response = client.post(
            "/jobs/search",
            json={
                "keyword": "RAG",
                "location": "上海",
                "platforms": ["BOSS直聘", "智联招聘"],
                "max_pages": 1,
                "job_types": ["社招"],
                "enrich_details": False,
            },
        )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["total"], 1)
        self.assertEqual(payload["summary"]["search_final_total"], 1)
        kwargs = collect_all_jobs.call_args.kwargs
        self.assertEqual(kwargs["keyword"], "RAG")
        self.assertEqual(kwargs["location"], "上海")
        self.assertEqual(kwargs["platforms"], ["boss", "zhilian"])
        self.assertEqual(kwargs["max_pages"], 1)
        self.assertFalse(kwargs["enrich_details"])
        get_last_search_summary.assert_called_once()

    def test_import_job_rejects_empty_payload(self):
        client = TestClient(app)

        response = client.post("/jobs/import", json={})

        self.assertEqual(response.status_code, 400)

    def test_match_jobs_returns_ranked_jobs(self):
        old_db_path = db.DB_PATH
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                db.DB_PATH = Path(temp_dir) / "jobs.db"
                db.init_db()
                client = TestClient(app)
                client.post(
                    "/jobs/import",
                    json={
                        "title": "RAG 应用开发工程师",
                        "company": "示例科技",
                        "location": "上海",
                        "salary": "12-18K",
                        "jd_text": "任职要求：熟悉 Python、RAG、FastAPI，负责 Agent 应用。",
                    },
                )

                response = client.post(
                    "/jobs/match",
                    json={
                        "resume_text": "我做过 Python、RAG、FastAPI 和 Agent 项目。",
                        "top_n": 5,
                        "ai_top_n": 0,
                    },
                )

                self.assertEqual(response.status_code, 200, response.text)
                payload = response.json()
                self.assertEqual(payload["total"], 1)
                self.assertEqual(payload["items"][0]["title"], "RAG 应用开发工程师")
                self.assertIn("resume_match", payload["items"][0])
                self.assertIn("summary", payload)
                self.assertEqual(payload["summary"]["platform_counts"]["manual"], 1)
                self.assertGreaterEqual(payload["summary"]["avg_score"], 0)
        finally:
            db.DB_PATH = old_db_path

    def test_job_actions_use_temp_memory(self):
        old_memory_dir = memory_store.MEMORY_DIR
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                memory_store.MEMORY_DIR = Path(temp_dir) / "memory"
                client = TestClient(app)

                bookmark = client.post(
                    "/jobs/bookmark",
                    json={
                        "platform": "manual",
                        "job_id": "job-1",
                        "company": "示例科技",
                        "title": "AI 应用开发",
                    },
                )
                feedback = client.post(
                    "/jobs/feedback",
                    json={
                        "platform": "manual",
                        "job_id": "job-1",
                        "company": "示例科技",
                        "title": "AI 应用开发",
                        "status": "感兴趣",
                        "note": "优先看",
                    },
                )
                application = client.post(
                    "/jobs/application",
                    json={
                        "platform": "manual",
                        "job_id": "job-1",
                        "company": "示例科技",
                        "title": "AI 应用开发",
                        "status": "已投递",
                        "next_action": "等待回复",
                    },
                )
                listed = client.get("/jobs/actions")

                self.assertEqual(bookmark.status_code, 200, bookmark.text)
                self.assertEqual(feedback.status_code, 200, feedback.text)
                self.assertEqual(application.status_code, 200, application.text)
                payload = listed.json()
                self.assertEqual(payload["summary"]["feedback_total"], 2)
                self.assertEqual(payload["summary"]["application_total"], 1)
                self.assertEqual(payload["summary"]["application_status_counts"]["已投递"], 1)
        finally:
            memory_store.MEMORY_DIR = old_memory_dir

    def test_match_jobs_applies_negative_feedback(self):
        old_db_path = db.DB_PATH
        old_memory_dir = memory_store.MEMORY_DIR
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir)
                db.DB_PATH = temp_path / "jobs.db"
                memory_store.MEMORY_DIR = temp_path / "memory"
                db.init_db()
                client = TestClient(app)
                client.post(
                    "/jobs/import",
                    json={
                        "title": "RAG 应用开发工程师",
                        "company": "示例科技",
                        "location": "上海",
                        "salary": "12-18K",
                        "jd_text": "任职要求：熟悉 Python、RAG、FastAPI，负责 Agent 应用。",
                    },
                )
                client.post(
                    "/jobs/feedback",
                    json={
                        "company": "示例科技",
                        "title": "RAG 应用开发工程师",
                        "status": "不合适",
                    },
                )

                response = client.post(
                    "/jobs/match",
                    json={
                        "resume_text": "Python RAG FastAPI Agent 项目经验。",
                        "top_n": 5,
                        "ai_top_n": 0,
                    },
                )

                self.assertEqual(response.status_code, 200, response.text)
                job = response.json()["items"][0]
                self.assertTrue(job["action_negative"])
                self.assertLessEqual(job["resume_match"]["score"], 55)
                self.assertGreater(response.json()["summary"]["action_summary"]["negative"], 0)
        finally:
            db.DB_PATH = old_db_path
            memory_store.MEMORY_DIR = old_memory_dir


if __name__ == "__main__":
    unittest.main()
