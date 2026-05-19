"""Shared job filtering helpers."""

from __future__ import annotations

import re

FULL_TIME_TYPES = {"社招", "全职"}
CAMPUS_TYPES = {"校招", "应届"}
INTERN_TYPES = {"实习", "日常实习", "暑期实习"}
ALL_JOB_TYPE_GROUPS = ("社招", "校招", "实习")

DEGREE_LEVELS = {
    "不限": 0,
    "大专": 1,
    "本科": 2,
    "硕士": 3,
    "博士": 4,
}


def normalize_job_type(value: str | None, job: dict | None = None) -> str:
    """Normalize platform-specific job type text into 社招/校招/实习."""
    type_text = str(value or "")
    if any(token in type_text for token in INTERN_TYPES):
        return "实习"
    if any(token in type_text for token in CAMPUS_TYPES):
        return "校招"
    if any(token in type_text for token in FULL_TIME_TYPES):
        return "社招"

    text = ""
    if job:
        text = " ".join(
            str(job.get(key, ""))
            for key in ("title", "description", "requirements", "skills")
        )

    if any(token in text for token in INTERN_TYPES):
        return "实习"
    if any(token in text for token in CAMPUS_TYPES):
        return "校招"
    return "社招"


def job_matches_type(job: dict, selected_types: list[str] | tuple[str, ...] | set[str] | None) -> bool:
    """Return whether a job belongs to one of the selected broad type groups."""
    if not selected_types:
        return True
    normalized = normalize_job_type(job.get("job_type"), job)
    return normalized in set(selected_types)


def filter_jobs_by_type(jobs: list[dict], selected_types: list[str] | tuple[str, ...] | set[str] | None) -> list[dict]:
    """Filter jobs by broad type groups and write normalized_job_type for display."""
    if not selected_types:
        filtered = list(jobs)
    else:
        filtered = [job for job in jobs if job_matches_type(job, selected_types)]

    for job in filtered:
        job["normalized_job_type"] = normalize_job_type(job.get("job_type"), job)
    return filtered


def enrich_job_fields(job: dict) -> dict:
    """Add normalized display/filter fields without mutating source assumptions."""
    job["normalized_job_type"] = normalize_job_type(job.get("job_type"), job)
    job["salary_min_k"], job["salary_max_k"] = parse_salary_monthly_k(job.get("salary", ""))
    job["experience_years_min"] = parse_experience_years(job)
    job["degree_level"] = parse_degree_level(job)
    job["company_address"] = infer_company_address(job)
    job["weekend_policy"] = infer_weekend_policy(job)
    job["experience_display"] = infer_experience_display(job)
    job["degree_display"] = infer_degree_display(job)
    job["weekend_display"] = infer_weekend_display(job)
    return job


def filter_jobs(jobs: list[dict], criteria: dict | None = None) -> list[dict]:
    """Filter jobs using shared fields across platforms.

    Missing platform fields are treated as unknown and kept for most filters, so a
    sparse crawler result is not discarded just because the platform omitted data.
    """
    criteria = criteria or {}
    selected_types = criteria.get("job_types")
    min_salary = criteria.get("min_salary_k")
    max_salary = criteria.get("max_salary_k")
    max_experience = criteria.get("max_experience_years")
    degrees = criteria.get("degrees")
    weekend_only = criteria.get("weekend_only")

    results: list[dict] = []
    for raw in jobs:
        job = enrich_job_fields(raw)

        if selected_types and job["normalized_job_type"] not in set(selected_types):
            continue

        salary_min = job.get("salary_min_k")
        salary_max = job.get("salary_max_k")
        if min_salary is not None and salary_max is not None and salary_max < float(min_salary):
            continue
        if max_salary is not None and salary_min is not None and salary_min > float(max_salary):
            continue

        if max_experience is not None:
            exp_min = job.get("experience_years_min")
            if exp_min is not None and exp_min > int(max_experience):
                continue

        if degrees:
            required_level = job.get("degree_level")
            allowed_levels = [DEGREE_LEVELS[d] for d in degrees if d in DEGREE_LEVELS]
            if required_level is not None and allowed_levels and required_level > max(allowed_levels):
                continue

        if weekend_only and job.get("weekend_policy") not in ("双休", "大小周/双休不确定"):
            continue

        results.append(job)
    return results


def parse_salary_monthly_k(value: str | None) -> tuple[float | None, float | None]:
    text = str(value or "").replace(" ", "")
    if not text:
        return None, None

    match = re.search(r"(\d+(?:\.\d+)?)-(\d+(?:\.\d+)?)[kK]", text)
    if match:
        return float(match.group(1)), float(match.group(2))

    match = re.search(r"(\d+(?:\.\d+)?)[kK]", text)
    if match:
        val = float(match.group(1))
        return val, val

    match = re.search(r"(\d+(?:\.\d+)?)-(\d+(?:\.\d+)?)万/年", text)
    if match:
        return float(match.group(1)) * 10 / 12, float(match.group(2)) * 10 / 12

    match = re.search(r"(\d+(?:\.\d+)?)万/年", text)
    if match:
        val = float(match.group(1)) * 10 / 12
        return val, val

    match = re.search(r"(\d+(?:\.\d+)?)千-(\d+(?:\.\d+)?)万", text)
    if match:
        return float(match.group(1)), float(match.group(2)) * 10

    match = re.search(r"(\d+(?:\.\d+)?)-(\d+(?:\.\d+)?)万(?:/月|·\d+薪)?", text)
    if match:
        return float(match.group(1)) * 10, float(match.group(2)) * 10

    match = re.search(r"(\d+(?:\.\d+)?)万(?:/月|·\d+薪)?", text)
    if match:
        val = float(match.group(1)) * 10
        return val, val

    match = re.search(r"(\d+(?:\.\d+)?)千", text)
    if match:
        val = float(match.group(1))
        return val, val

    match = re.search(r"(\d+(?:\.\d+)?)-(\d+(?:\.\d+)?)[kK]", text)
    if match:
        return float(match.group(1)), float(match.group(2))

    match = re.search(r"(\d+(?:\.\d+)?)[kK]", text)
    if match:
        val = float(match.group(1))
        return val, val

    match = re.search(r"(\d+)-(\d+)元/月", text)
    if match:
        return float(match.group(1)) / 1000, float(match.group(2)) / 1000

    match = re.search(r"(\d+)-(\d+)元/天", text)
    if match:
        lo = float(match.group(1)) * 22 / 1000
        hi = float(match.group(2)) * 22 / 1000
        return lo, hi

    match = re.search(r"(\d+)元/天", text)
    if match:
        val = float(match.group(1)) * 22 / 1000
        return val, val

    return None, None


def parse_experience_years(job: dict) -> int | None:
    text = " ".join(str(job.get(key, "")) for key in ("experience", "requirements", "description", "skills"))
    if any(token in text for token in ("经验不限", "不限经验", "无需经验", "无经验", "应届", "在校生")):
        return 0
    match = re.search(r"(\d+)\s*年以上", text)
    if match:
        return int(match.group(1))
    match = re.search(r"(\d+)\s*-\s*(\d+)\s*年", text)
    if match:
        return int(match.group(1))
    match = re.search(r"(\d+)\s*年(?:及)?以上", text)
    if match:
        return int(match.group(1))
    match = re.search(r"(\d+)\s*年", text)
    if match:
        return int(match.group(1))
    return None


def parse_degree_level(job: dict) -> int | None:
    text = " ".join(str(job.get(key, "")) for key in ("degree", "requirements", "description"))
    if any(token in text for token in ("博士", "博士研究生")):
        return DEGREE_LEVELS["博士"]
    if any(token in text for token in ("硕士", "研究生")):
        return DEGREE_LEVELS["硕士"]
    if "本科" in text:
        return DEGREE_LEVELS["本科"]
    if any(token in text for token in ("大专", "专科")):
        return DEGREE_LEVELS["大专"]
    if "不限" in text:
        return DEGREE_LEVELS["不限"]
    return None


def infer_company_address(job: dict) -> str:
    return str(job.get("company_address") or job.get("address") or job.get("location") or "")


def infer_weekend_policy(job: dict) -> str:
    text = " ".join(str(job.get(key, "")) for key in ("welfare", "description", "requirements", "skills"))
    if any(token in text for token in ("双休", "周末双休", "五天工作制", "周末休息")):
        return "双休"
    if "大小周" in text:
        return "大小周/双休不确定"
    if any(token in text for token in ("单休", "单双休")):
        return "非双休/不确定"
    return "未知"


def infer_experience_display(job: dict) -> str:
    value = str(job.get("experience") or "").strip()
    if value:
        return value
    if parse_experience_years(job) is not None:
        years = parse_experience_years(job)
        return "经验不限" if years == 0 else f"{years}年以上"
    return "列表页未提供"


def infer_degree_display(job: dict) -> str:
    value = str(job.get("degree") or "").strip()
    if value:
        return value
    level = parse_degree_level(job)
    if level is None:
        return "列表页未提供"
    for name, current_level in DEGREE_LEVELS.items():
        if current_level == level:
            return name
    return "列表页未提供"


def infer_weekend_display(job: dict) -> str:
    policy = infer_weekend_policy(job)
    return "列表页未提供" if policy == "未知" else policy
