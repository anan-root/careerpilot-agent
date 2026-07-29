"""Search summary merge helpers shared by UI and tests."""

from __future__ import annotations

from collections import Counter


def merge_invalid_job_summaries(summaries: list[dict]) -> dict:
    reason_counts: Counter[str] = Counter()
    platform_counts: Counter[str] = Counter()
    total = 0
    for item in summaries:
        payload = item.get("search_invalid_jobs") or {}
        total += int(payload.get("total", 0) or 0)
        reason_counts.update(payload.get("reason_counts") or {})
        platform_counts.update(payload.get("platform_counts") or {})
    return {
        "total": total,
        "reason_counts": dict(reason_counts),
        "platform_counts": dict(platform_counts),
    }


def merge_duplicate_summaries(summaries: list[dict]) -> dict:
    reason_counts: Counter[str] = Counter()
    result = {"input": 0, "kept": 0, "dropped": 0}
    for item in summaries:
        payload = item.get("search_duplicate_summary") or {}
        result["input"] += int(payload.get("input", 0) or 0)
        result["kept"] += int(payload.get("kept", 0) or 0)
        result["dropped"] += int(payload.get("dropped", 0) or 0)
        reason_counts.update(payload.get("reason_counts") or {})
    result["reason_counts"] = dict(reason_counts)
    return result


def merge_job_quality_summaries(summaries: list[dict]) -> dict:
    total = 0
    weighted_confidence = 0.0
    label_counts: Counter[str] = Counter()
    field_totals: dict[str, float] = {}
    field_weights: dict[str, int] = {}
    for item in summaries:
        payload = item.get("search_job_quality") or {}
        count = int(payload.get("total", 0) or 0)
        total += count
        weighted_confidence += float(payload.get("avg_confidence", 0) or 0) * count
        label_counts.update(payload.get("label_counts") or {})
        for field, value in (payload.get("avg_field_confidence") or {}).items():
            field_totals[field] = field_totals.get(field, 0.0) + float(value or 0) * count
            field_weights[field] = field_weights.get(field, 0) + count
    return {
        "total": total,
        "avg_confidence": round(weighted_confidence / total, 1) if total else 0.0,
        "label_counts": dict(label_counts),
        "avg_field_confidence": {
            field: round(value / field_weights[field], 1)
            for field, value in field_totals.items()
            if field_weights.get(field)
        },
    }
