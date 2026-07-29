import tempfile
import unittest
from pathlib import Path

from click.testing import CliRunner

import db
from cli import cli


class CliImportJobTest(unittest.TestCase):
    def test_import_job_from_file_uses_temp_database(self):
        old_db_path = db.DB_PATH
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir)
                db.DB_PATH = temp_path / "jobs.db"
                db.init_db()
                jd_file = temp_path / "jd.txt"
                jd_file.write_text(
                    "职位名称：AI 应用开发工程师\n公司名称：示例科技\n工作地点：上海\n薪资：12-18K\n任职要求：熟悉 Python、RAG。",
                    encoding="utf-8",
                )

                result = CliRunner().invoke(cli, ["import-job", "--jd-file", str(jd_file)])
                jobs = db.get_all_jobs_df()

                self.assertEqual(result.exit_code, 0, result.output)
                self.assertEqual(len(jobs), 1)
                self.assertEqual(jobs[0]["platform"], "manual")
                self.assertEqual(jobs[0]["title"], "AI 应用开发工程师")
        finally:
            db.DB_PATH = old_db_path


if __name__ == "__main__":
    unittest.main()
