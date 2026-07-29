"""Job quality controls for collection, import, and ranking surfaces."""

from __future__ import annotations

from collections import Counter

EMPTY_MARKERS = ("", "未知", "暂无", "列表页未提供", "未公开", "不详", "none", "null")
INVALID_TITLE_MARKERS = ("登录", "验证码", "搜索结果", "职位列表", "没有找到", "暂无岗位", "页面不存在")

CONFIDENCE_FIELD_SOURCES = {
    "title": ("title",),
    "company": ("company",),
    "location": ("location", "company_address"),
    "salary": ("salary",),
    "experience": ("experience", "experience_display"),
    "degree": ("degree", "degree_display"),
    "job_text": ("full_jd", "requirements", "description"),
    "source": ("source_url", "url"),
}


def apply_quality_control(job: dict) -> dict:
    """Attach field confidence and invalid-job metadata to a job dict."""
    assessment = assess_job_quality(job)
    job["field_confidence"] = assessment["field_confidence"]
    job["job_quality_confidence_score"] = assessment["confidence_score"]
    job["job_quality_label"] = assessment["label"]
    job["job_quality_invalid"] = assessment["invalid"]
    job["job_quality_invalid_reasons"] = assessment["invalid_reasons"]
    return job


def assess_job_quality(job: dict) -> dict:
    field_confidence = {
        field: _field_confidence(job, source_fields)
        for field, source_fields in CONFIDENCE_FIELD_SOURCES.items()
    }
    confidence_values = list(field_confidence.values())
    confidence_score = round(sum(confidence_values) / len(confidence_values), 1) if confidence_values else 0.0
    invalid_reasons = invalid_job_reasons(job)
    return {
        "field_confidence": field_confidence,
        "confidence_score": confidence_score,
        "label": _quality_label(confidence_score, invalid_reasons),
        "invalid": bool(invalid_reasons),
        "invalid_reasons": invalid_reasons,
    }


def invalid_job_reasons(job: dict) -> list[str]:
    reasons: list[str] = []
    title = str(job.get("title") or "").strip()
    company = str(job.get("company") or "").strip()
    source_url = str(job.get("source_url") or job.get("url") or "").strip()

    if not _has_value(title):
        reasons.append("缺少岗位名称")
    elif any(marker in title for marker in INVALID_TITLE_MARKERS):
        reasons.append("岗位名称像页面提示")

    if not _has_value(company) and not _has_value(source_url):
        reasons.append("缺少公司和来源")

    if not any(_has_value(job.get(field)) for field in ("description", "requirements", "full_jd", "skills", "salary", "location")):
        reasons.append("岗位信息过少")

    return _unique(reasons)


def filter_invalid_jobs(jobs: list[dict]) -> tuple[list[dict], dict]:
    valid: list[dict] = []
    invalid: list[dict] = []
    for job in jobs:
        apply_quality_control(job)
        if job.get("job_quality_invalid"):
            invalid.append(job)
        else:
            valid.append(job)
    return valid, summarize_invalid_jobs(invalid)


def summarize_invalid_jobs(jobs: list[dict]) -> dict:
    reason_counts: Counter[str] = Counter()
    platform_counts: Counter[str] = Counter()
    for job in jobs:
        platform_counts[str(job.get("platform") or "unknown")] += 1
        reason_counts.update(job.get("job_quality_invalid_reasons") or ["未知原因"])
    return {
        "total": len(jobs),
        "reason_counts": dict(reason_counts),
        "platform_counts": dict(platform_counts),
    }


def summarize_job_quality(jobs: list[dict]) -> dict:
    if not jobs:
        return {
            "total": 0,
            "avg_confidence": 0.0,
            "label_counts": {},
            "avg_field_confidence": {},
        }

    for job in jobs:
        if "field_confidence" not in job:
            apply_quality_control(job)

    field_totals: dict[str, list[float]] = {field: [] for field in CONFIDENCE_FIELD_SOURCES}
    labels: Counter[str] = Counter()
    scores = []
    for job in jobs:
        labels[str(job.get("job_quality_label") or "未知")] += 1
        scores.append(float(job.get("job_quality_confidence_score") or 0))
        for field, value in (job.get("field_confidence") or {}).items():
            field_totals.setdefault(field, []).append(float(value or 0))

    return {
        "total": len(jobs),
        "avg_confidence": round(sum(scores) / len(scores), 1) if scores else 0.0,
        "label_counts": dict(labels),
        "avg_field_confidence": {
            field: round(sum(values) / len(values), 1) if values else 0.0
            for field, values in field_totals.items()
        },
    }


def _field_confidence(job: dict, fields: tuple[str, ...]) -> int:
    best = 0
    for field in fields:
        value = str(job.get(field) or "").strip()
        if not _has_value(value):
            continue
        if value.startswith("列表页未提供") or value in {"未知", "暂无"}:
            best = max(best, 20)
        elif len(value) >= 12:
            best = max(best, 90)
        else:
            best = max(best, 75)
    return best


def _quality_label(score: float, invalid_reasons: list[str]) -> str:
    if invalid_reasons:
        return "无效"
    if score >= 80:
        return "高"
    if score >= 60:
        return "中"
    return "低"


def _has_value(value: object) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    return not any(text.lower().startswith(marker) for marker in EMPTY_MARKERS if marker)


def _unique(items: list[str]) -> list[str]:
    result: list[str] = []
    for item in items:
        if item and item not in result:
            result.append(item)
    return result
