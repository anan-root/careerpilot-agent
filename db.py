"""SQLite storage for jobs, companies, and application tracking."""

from __future__ import annotations

import sqlite3
import json
from pathlib import Path
from datetime import datetime

DB_PATH = Path(__file__).parent / "data" / "jobs.db"

_MIGRATE_COLUMNS = [
    ("skills", "TEXT"),
    ("degree", "TEXT"),
    ("experience", "TEXT"),
    ("company_size", "TEXT"),
    ("company_industry", "TEXT"),
    ("company_stage", "TEXT"),
    ("welfare", "TEXT"),
    ("hr_name", "TEXT"),
    ("hr_title", "TEXT"),
    ("chat_url", "TEXT"),
    ("full_jd", "TEXT"),
    ("deadline", "TEXT"),
    ("source_url", "TEXT"),
    ("company_address", "TEXT"),
    ("crawl_status", "TEXT"),
    ("crawl_keyword", "TEXT"),
    ("detail_status", "TEXT"),
    ("detail_source_url", "TEXT"),
]


def get_conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            platform TEXT NOT NULL,
            job_id TEXT,
            title TEXT NOT NULL,
            company TEXT NOT NULL,
            location TEXT,
            salary TEXT,
            job_type TEXT,
            description TEXT,
            requirements TEXT,
            url TEXT,
            posted_date TEXT,
            scraped_at TEXT DEFAULT (datetime('now')),
            score REAL,
            score_details TEXT,
            status TEXT DEFAULT 'new',
            skills TEXT,
            degree TEXT,
            experience TEXT,
            company_size TEXT,
            company_industry TEXT,
            company_stage TEXT,
            welfare TEXT,
            hr_name TEXT,
            hr_title TEXT,
            chat_url TEXT,
            full_jd TEXT,
            deadline TEXT,
            source_url TEXT,
            company_address TEXT,
            crawl_status TEXT,
            crawl_keyword TEXT,
            detail_status TEXT,
            detail_source_url TEXT,
            UNIQUE(platform, job_id)
        );

        CREATE TABLE IF NOT EXISTS companies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            industry TEXT,
            size TEXT,
            location TEXT,
            description TEXT,
            rating REAL,
            pros TEXT,
            cons TEXT,
            avg_salary TEXT,
            work_life_balance TEXT,
            updated_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS applications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER REFERENCES jobs(id),
            resume_path TEXT,
            interview_pack_path TEXT,
            applied_at TEXT,
            status TEXT DEFAULT 'pending',
            notes TEXT,
            updated_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS interview_materials (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER REFERENCES jobs(id),
            skill_tree TEXT,
            study_path TEXT,
            eight_part_essay TEXT,
            mock_questions TEXT,
            real_interview_exp TEXT,
            generated_at TEXT DEFAULT (datetime('now'))
        );
    """)
    conn.commit()
    _migrate_add_columns(conn)
    conn.close()


def _migrate_add_columns(conn: sqlite3.Connection):
    """Add new columns to existing jobs table without losing data."""
    cursor = conn.execute("PRAGMA table_info(jobs)")
    existing = {row[1] for row in cursor.fetchall()}
    for col_name, col_type in _MIGRATE_COLUMNS:
        if col_name not in existing:
            conn.execute(f"ALTER TABLE jobs ADD COLUMN {col_name} {col_type}")
    conn.commit()


def insert_job(
    platform: str, title: str, company: str, *,
    job_id: str = "", location: str = "", salary: str = "",
    job_type: str = "", description: str = "", requirements: str = "",
    url: str = "", posted_date: str = "",
    skills: str = "", degree: str = "", experience: str = "",
    company_size: str = "", company_industry: str = "",
    company_stage: str = "", welfare: str = "",
    hr_name: str = "", hr_title: str = "", chat_url: str = "",
    full_jd: str = "", deadline: str = "", source_url: str = "",
    company_address: str = "", crawl_status: str = "",
    crawl_keyword: str = "", detail_status: str = "",
    detail_source_url: str = "",
) -> int | None:
    resolved_job_id = job_id or f"{company}_{title}"
    conn = get_conn()
    try:
        cur = conn.execute(
            """INSERT OR IGNORE INTO jobs
               (platform, job_id, title, company, location, salary, job_type,
                description, requirements, url, posted_date,
                skills, degree, experience, company_size, company_industry,
                company_stage, welfare, hr_name, hr_title, chat_url,
                full_jd, deadline, source_url, company_address,
                crawl_status, crawl_keyword, detail_status, detail_source_url)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                       ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                       ?, ?, ?, ?, ?)""",
            (platform, resolved_job_id, title, company, location,
             salary, job_type, description, requirements, url, posted_date,
             skills, degree, experience, company_size, company_industry,
             company_stage, welfare, hr_name, hr_title, chat_url,
             full_jd, deadline, source_url, company_address,
             crawl_status, crawl_keyword, detail_status, detail_source_url),
        )
        conn.commit()
        if cur.lastrowid:
            return cur.lastrowid
        row = conn.execute(
            "SELECT id FROM jobs WHERE platform=? AND job_id=?",
            (platform, resolved_job_id),
        ).fetchone()
        if not row:
            return None
        row_id = int(row["id"])
        _update_existing_job_fields(
            conn,
            row_id,
            {
                "location": location,
                "salary": salary,
                "job_type": job_type,
                "description": description,
                "requirements": requirements,
                "url": url,
                "posted_date": posted_date,
                "skills": skills,
                "degree": degree,
                "experience": experience,
                "company_size": company_size,
                "company_industry": company_industry,
                "company_stage": company_stage,
                "welfare": welfare,
                "hr_name": hr_name,
                "hr_title": hr_title,
                "chat_url": chat_url,
                "full_jd": full_jd,
                "deadline": deadline,
                "source_url": source_url,
                "company_address": company_address,
                "crawl_status": crawl_status,
                "crawl_keyword": crawl_keyword,
                "detail_status": detail_status,
                "detail_source_url": detail_source_url,
            },
        )
        return row_id
    finally:
        conn.close()


def _update_existing_job_fields(conn: sqlite3.Connection, row_id: int, fields: dict[str, str]):
    row = conn.execute("SELECT * FROM jobs WHERE id=?", (row_id,)).fetchone()
    if not row:
        return

    updates = {
        key: value
        for key, value in fields.items()
        if _should_update_field(key, row[key] if key in row.keys() else "", value)
    }
    if not updates:
        return

    assignments = ", ".join(f"{key}=?" for key in updates)
    params = list(updates.values()) + [row_id]
    conn.execute(f"UPDATE jobs SET {assignments} WHERE id=?", params)
    conn.commit()


def _should_update_field(key: str, current: str | None, new_value: str | None) -> bool:
    new_text = str(new_value or "").strip()
    if not new_text:
        return False

    current_text = str(current or "").strip()
    if not current_text or current_text.startswith("列表页未提供"):
        return True

    longer_is_better = {
        "location",
        "description",
        "requirements",
        "skills",
        "welfare",
        "full_jd",
        "company_address",
        "source_url",
        "url",
    }
    if key in longer_is_better:
        return len(new_text) > len(current_text)

    if key == "detail_status":
        return _status_rank(new_text, _DETAIL_STATUS_RANK) > _status_rank(current_text, _DETAIL_STATUS_RANK)

    if key == "crawl_status":
        return _status_rank(new_text, _CRAWL_STATUS_RANK) > _status_rank(current_text, _CRAWL_STATUS_RANK)

    return False


_DETAIL_STATUS_RANK = {
    "fetched": 5,
    "not_requested": 3,
    "skipped_limit": 2,
    "skipped_disabled": 2,
    "skipped_detail_block_prone": 2,
    "blocked_or_empty": 1,
    "failed": 1,
}

_CRAWL_STATUS_RANK = {
    "browser_login_opt_in": 5,
    "browser_list": 4,
    "requests_or_api": 3,
    "requests_list": 3,
    "curated_fallback": 1,
}


def _status_rank(value: str, ranks: dict[str, int]) -> int:
    return ranks.get(str(value or "").strip(), 0)


def update_job_score(job_db_id: int, score: float, details: dict):
    conn = get_conn()
    conn.execute(
        "UPDATE jobs SET score=?, score_details=? WHERE id=?",
        (score, json.dumps(details, ensure_ascii=False), job_db_id),
    )
    conn.commit()
    conn.close()


def get_jobs(*, min_score: float | None = None, status: str | None = None,
             platform: str | None = None, limit: int = 100) -> list[dict]:
    conn = get_conn()
    sql = "SELECT * FROM jobs WHERE 1=1"
    params: list = []
    if min_score is not None:
        sql += " AND score >= ?"
        params.append(min_score)
    if status:
        sql += " AND status = ?"
        params.append(status)
    if platform:
        sql += " AND platform = ?"
        params.append(platform)
    sql += " ORDER BY score DESC NULLS LAST, scraped_at DESC LIMIT ?"
    params.append(limit)
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_job_by_id(job_db_id: int) -> dict | None:
    conn = get_conn()
    row = conn.execute("SELECT * FROM jobs WHERE id=?", (job_db_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_all_jobs_df():
    """Return all jobs as a pandas-friendly list of dicts."""
    conn = get_conn()
    rows = conn.execute("SELECT * FROM jobs ORDER BY score DESC NULLS LAST, scraped_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


init_db()
