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
        "llm_rerank_requested": summary.get("llm_rerank_requested", 0),
        "llm_rerank_success": summary.get("llm_rerank_success", 0),
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


def load_outreach_tasks() -> list[dict]:
    tasks = read_json("outreach_tasks.json", []) or []
    if not isinstance(tasks, list):
        return []
    normalized = [_normalize_outreach_task(task, index) for index, task in enumerate(tasks) if isinstance(task, dict)]
    normalized.sort(key=lambda item: int(item.get("order", 0)))
    return normalized


def save_outreach_task(task: dict) -> dict:
    tasks = load_outreach_tasks()
    payload = _normalize_outreach_task(task, len(tasks))
    now = _now()
    payload["updated_at"] = now
    task_id = payload.get("task_id") or f"task_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:6]}"
    payload["task_id"] = task_id

    replaced = False
    for index, existing in enumerate(tasks):
        if existing.get("task_id") == task_id:
            payload.setdefault("created_at", existing.get("created_at") or now)
            payload["created_at"] = payload.get("created_at") or existing.get("created_at") or now
            payload["order"] = int(existing.get("order", index))
            tasks[index] = payload
            replaced = True
            break
    if not replaced:
        payload["created_at"] = payload.get("created_at") or now
        payload["order"] = len(tasks)
        tasks.append(payload)

    _write_ordered_outreach_tasks(tasks)
    return payload


def delete_outreach_task(task_id: str) -> bool:
    tasks = load_outreach_tasks()
    kept = [task for task in tasks if task.get("task_id") != task_id]
    if len(kept) == len(tasks):
        return False
    _write_ordered_outreach_tasks(kept)
    return True


def move_outreach_task(task_id: str, direction: int) -> list[dict]:
    tasks = load_outreach_tasks()
    index = next((i for i, task in enumerate(tasks) if task.get("task_id") == task_id), None)
    if index is None:
        return tasks
    target = max(0, min(len(tasks) - 1, index + int(direction)))
    if target != index:
        tasks[index], tasks[target] = tasks[target], tasks[index]
    return _write_ordered_outreach_tasks(tasks)


def export_memory_snapshot() -> dict:
    return {
        "profile": load_profile(),
        "job_feedback": load_job_feedback(limit=500),
        "applications": load_application_records(limit=500),
        "outreach_tasks": load_outreach_tasks(),
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


def save_outreach_record(
    job: dict,
    *,
    task_id: str = "",
    action_type: str = "greeting",
    message_text: str = "",
    max_chars: int | None = None,
    custom_prompt: str = "",
    confirm_required: bool = True,
    send_result: str = "",
    platform_url: str = "",
    error: str = "",
    status: str = "drafted",
    note: str = "",
) -> Path:
    return append_jsonl(
        "applications.jsonl",
        {
            "job_key": _job_key(job),
            "task_id": task_id,
            "platform": job.get("platform", ""),
            "company": job.get("company", ""),
            "title": job.get("title", ""),
            "status": status,
            "action_type": action_type,
            "message_text": message_text,
            "max_chars": max_chars,
            "custom_prompt": custom_prompt,
            "confirm_required": bool(confirm_required),
            "send_result": send_result,
            "platform_url": platform_url or job.get("chat_url") or job.get("source_url") or job.get("url", ""),
            "error": error,
            "note": note,
        },
    )


def _path(name: str) -> Path:
    safe_name = name.replace("\\", "/").lstrip("/")
    return MEMORY_DIR / safe_name


def _normalize_outreach_task(task: dict, index: int = 0) -> dict:
    payload = dict(task or {})
    payload["task_id"] = str(payload.get("task_id") or "").strip()
    payload["name"] = str(payload.get("name") or payload.get("keyword") or "未命名任务").strip()
    payload["natural_text"] = str(payload.get("natural_text") or "").strip()
    payload["keyword"] = str(payload.get("keyword") or payload.get("search_text") or "AI Agent").strip()
    payload["search_text"] = str(payload.get("search_text") or payload.get("keyword") or "AI Agent").strip()
    payload["cities"] = _normalize_text_list(payload.get("cities") or payload.get("cities_text") or payload.get("location") or "上海")
    payload["cities_text"] = str(payload.get("cities_text") or " ".join(payload["cities"]) or "上海").strip()
    payload["location"] = str(payload.get("location") or (payload["cities"][0] if payload["cities"] else "上海")).strip()
    payload["platforms"] = _normalize_text_list(payload.get("platforms") or ["boss", "zhilian", "51job"])
    payload["max_pages"] = _clamp_int(payload.get("max_pages"), 1, 10, 2)
    payload["criteria"] = payload.get("criteria") if isinstance(payload.get("criteria"), dict) else {}
    payload["job_types"] = _normalize_text_list(payload.get("job_types") or payload["criteria"].get("job_types") or ["社招"])
    payload["ai_filter_text"] = str(payload.get("ai_filter_text") or "").strip()
    payload["regex_include"] = str(payload.get("regex_include") or "").strip()
    payload["regex_exclude"] = str(payload.get("regex_exclude") or "").strip()
    payload["match_threshold"] = _clamp_int(payload.get("match_threshold"), 0, 100, 70)
    payload["greeting_max_chars"] = _clamp_int(payload.get("greeting_max_chars"), 20, 300, 100)
    payload["greeting_prompt"] = str(payload.get("greeting_prompt") or "").strip()
    payload["reply_prompt"] = str(payload.get("reply_prompt") or "").strip()
    payload["only_active_hr"] = bool(payload.get("only_active_hr", False))
    payload["job_kind"] = str(payload.get("job_kind") or "").strip()
    payload["send_limit"] = _clamp_int(payload.get("send_limit"), 1, 1, 1)
    payload["order"] = _clamp_int(payload.get("order"), 0, 100000, index)
    return payload


def _write_ordered_outreach_tasks(tasks: list[dict]) -> list[dict]:
    ordered = []
    for index, task in enumerate(tasks):
        item = _normalize_outreach_task(task, index)
        item["order"] = index
        ordered.append(item)
    write_json("outreach_tasks.json", ordered)
    return ordered


def _normalize_text_list(value: Any) -> list[str]:
    if isinstance(value, str):
        raw = re_split_text(value)
    elif isinstance(value, (list, tuple, set)):
        raw = []
        for item in value:
            raw.extend(re_split_text(item) if isinstance(item, str) else [item])
    else:
        raw = []
    result = []
    for item in raw:
        text = str(item or "").strip()
        if text and text not in result:
            result.append(text)
    return result


def re_split_text(value: object) -> list[str]:
    import re

    return [part for part in re.split(r"[,，、\s/]+", str(value or "")) if part]


def _clamp_int(value: object, min_value: int, max_value: int, default: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = int(default)
    return max(min_value, min(max_value, number))


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
        ai_match = job.get("ai_match") or (job.get("resume_match") or {}).get("ai") or {}
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
            "matched_reasons": (ai_match.get("matched_evidence") or decision.get("matched_reasons", []))[:3],
            "risks": (ai_match.get("risk_points") or ai_match.get("risks") or decision.get("risks", []))[:3],
            "resume_actions": (ai_match.get("resume_actions") or decision.get("resume_actions", []))[:3],
            "interview_focus": (ai_match.get("interview_focus") or decision.get("interview_focus", []))[:3],
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
