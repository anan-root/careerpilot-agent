"""Local job decision Agent for explainable recommendations."""

from __future__ import annotations

from job_filters import DEGREE_LEVELS, enrich_job_fields
from memory.store import load_job_feedback


def rank_jobs_with_decisions(jobs: list[dict], profile: dict | None, plan: dict | None = None) -> list[dict]:
    """Attach a JobDecision to each job and sort by decision score."""
    profile = profile or {}
    plan = plan or {}
    memory_context = dict(profile.get("_memory_context") or {})
    feedback = load_job_feedback()
    ranked = []
    for job in jobs:
        enriched = enrich_job_fields(dict(job))
        decision = decide_job(enriched, profile, plan, feedback, memory_context)
        enriched["job_decision"] = decision
        ranked.append(enriched)
    ranked.sort(key=lambda item: item.get("job_decision", {}).get("score", 0), reverse=True)
    return ranked


def decide_job(
    job: dict,
    profile: dict | None,
    plan: dict | None = None,
    feedback: list[dict] | None = None,
    memory_context: dict | None = None,
) -> dict:
    job = enrich_job_fields(dict(job))
    profile = profile or {}
    plan = plan or {}
    feedback = feedback or []
    memory_context = memory_context or {}
    criteria = plan.get("criteria") or {}
    excluded_terms = plan.get("excluded_terms") or []

    score = 38.0
    matched_reasons: list[str] = []
    missing_requirements: list[str] = []
    risks: list[str] = []
    resume_actions: list[str] = []
    interview_focus: list[str] = []

    job_text = _job_text(job)
    profile_skills = [str(skill) for skill in profile.get("skills", [])]
    project_keywords = _project_keywords(profile)
    matched_skills = [skill for skill in profile_skills if skill and skill.lower() in job_text.lower()]
    matched_projects = [kw for kw in project_keywords if kw and kw.lower() in job_text.lower()]

    if matched_skills:
        score += min(20, len(matched_skills) * 3.5)
        matched_reasons.append(f"技能命中：{', '.join(matched_skills[:8])}")
    elif profile_skills:
        score -= 8
        missing_requirements.append("岗位文本和简历技能暂未形成明显重合")

    if matched_projects:
        score += min(12, len(matched_projects) * 2.5)
        matched_reasons.append(f"项目关键词相关：{', '.join(matched_projects[:6])}")
    elif profile.get("projects"):
        resume_actions.append("在简历项目描述里补充岗位关键词对应的真实证据")

    title_score = _title_alignment(job, profile, plan)
    score += title_score
    if title_score > 8:
        matched_reasons.append("岗位方向与目标方向接近")

    score += _salary_adjustment(job, criteria, risks)
    score += _experience_adjustment(job, profile, criteria, risks)
    score += _degree_adjustment(job, profile, criteria, risks)
    score += _weekend_adjustment(job, criteria, risks)
    score += _excluded_term_adjustment(job, excluded_terms, risks)
    score += _field_completeness_adjustment(job, risks)
    score += _memory_feedback_adjustment(job, feedback, risks)
    score += _memory_context_adjustment(job, memory_context, risks)
    score = _apply_confidence_cap(score, profile, matched_skills, matched_projects, risks)

    if not matched_reasons:
        matched_reasons.append("目前主要基于岗位基础条件进入候选列表，建议上传或完善简历画像后再精排")

    if not resume_actions:
        resume_actions.extend(_resume_actions_from_missing(job, matched_skills))
    interview_focus.extend(_interview_focus(job, matched_skills))

    score = round(max(0.0, min(100.0, score)), 1)
    return {
        "score": score,
        "level": _level(score, risks),
        "matched_reasons": matched_reasons[:5],
        "missing_requirements": missing_requirements[:5],
        "risks": risks[:6],
        "resume_actions": resume_actions[:5],
        "interview_focus": interview_focus[:6],
    }


def _salary_adjustment(job: dict, criteria: dict, risks: list[str]) -> float:
    min_expected = criteria.get("min_salary_k")
    preferred_max = criteria.get("salary_preferred_max_k")
    salary_min = job.get("salary_min_k")
    salary_max = job.get("salary_max_k")
    if min_expected is None:
        if preferred_max is None:
            return 0
        if salary_max is None:
            risks.append("薪资可解析范围不足")
            return -1
        if salary_min is not None and salary_min > float(preferred_max):
            risks.append("薪资高于当前偏好")
            return -8
        if salary_max is not None and salary_max <= float(preferred_max):
            return 4
        return 1
    if salary_max is None:
        risks.append("薪资可解析范围不足")
        return -2
    if salary_max < float(min_expected):
        risks.append("薪资上限低于预期")
        return -18
    if salary_min is not None and salary_min >= float(min_expected):
        return 7
    return 2


def _experience_adjustment(job: dict, profile: dict, criteria: dict, risks: list[str]) -> float:
    job_exp = job.get("experience_years_min")
    max_expected = criteria.get("max_experience_years")
    preferred_max = criteria.get("experience_preferred_max_years")
    user_exp = profile.get("experience_years")
    if max_expected is not None and job_exp is not None and job_exp > int(max_expected):
        risks.append(f"经验要求可能偏高：{job.get('experience_display', job_exp)}")
        return -16
    if preferred_max is not None and job_exp is not None and job_exp > int(preferred_max):
        risks.append(f"经验要求高于当前偏好：{job.get('experience_display', job_exp)}")
        return -10
    if user_exp is not None and job_exp is not None and job_exp > int(user_exp) + 1:
        risks.append("岗位经验门槛可能高于简历经历")
        return -10
    if job_exp == 0:
        return 3
    if job_exp is None:
        risks.append("经验要求未公开")
        return -1
    return 4


def _degree_adjustment(job: dict, profile: dict, criteria: dict, risks: list[str]) -> float:
    required_level = job.get("degree_level")
    if required_level is None:
        risks.append("学历要求未公开")
        return -1

    allowed = criteria.get("degrees") or []
    allowed_levels = [DEGREE_LEVELS[item] for item in allowed if item in DEGREE_LEVELS]
    if allowed_levels and required_level > max(allowed_levels):
        risks.append(f"学历要求可能超过设定范围：{job.get('degree_display', '')}")
        return -14
    return 3


def _weekend_adjustment(job: dict, criteria: dict, risks: list[str]) -> float:
    weekend_only = bool(criteria.get("weekend_only"))
    weekend_preferred = bool(criteria.get("weekend_preferred") or weekend_only)
    if not weekend_preferred:
        return 0
    policy = job.get("weekend_policy")
    if policy == "双休":
        return 6
    if policy == "未知":
        risks.append("双休信息未公开")
        return -3 if weekend_only else -1
    risks.append(f"工作制风险：{policy}")
    return -8 if weekend_only else -4


def _excluded_term_adjustment(job: dict, excluded_terms: list[str], risks: list[str]) -> float:
    text = _job_text(job)
    penalty = 0.0
    for term in excluded_terms:
        if term and term in text:
            risks.append(f"命中排除词：{term}")
            penalty -= 20
    for term in ("外包", "培训", "销售"):
        if term in text and f"命中排除词：{term}" not in risks:
            risks.append(f"可能存在{term}相关风险")
            penalty -= 8
    return penalty


def _field_completeness_adjustment(job: dict, risks: list[str]) -> float:
    score = 0.0
    for key, label in (("experience", "经验"), ("degree", "学历"), ("salary", "薪资"), ("company_address", "地址")):
        if job.get(key):
            score += 1.5
        else:
            risks.append(f"{label}字段缺失")
            score -= 1.5
    return score


def _apply_confidence_cap(
    score: float,
    profile: dict,
    matched_skills: list[str],
    matched_projects: list[str],
    risks: list[str],
) -> float:
    if not profile:
        return min(score, 76)
    if not profile.get("projects") and len(matched_skills) < 4:
        risks.append("简历项目证据不足，暂不判为强推")
        return min(score, 78)
    if matched_projects and len(matched_skills) >= 4:
        return min(score, 96)
    if len(matched_skills) >= 3:
        return min(score, 88)
    return min(score, 82)


def _memory_feedback_adjustment(job: dict, feedback: list[dict], risks: list[str]) -> float:
    if not feedback:
        return 0.0
    text = _job_text(job)
    company = str(job.get("company") or "")
    adjustment = 0.0
    for item in feedback[-80:]:
        note = str(item.get("note") or "")
        status = str(item.get("status") or "")
        fb_company = str(item.get("company") or "")
        if status == "不合适":
            if fb_company and fb_company == company:
                risks.append("你曾标记该公司岗位不合适")
                adjustment -= 14
            for term in ("外包", "培训", "销售", "薪资低", "经验高"):
                if term in note and term in text:
                    risks.append(f"命中过往负反馈：{term}")
                    adjustment -= 6
        elif status in {"感兴趣", "已投递", "已沟通", "面试中"} and fb_company and fb_company == company:
            adjustment += 4
    return adjustment


def _memory_context_adjustment(job: dict, memory_context: dict, risks: list[str]) -> float:
    if not memory_context:
        return 0.0
    text = _job_text(job)
    company = str(job.get("company") or "")
    adjustment = 0.0
    if company and company in set(memory_context.get("disliked_companies") or []):
        risks.append("记忆中该公司曾被标记不合适")
        adjustment -= 12
    if company and company in set(memory_context.get("interested_companies") or []):
        adjustment += 3
    for term in memory_context.get("negative_terms") or []:
        if term and term in text:
            risks.append(f"命中记忆避开项：{term}")
            adjustment -= 7
    return adjustment


def _title_alignment(job: dict, profile: dict, plan: dict) -> float:
    title = str(job.get("title") or "").lower()
    targets = [plan.get("keyword", ""), *(plan.get("expanded_keywords") or []), *(profile.get("target_roles") or [])]
    score = 0.0
    for target in targets:
        for token in _split_terms(str(target)):
            if token and token.lower() in title:
                score += 4
    return min(score, 14)


def _resume_actions_from_missing(job: dict, matched_skills: list[str]) -> list[str]:
    actions = []
    skills = str(job.get("skills") or "").replace(",", "、")
    if skills and not matched_skills:
        actions.append(f"检查简历是否能补充这些真实技能证据：{skills[:80]}")
    requirements = str(job.get("requirements") or job.get("description") or "")
    if requirements:
        actions.append("把岗位要求拆成关键词，补到最相关的项目经历中")
    actions.append("准备一个能证明岗位方向的项目故事，按背景-行动-结果组织")
    return actions


def _interview_focus(job: dict, matched_skills: list[str]) -> list[str]:
    focus = []
    for skill in matched_skills[:4]:
        focus.append(f"准备 {skill} 的项目追问")
    text = _job_text(job)
    for token in ("RAG", "Agent", "大模型", "LLM", "Prompt", "向量检索", "FastAPI", "React"):
        if token.lower() in text.lower() and not any(token in item for item in focus):
            focus.append(f"复盘 {token} 的原理和落地细节")
    return focus or ["准备岗位职责对应的项目细节和技术取舍"]


def _project_keywords(profile: dict) -> list[str]:
    keywords: list[str] = []
    for project in profile.get("projects", []):
        if isinstance(project, dict):
            keywords.extend(project.get("keywords") or [])
            if project.get("name"):
                keywords.append(project["name"])
    return _unique(keywords)


def _job_text(job: dict) -> str:
    keys = (
        "title", "company", "location", "salary", "job_type", "description",
        "requirements", "skills", "welfare", "company_industry", "full_jd",
    )
    return " ".join(str(job.get(key) or "") for key in keys)


def _split_terms(value: str) -> list[str]:
    return [item.strip() for item in value.replace("/", " ").replace("-", " ").replace("、", " ").split()]


def _level(score: float, risks: list[str]) -> str:
    serious = any("命中排除词" in risk or "薪资上限低于预期" in risk for risk in risks)
    if any("命中排除词" in risk for risk in risks):
        return "不建议"
    uncertainty = sum(1 for risk in risks if "未公开" in risk or "缺失" in risk or "不确定" in risk)
    if score >= 82 and not serious and uncertainty <= 1:
        return "强推"
    if score >= 64 and not serious:
        return "可投"
    if score >= 45:
        return "谨慎"
    return "不建议"


def _unique(items: list[str]) -> list[str]:
    result = []
    for item in items:
        value = str(item or "").strip()
        if value and value not in result:
            result.append(value)
    return result
