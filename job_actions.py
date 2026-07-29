"""Job action context: bookmarks, feedback, and applications."""

from __future__ import annotations

NEGATIVE_STATUSES = {"不合适", "已拒绝", "不看", "拉黑"}
POSITIVE_STATUSES = {"收藏", "感兴趣", "已投递", "已沟通", "面试中"}
APPLICATION_STATUSES = {"已投递", "已沟通", "面试中", "offer", "已录用"}


def build_action_context(feedback: list[dict] | None = None, applications: list[dict] | None = None) -> dict:
    """Build lookup maps for fast job action annotation."""
    feedback = list(feedback or [])
    applications = list(applications or [])
    context = {
        "feedback_by_key": {},
        "applications_by_key": {},
        "disliked_companies": set(),
        "interested_companies": set(),
    }
    for item in feedback:
        status = str(item.get("status") or "")
        _index_action(context["feedback_by_key"], item)
        company = str(item.get("company") or "")
        if status in NEGATIVE_STATUSES and company:
            context["disliked_companies"].add(company)
        if status in POSITIVE_STATUSES and company:
            context["interested_companies"].add(company)
    for item in applications:
        _index_action(context["applications_by_key"], item)
    return context


def annotate_jobs_with_actions(
    jobs: list[dict],
    *,
    feedback: list[dict] | None = None,
    applications: list[dict] | None = None,
    context: dict | None = None,
    adjust_scores: bool = False,
    resort: bool = False,
) -> list[dict]:
    """Return copied jobs annotated with latest feedback/application status."""
    context = context or build_action_context(feedback, applications)
    annotated = [_annotate_job(dict(job), context, adjust_scores=adjust_scores) for job in jobs]
    if resort:
        annotated.sort(key=_sort_score, reverse=True)
    return annotated


def summarize_action_context(jobs: list[dict]) -> dict:
    counts: dict[str, int] = {}
    for job in jobs:
        for tag in job.get("action_status_tags") or []:
            counts[tag] = counts.get(tag, 0) + 1
    return {
        "status_counts": counts,
        "bookmarked": counts.get("收藏", 0),
        "applied": sum(counts.get(status, 0) for status in APPLICATION_STATUSES),
        "negative": sum(counts.get(status, 0) for status in NEGATIVE_STATUSES),
    }


def action_score_delta(job: dict) -> float:
    status = str(job.get("action_feedback_status") or "")
    application_status = str(job.get("action_application_status") or "")
    if status in NEGATIVE_STATUSES:
        return -22.0
    if application_status in APPLICATION_STATUSES:
        return 5.0
    if status in {"收藏", "感兴趣"}:
        return 4.0
    return 0.0


def _annotate_job(job: dict, context: dict, *, adjust_scores: bool) -> dict:
    feedback = _lookup_action(context.get("feedback_by_key") or {}, job)
    application = _lookup_action(context.get("applications_by_key") or {}, job)
    feedback_status = str((feedback or {}).get("status") or "")
    application_status = str((application or {}).get("status") or "")
    tags = []
    if feedback_status:
        tags.append(feedback_status)
    if application_status and application_status not in tags:
        tags.append(application_status)

    job["action_feedback_status"] = feedback_status
    job["action_application_status"] = application_status
    job["action_status_tags"] = tags
    job["action_bookmarked"] = feedback_status == "收藏"
    job["action_negative"] = feedback_status in NEGATIVE_STATUSES
    job["action_note"] = str((feedback or application or {}).get("note") or "")
    job["action_next_action"] = str((application or {}).get("next_action") or "")

    if adjust_scores:
        _adjust_resume_match_score(job)
    return job


def _adjust_resume_match_score(job: dict) -> None:
    delta = action_score_delta(job)
    match = job.get("resume_match")
    if not isinstance(match, dict) or not delta:
        return
    score = _to_score(match.get("score"))
    if score is None:
        return
    adjusted = max(0.0, min(100.0, score + delta))
    if job.get("action_negative"):
        adjusted = min(adjusted, 55.0)
    match["base_score"] = score
    match["score"] = round(adjusted, 1)
    match["action_adjustment"] = delta


def _index_action(index: dict[str, dict], item: dict) -> None:
    for key in _record_keys(item):
        if key:
            index[key] = dict(item)


def _lookup_action(index: dict[str, dict], job: dict) -> dict:
    for key in _job_lookup_keys(job):
        if key in index:
            return index[key]
    return {}


def _record_keys(item: dict) -> list[str]:
    return _keys(
        item.get("platform", ""),
        item.get("job_id", ""),
        item.get("company", ""),
        item.get("title", ""),
        item.get("job_key", ""),
    )


def _job_lookup_keys(job: dict) -> list[str]:
    return _keys(
        job.get("platform", ""),
        job.get("job_id", ""),
        job.get("company", ""),
        job.get("title", ""),
        "",
    )


def _keys(platform: object, job_id: object, company: object, title: object, job_key: object) -> list[str]:
    values = {
        "platform": str(platform or "").strip(),
        "job_id": str(job_id or "").strip(),
        "company": str(company or "").strip(),
        "title": str(title or "").strip(),
        "job_key": str(job_key or "").strip(),
    }
    keys = []
    if values["job_key"]:
        keys.append(values["job_key"])
    if values["platform"] and values["job_id"]:
        keys.append(f"{values['platform']}|{values['job_id']}")
    if values["platform"] and values["job_id"] and values["company"] and values["title"]:
        keys.append(f"{values['platform']}|{values['job_id']}|{values['company']}|{values['title']}")
    if values["company"] and values["title"]:
        keys.append(f"{values['company']}|{values['title']}")
    if values["company"]:
        keys.append(f"company:{values['company']}")
    return _unique(keys)


def _sort_score(job: dict) -> float:
    for payload in (job.get("job_decision") or {}, job.get("resume_match") or {}):
        score = _to_score(payload.get("score"))
        if score is not None:
            return score
    return 0.0


def _to_score(value: object) -> float | None:
    try:
        return max(0.0, min(100.0, float(value)))
    except (TypeError, ValueError):
        return None


def _unique(items: list[str]) -> list[str]:
    result = []
    for item in items:
        if item and item not in result:
            result.append(item)
    return result
