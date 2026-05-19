"""Small JSON-backed memory store for local Agent state."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
MEMORY_DIR = DATA_DIR / "memory"
OUTPUT_RUN_DIR = DATA_DIR / "outputs" / "agent_runs"
AGENT_RUNS_DIR = MEMORY_DIR / "agent_runs"


def read_json(name: str, default: Any = None) -> Any:
    path = _path(name)
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def write_json(name: str, data: Any) -> Path:
    path = _path(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def append_jsonl(name: str, record: dict) -> Path:
    path = _path(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(record)
    payload.setdefault("created_at", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    return path


def save_profile(profile: dict) -> Path:
    payload = dict(profile or {})
    payload["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return write_json("profile.json", payload)


def load_profile() -> dict:
    return read_json("profile.json", {}) or {}


def save_search_history(goal_text: str, plan: dict, summary: dict) -> Path:
    return append_jsonl(
        "search_history.jsonl",
        {
            "goal_text": goal_text,
            "plan": plan,
            "summary": summary,
        },
    )


def create_agent_run(goal_text: str, resume_present: bool = False) -> dict:
    """Create a durable task record for one Agent search run."""
    now = _now()
    run_id = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:8]}"
    record = {
        "run_id": run_id,
        "goal_text": goal_text,
        "status": "running",
        "resume_present": bool(resume_present),
        "steps": [
            {
                "name": "创建 Agent 任务",
                "status": "done",
                "detail": "已接收用户目标",
                "time": now,
            }
        ],
        "created_at": now,
        "updated_at": now,
    }
    _write_agent_run(record)
    return record


def add_agent_run_step(run_id: str, name: str, status: str = "done", detail: str = "") -> dict:
    record = load_agent_run(run_id)
    if not record:
        return {}
    record.setdefault("steps", []).append({
        "name": name,
        "status": status,
        "detail": detail,
        "time": _now(),
    })
    record["updated_at"] = _now()
    _write_agent_run(record)
    return record


def save_agent_run_report(run_id: str, report: str) -> Path:
    OUTPUT_RUN_DIR.mkdir(parents=True, exist_ok=True)
    path = OUTPUT_RUN_DIR / f"{run_id}.md"
    path.write_text(report, encoding="utf-8")
    return path


def finish_agent_run(run_id: str, result: dict, report_path: str = "") -> dict:
    record = load_agent_run(run_id)
    if not record:
        return {}
    jobs = result.get("jobs") or []
    plan = result.get("plan") or {}
    summary = result.get("summary") or {}
    now = _now()
    record.update({
        "status": "completed",
        "completed_at": now,
        "updated_at": now,
        "plan": _public_plan(plan),
        "job_count": len(jobs),
        "decision_counts": _decision_counts(jobs),
        "platform_counts": summary.get("search_final_platform_counts") or {},
        "search_keywords": summary.get("search_keywords") or plan.get("expanded_keywords") or [],
        "raw_total": summary.get("search_raw_total", len(jobs)),
        "filtered_total": summary.get("search_filtered_total", len(jobs)),
        "final_total": summary.get("search_final_total", len(jobs)),
        "top_job": _top_job_summary(jobs),
        "top_jobs": _top_jobs_summary(jobs),
        "report_path": report_path,
    })
    record.setdefault("steps", []).append({
        "name": "完成 Agent 任务",
        "status": "done",
        "detail": f"最终展示 {len(jobs)} 个岗位",
        "time": now,
    })
    _write_agent_run(record)
    return record


def fail_agent_run(run_id: str, error: str) -> dict:
    record = load_agent_run(run_id)
    if not record:
        return {}
    now = _now()
    record.update({
        "status": "failed",
        "error": error,
        "updated_at": now,
        "completed_at": now,
    })
    record.setdefault("steps", []).append({
        "name": "Agent 任务失败",
        "status": "failed",
        "detail": error,
        "time": now,
    })
    _write_agent_run(record)
    return record


def load_agent_run(run_id: str) -> dict:
    path = AGENT_RUNS_DIR / f"{run_id}.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def load_agent_runs(limit: int = 20) -> list[dict]:
    if not AGENT_RUNS_DIR.exists():
        return []
    runs = []
    for path in AGENT_RUNS_DIR.glob("*.json"):
        try:
            runs.append(json.loads(path.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            continue
    runs.sort(key=lambda item: item.get("updated_at", ""), reverse=True)
    return runs[:limit]


def save_job_feedback(job: dict, status: str, note: str = "") -> Path:
    return append_jsonl(
        "job_feedback.jsonl",
        {
            "job_key": _job_key(job),
            "platform": job.get("platform", ""),
            "company": job.get("company", ""),
            "title": job.get("title", ""),
            "status": status,
            "note": note,
        },
    )


def load_job_feedback(limit: int = 200) -> list[dict]:
    return _read_jsonl("job_feedback.jsonl", limit=limit)


def load_application_records(limit: int = 200) -> list[dict]:
    return _read_jsonl("applications.jsonl", limit=limit)


def export_memory_snapshot() -> dict:
    return {
        "profile": load_profile(),
        "job_feedback": load_job_feedback(limit=500),
        "applications": load_application_records(limit=500),
        "search_history": _read_jsonl("search_history.jsonl", limit=200),
        "agent_runs": load_agent_runs(limit=100),
        "exported_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def save_application_record(job: dict, status: str, next_action: str = "", note: str = "") -> Path:
    return append_jsonl(
        "applications.jsonl",
        {
            "job_key": _job_key(job),
            "platform": job.get("platform", ""),
            "company": job.get("company", ""),
            "title": job.get("title", ""),
            "status": status,
            "next_action": next_action,
            "note": note,
        },
    )


def _path(name: str) -> Path:
    safe_name = name.replace("\\", "/").lstrip("/")
    return MEMORY_DIR / safe_name


def _write_agent_run(record: dict) -> Path:
    AGENT_RUNS_DIR.mkdir(parents=True, exist_ok=True)
    path = AGENT_RUNS_DIR / f"{record['run_id']}.json"
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _read_jsonl(name: str, limit: int = 200) -> list[dict]:
    path = _path(name)
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines()[-limit:]:
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def _job_key(job: dict) -> str:
    return "|".join(
        str(job.get(key) or "").strip()
        for key in ("platform", "job_id", "company", "title")
    )


def _decision_counts(jobs: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for job in jobs:
        level = (job.get("job_decision") or {}).get("level", "未评估")
        counts[level] = counts.get(level, 0) + 1
    return counts


def _top_job_summary(jobs: list[dict]) -> dict:
    if not jobs:
        return {}
    job = jobs[0]
    decision = job.get("job_decision") or {}
    return {
        "company": job.get("company", ""),
        "title": job.get("title", ""),
        "platform": job.get("platform", ""),
        "salary": job.get("salary", ""),
        "level": decision.get("level", ""),
        "score": decision.get("score", ""),
    }


def _top_jobs_summary(jobs: list[dict], limit: int = 10) -> list[dict]:
    rows = []
    for job in jobs[:limit]:
        decision = job.get("job_decision") or {}
        rows.append({
            "company": job.get("company", ""),
            "title": job.get("title", ""),
            "platform": job.get("platform", ""),
            "location": job.get("location", ""),
            "salary": job.get("salary", ""),
            "experience": job.get("experience_display") or job.get("experience", ""),
            "degree": job.get("degree_display") or job.get("degree", ""),
            "weekend": job.get("weekend_display") or job.get("weekend_policy", ""),
            "level": decision.get("level", ""),
            "score": decision.get("score", ""),
            "matched_reasons": decision.get("matched_reasons", [])[:3],
            "risks": decision.get("risks", [])[:3],
            "resume_actions": decision.get("resume_actions", [])[:3],
            "interview_focus": decision.get("interview_focus", [])[:3],
        })
    return rows


def _public_plan(plan: dict) -> dict:
    return {
        key: value
        for key, value in (plan or {}).items()
        if not str(key).startswith("_")
    }


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
