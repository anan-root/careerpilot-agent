"""Minimal HTTP API for CareerPilot integrations."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

import db
from agents.resume_matcher import rank_jobs_for_resume
from crawlers.aggregator import collect_all_jobs, get_last_search_summary
from job_filters import filter_jobs_by_type
from job_actions import annotate_jobs_with_actions
from job_importer import build_job_from_url, build_manual_job, save_imported_job
from match_dashboard import build_match_dashboard
from memory.store import (
    load_application_records,
    load_job_feedback,
    save_application_record,
    save_job_feedback,
)
from platform_registry import DEFAULT_PLATFORM_CODES, PLATFORM_LABELS, PLATFORM_ORDER, normalize_platforms

app = FastAPI(title="CareerPilot API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:3000",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

CAPABILITIES = {
    "service": "career-pilot-api",
    "version": "0.1.0",
    "features": [
        "job_import",
        "url_import",
        "job_list",
        "resume_match",
        "match_dashboard",
        "platform_search",
        "platform_metadata",
        "bookmark",
        "feedback",
        "application_tracking",
        "browser_extension",
    ],
    "endpoints": {
        "health": "GET /health",
        "capabilities": "GET /meta/capabilities",
        "platforms": "GET /meta/platforms",
        "search_jobs": "POST /jobs/search",
        "import_job": "POST /jobs/import",
        "list_jobs": "GET /jobs",
        "match_jobs": "POST /jobs/match",
        "bookmark_job": "POST /jobs/bookmark",
        "feedback_job": "POST /jobs/feedback",
        "application_job": "POST /jobs/application",
        "list_job_actions": "GET /jobs/actions",
    },
}


class JobImportRequest(BaseModel):
    title: str = ""
    company: str = ""
    location: str = ""
    salary: str = ""
    url: str = ""
    jd_text: str = ""
    fetch_url: bool = False


class JobSearchRequest(BaseModel):
    keyword: str = "AI Agent"
    location: str = "上海"
    platforms: list[str] = Field(default_factory=list)
    max_pages: int = Field(default=2, ge=1, le=5)
    job_types: list[str] = Field(default_factory=lambda: ["社招", "校招"])
    criteria: dict = Field(default_factory=dict)
    expand_keywords: bool = True
    max_keywords: int = Field(default=4, ge=1, le=8)
    enrich_details: bool = True
    detail_limit: int = Field(default=20, ge=0, le=100)
    use_browser_crawlers: bool = False
    allow_browser_login: bool = False


class JobMatchRequest(BaseModel):
    resume_text: str
    top_n: int = Field(default=20, ge=1, le=100)
    ai_top_n: int = Field(default=0, ge=0, le=20)
    job_types: list[str] = Field(default_factory=lambda: ["社招", "校招"])


class JobActionRequest(BaseModel):
    job_db_id: int | None = None
    platform: str = ""
    job_id: str = ""
    company: str = ""
    title: str = ""
    status: str = ""
    note: str = ""
    next_action: str = ""


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "career-pilot-api"}


@app.get("/meta/capabilities")
def capabilities() -> dict:
    return CAPABILITIES


@app.get("/meta/platforms")
def platforms() -> dict:
    items = [
        {
            "code": code,
            "label": PLATFORM_LABELS.get(code, code),
            "default": code in DEFAULT_PLATFORM_CODES,
        }
        for code in PLATFORM_ORDER
    ]
    return {"default": list(DEFAULT_PLATFORM_CODES), "items": items}


@app.post("/jobs/search")
def search_jobs(payload: JobSearchRequest) -> dict:
    platforms = normalize_platforms(payload.platforms) if payload.platforms else None
    criteria = dict(payload.criteria or {})
    jobs = collect_all_jobs(
        keyword=payload.keyword.strip() or "AI Agent",
        location=payload.location.strip() or "上海",
        platforms=platforms,
        max_pages=payload.max_pages,
        job_types=payload.job_types,
        criteria=criteria,
        expand_keywords=payload.expand_keywords,
        max_keywords=payload.max_keywords,
        enrich_details=payload.enrich_details,
        detail_limit=payload.detail_limit,
        use_browser_crawlers=payload.use_browser_crawlers,
        allow_browser_login=payload.allow_browser_login,
    )
    return {
        "items": jobs,
        "total": len(jobs),
        "summary": get_last_search_summary(),
    }


@app.post("/jobs/import")
def import_job(payload: JobImportRequest) -> dict:
    values = (
        payload.title,
        payload.company,
        payload.location,
        payload.salary,
        payload.url,
        payload.jd_text,
    )
    if not any(str(value or "").strip() for value in values):
        raise HTTPException(status_code=400, detail="请提供岗位字段、JD 文本或岗位链接。")

    if payload.fetch_url and payload.url.strip():
        job = build_job_from_url(
            payload.url,
            title=payload.title,
            company=payload.company,
            location=payload.location,
            salary=payload.salary,
            jd_text=payload.jd_text,
        )
    else:
        job = build_manual_job(
            title=payload.title,
            company=payload.company,
            location=payload.location,
            salary=payload.salary,
            jd_text=payload.jd_text,
            url=payload.url,
        )
    saved = save_imported_job(job)
    return {"job": saved}


@app.get("/jobs")
def list_jobs(limit: int = Query(default=50, ge=1, le=500)) -> dict:
    jobs = db.get_jobs(limit=limit)
    return {"items": jobs, "total": len(jobs)}


@app.post("/jobs/match")
def match_jobs(payload: JobMatchRequest) -> dict:
    if not payload.resume_text.strip():
        raise HTTPException(status_code=400, detail="请提供简历文本。")

    jobs = db.get_all_jobs_df()
    jobs = filter_jobs_by_type(jobs, payload.job_types)
    ranked = rank_jobs_for_resume(
        payload.resume_text,
        jobs,
        top_n=payload.top_n,
        ai_top_n=payload.ai_top_n,
    )
    feedback = load_job_feedback(limit=500)
    applications = load_application_records(limit=500)
    ranked = annotate_jobs_with_actions(
        ranked,
        feedback=feedback,
        applications=applications,
        adjust_scores=True,
        resort=True,
    )
    return {
        "items": ranked,
        "total": len(ranked),
        "summary": build_match_dashboard(ranked),
    }


@app.post("/jobs/bookmark")
def bookmark_job(payload: JobActionRequest) -> dict:
    job = _job_from_action(payload)
    status = payload.status.strip() or "收藏"
    save_job_feedback(job, status, payload.note)
    return {"saved": True, "type": "bookmark", "job": _action_job_public(job), "status": status}


@app.post("/jobs/feedback")
def feedback_job(payload: JobActionRequest) -> dict:
    job = _job_from_action(payload)
    status = payload.status.strip()
    if not status:
        raise HTTPException(status_code=400, detail="请提供反馈状态。")
    save_job_feedback(job, status, payload.note)
    return {"saved": True, "type": "feedback", "job": _action_job_public(job), "status": status}


@app.post("/jobs/application")
def application_job(payload: JobActionRequest) -> dict:
    job = _job_from_action(payload)
    status = payload.status.strip() or "已投递"
    save_application_record(job, status, next_action=payload.next_action, note=payload.note)
    return {"saved": True, "type": "application", "job": _action_job_public(job), "status": status}


@app.get("/jobs/actions")
def list_job_actions(limit: int = Query(default=100, ge=1, le=500)) -> dict:
    feedback = load_job_feedback(limit=limit)
    applications = load_application_records(limit=limit)
    return {
        "feedback": feedback,
        "applications": applications,
        "summary": _action_summary(feedback, applications),
    }


def _job_from_action(payload: JobActionRequest) -> dict:
    if payload.job_db_id is not None:
        job = db.get_job_by_id(payload.job_db_id)
        if not job:
            raise HTTPException(status_code=404, detail="没有找到岗位。")
        return job

    job = {
        "platform": payload.platform,
        "job_id": payload.job_id,
        "company": payload.company,
        "title": payload.title,
    }
    if not any(str(job.get(field) or "").strip() for field in ("company", "title", "job_id")):
        raise HTTPException(status_code=400, detail="请提供岗位 ID 或岗位基础字段。")
    return job


def _action_job_public(job: dict) -> dict:
    return {
        "id": job.get("id") or job.get("db_id"),
        "platform": job.get("platform", ""),
        "job_id": job.get("job_id", ""),
        "company": job.get("company", ""),
        "title": job.get("title", ""),
    }


def _action_summary(feedback: list[dict], applications: list[dict]) -> dict:
    return {
        "feedback_total": len(feedback),
        "application_total": len(applications),
        "feedback_status_counts": _count_by_status(feedback),
        "application_status_counts": _count_by_status(applications),
    }


def _count_by_status(rows: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        status = str(row.get("status") or "未知")
        counts[status] = counts.get(status, 0) + 1
    return counts


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("api:app", host="127.0.0.1", port=8000, reload=False)
