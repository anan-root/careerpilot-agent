"""Shared job schema helpers for platform-normalized job records."""

from __future__ import annotations

from typing import Protocol

JOB_SCHEMA_VERSION = "job_schema_v1"

CANONICAL_JOB_FIELDS = (
    "platform",
    "job_id",
    "title",
    "company",
    "location",
    "salary",
    "job_type",
    "description",
    "requirements",
    "skills",
    "degree",
    "experience",
    "company_size",
    "company_industry",
    "company_stage",
    "welfare",
    "company_address",
    "url",
    "source_url",
    "posted_date",
    "crawl_status",
    "crawl_keyword",
    "detail_status",
    "detail_source_url",
)

QUALITY_FIELD_GROUPS = {
    "identity": ("platform", "job_id", "url"),
    "title": ("title",),
    "company": ("company",),
    "location": ("location", "company_address"),
    "salary": ("salary",),
    "experience": ("experience", "experience_display"),
    "degree": ("degree", "degree_display"),
    "job_text": ("full_jd", "requirements", "description"),
    "skills": ("skills",),
    "welfare": ("welfare", "weekend_policy"),
}

EMPTY_MARKERS = ("未知", "暂无", "列表页未提供", "未公开", "不详", "none", "null")


class PlatformAdapter(Protocol):
    """Contract for product-grade platform crawlers."""

    platform: str

    def search_jobs(self, keyword: str, city: str, page: int = 1) -> list[dict]:
        ...

    def fetch_detail(self, job: dict) -> dict:
        ...

    def normalize(self, raw_job: dict) -> dict:
        ...


def apply_job_schema(job: dict) -> dict:
    """Mutate a job dict with canonical defaults and field quality metadata."""
    for field in CANONICAL_JOB_FIELDS:
        job.setdefault(field, "")
    if not job.get("source_url"):
        job["source_url"] = job.get("url", "")

    quality = assess_field_quality(job)
    job["job_schema_version"] = JOB_SCHEMA_VERSION
    job["field_quality_score"] = quality["score"]
    job["field_quality_filled"] = quality["filled"]
    job["field_quality_total"] = quality["total"]
    job["field_quality_missing"] = quality["missing"]
    return job


def assess_field_quality(job: dict) -> dict:
    """Score whether a job has enough normalized fields for reliable matching."""
    filled: list[str] = []
    missing: list[str] = []

    for group, fields in QUALITY_FIELD_GROUPS.items():
        if any(_has_value(job.get(field)) for field in fields):
            filled.append(group)
        else:
            missing.append(group)

    total = len(QUALITY_FIELD_GROUPS)
    score = round(len(filled) / total * 100, 1) if total else 0.0
    return {
        "score": score,
        "filled": filled,
        "missing": missing,
        "total": total,
    }


def _has_value(value: object) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    return not any(text.lower().startswith(marker) for marker in EMPTY_MARKERS)
