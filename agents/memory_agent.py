"""Memory Agent: summarize local user preferences and job history."""

from __future__ import annotations

from collections import Counter

from memory.store import load_application_records, load_job_feedback, load_profile

NEGATIVE_TERMS = ("外包", "培训", "销售", "薪资低", "经验高", "学历高", "不双休", "单休", "大小周")


def build_memory_context() -> dict:
    """Build a compact context object for planning and ranking."""
    profile = load_profile()
    feedback = load_job_feedback()
    applications = load_application_records()

    negative_terms = _extract_negative_terms(feedback)
    disliked_companies = _companies_by_status(feedback, {"不合适", "已拒绝"})
    interested_companies = _companies_by_status([*feedback, *applications], {"感兴趣", "已投递", "已沟通", "面试中"})
    application_status_counts = Counter(str(item.get("status") or "未知") for item in applications)

    return {
        "profile": profile,
        "negative_terms": negative_terms,
        "disliked_companies": disliked_companies,
        "interested_companies": interested_companies,
        "application_status_counts": dict(application_status_counts),
        "feedback_count": len(feedback),
        "application_count": len(applications),
        "summary": summarize_memory(profile, negative_terms, interested_companies, disliked_companies, application_status_counts),
    }


def summarize_memory(
    profile: dict | None = None,
    negative_terms: list[str] | None = None,
    interested_companies: list[str] | None = None,
    disliked_companies: list[str] | None = None,
    application_status_counts: Counter | dict | None = None,
) -> str:
    profile = profile or load_profile()
    negative_terms = negative_terms or []
    interested_companies = interested_companies or []
    disliked_companies = disliked_companies or []
    application_status_counts = application_status_counts or {}

    target = "、".join((profile.get("target_roles") or [])[:3]) if profile else ""
    skills = "、".join((profile.get("skills") or [])[:6]) if profile else ""
    parts = []
    if target or skills:
        parts.append(f"当前画像：{target or '未明确方向'}；核心技能：{skills or '未提取'}")
    else:
        parts.append("当前还没有稳定简历画像")

    if negative_terms:
        parts.append(f"负反馈偏好：尽量避开 {'、'.join(negative_terms[:8])}")
    if disliked_companies:
        parts.append(f"已标记不合适公司：{'、'.join(disliked_companies[:5])}")
    if interested_companies:
        parts.append(f"近期感兴趣/投递公司：{'、'.join(interested_companies[:5])}")
    if application_status_counts:
        parts.append(f"投递状态统计：{dict(application_status_counts)}")
    return "；".join(parts)


def _extract_negative_terms(feedback: list[dict]) -> list[str]:
    found = []
    for item in feedback[-200:]:
        if str(item.get("status") or "") not in {"不合适", "已拒绝"}:
            continue
        note = str(item.get("note") or "")
        title = str(item.get("title") or "")
        text = f"{note} {title}"
        for term in NEGATIVE_TERMS:
            if term in text and term not in found:
                found.append(term)
    return found


def _companies_by_status(records: list[dict], statuses: set[str]) -> list[str]:
    companies = []
    for item in records[-200:]:
        if str(item.get("status") or "") not in statuses:
            continue
        company = str(item.get("company") or "").strip()
        if company and company not in companies:
            companies.append(company)
    return companies
