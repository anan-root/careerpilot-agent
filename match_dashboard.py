"""Reusable match dashboard summaries for API and Streamlit."""

from __future__ import annotations

from collections import Counter

from job_actions import summarize_action_context


def build_match_dashboard(jobs: list[dict], *, top_n: int = 8) -> dict:
    """Summarize ranked jobs into product-facing dashboard data."""
    scored = [
        (job, score)
        for job in jobs
        if (score := _job_score(job)) is not None
    ]
    scores = [score for _, score in scored]
    missing_counter: Counter[str] = Counter()
    matched_counter: Counter[str] = Counter()
    for job, _ in scored:
        missing_counter.update(_text_items(_match_payload(job).get("missing_keywords")))
        missing_counter.update(_text_items(_ai_payload(job).get("missing_requirements")))
        matched_counter.update(_text_items(_match_payload(job).get("matched_keywords")))
        matched_counter.update(_text_items(_match_payload(job).get("skill_matches")))
        matched_counter.update(_text_items(_ai_payload(job).get("matched_evidence")))

    return {
        "total": len(jobs),
        "evaluated_count": len(scored),
        "avg_score": round(sum(scores) / len(scores), 1) if scores else 0.0,
        "high_match_count": sum(1 for score in scores if score >= 75),
        "platform_counts": dict(Counter(str(job.get("platform") or "unknown") for job in jobs)),
        "level_counts": dict(Counter(_score_level(score) for score in scores)),
        "top_companies": [
            item
            for item, _ in Counter(str(job.get("company") or "") for job in jobs if job.get("company")).most_common(10)
        ],
        "top_missing_keywords": [item for item, _ in missing_counter.most_common(12)],
        "top_matched_keywords": [item for item, _ in matched_counter.most_common(12)],
        "avg_field_quality": _avg_field_quality(jobs),
        "action_summary": summarize_action_context(jobs),
        "top_jobs": [_job_summary(job, index) for index, (job, _) in enumerate(scored[:top_n], 1)],
    }


def _job_summary(job: dict, rank: int) -> dict:
    score = _job_score(job)
    match = _match_payload(job)
    ai_match = _ai_payload(job)
    decision = job.get("job_decision") or {}
    return {
        "rank": rank,
        "company": str(job.get("company") or ""),
        "title": str(job.get("title") or ""),
        "platform": str(job.get("platform") or ""),
        "location": str(job.get("location") or ""),
        "salary": str(job.get("salary") or ""),
        "score": score,
        "level": _score_level(score),
        "matched_keywords": _text_items(match.get("matched_keywords") or match.get("skill_matches"))[:8],
        "missing_keywords": _text_items(
            ai_match.get("missing_requirements")
            or match.get("missing_keywords")
            or decision.get("missing_requirements")
        )[:8],
        "risks": _text_items(ai_match.get("risk_points") or decision.get("risks"))[:5],
        "action_status_tags": _text_items(job.get("action_status_tags"))[:5],
        "source_url": str(job.get("source_url") or job.get("url") or ""),
    }


def _job_score(job: dict) -> float | None:
    for payload in (
        job.get("job_decision") or {},
        job.get("ai_match") or {},
        (job.get("resume_match") or {}).get("ai") or {},
        job.get("resume_match") or {},
    ):
        value = payload.get("score") if isinstance(payload, dict) else None
        score = _to_score(value)
        if score is not None:
            return score
    return None


def _score_level(score: float | None) -> str:
    if score is None:
        return "未评估"
    if score >= 85:
        return "强匹配"
    if score >= 70:
        return "优先看"
    if score >= 55:
        return "可考虑"
    return "低匹配"


def _avg_field_quality(jobs: list[dict]) -> float:
    scores = [_to_score(job.get("field_quality_score")) for job in jobs]
    scores = [score for score in scores if score is not None]
    return round(sum(scores) / len(scores), 1) if scores else 0.0


def _match_payload(job: dict) -> dict:
    payload = job.get("resume_match") or {}
    return payload if isinstance(payload, dict) else {}


def _ai_payload(job: dict) -> dict:
    payload = job.get("ai_match") or _match_payload(job).get("ai") or {}
    return payload if isinstance(payload, dict) else {}


def _text_items(value: object) -> list[str]:
    if value is None:
        return []
    source = value if isinstance(value, (list, tuple, set)) else [value]
    result: list[str] = []
    for item in source:
        text = str(item or "").strip()
        if text and text not in result:
            result.append(text)
    return result


def _to_score(value: object) -> float | None:
    if value in (None, ""):
        return None
    try:
        return round(max(0.0, min(100.0, float(value))), 1)
    except (TypeError, ValueError):
        return None
