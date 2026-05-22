"""Markdown report generation for CareerPilot Agent search runs."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from platform_registry import platform_label, platform_label_text


def build_agent_search_report(result: dict[str, Any]) -> str:
    """Build a beginner-readable, action-oriented Markdown report."""
    plan = result.get("plan") or {}
    jobs = result.get("jobs") or []
    summary = result.get("summary") or {}
    memory_context = result.get("memory_context") or {}
    resume_profile = result.get("resume_profile") or {}
    next_actions = result.get("next_actions") or []
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines: list[str] = [
        "# CareerPilot Agent 搜索报告",
        "",
        f"- 生成时间：{generated_at}",
        f"- 求职目标：{_clean(plan.get('goal_text') or result.get('goal_text') or '未记录')}",
        f"- 城市：{_clean(plan.get('location') or '上海')}",
        f"- 主关键词：{_clean(plan.get('keyword') or '')}",
        f"- 岗位类型：{_join(plan.get('job_types')) or '未限制'}",
        f"- 使用平台：{platform_label_text(plan.get('platforms'))}",
        f"- 展示结果：{len(jobs)} 个",
        "",
    ]

    agent_message = result.get("agent_message")
    if agent_message:
        lines.extend(["## Agent 总结", "", _clean(agent_message), ""])

    lines.extend(_build_plan_section(plan, summary))
    lines.extend(_build_memory_section(memory_context, resume_profile))
    lines.extend(_build_search_quality_section(summary))
    lines.extend(_build_decision_overview_section(jobs))
    lines.extend(_build_top_jobs_section(jobs))
    lines.extend(_build_next_actions_section(next_actions, jobs))
    lines.extend(_build_safety_section(plan, summary))

    return "\n".join(lines).rstrip() + "\n"


def _build_plan_section(plan: dict[str, Any], summary: dict[str, Any]) -> list[str]:
    criteria = plan.get("criteria") or {}
    keywords = summary.get("search_keywords") or plan.get("expanded_keywords") or [plan.get("keyword")]
    excluded = plan.get("excluded_terms") or criteria.get("excluded_terms") or []
    lines = [
        "## 搜索计划",
        "",
        f"- 实际检索关键词：{_join(keywords)}",
        f"- 薪资要求：{_salary_text(criteria)}",
        f"- 经验要求：{_experience_text(criteria)}",
        f"- 学历范围：{_join(criteria.get('degrees')) or '未限制'}",
        f"- 双休偏好：{_weekend_text(criteria)}",
        f"- 排除词：{_join(excluded) or '无'}",
    ]
    notes = plan.get("notes") or []
    if notes:
        lines.append(f"- 计划备注：{'；'.join(_clean(note) for note in notes)}")
    lines.append("")
    return lines


def _build_memory_section(memory_context: dict[str, Any], resume_profile: dict[str, Any]) -> list[str]:
    lines = ["## 简历画像与求职记忆", ""]
    summary = memory_context.get("summary")
    if summary:
        lines.append(f"- 记忆摘要：{_clean(summary)}")
    else:
        lines.append("- 记忆摘要：暂无历史偏好记录。")

    if resume_profile:
        skills = resume_profile.get("skills") or []
        roles = resume_profile.get("target_roles") or []
        exp = resume_profile.get("experience_years")
        lines.extend([
            f"- 简历目标角色：{_join(roles) or '未提取'}",
            f"- 简历技能：{_join(skills[:12]) or '未提取'}",
            f"- 经验年限：{exp if exp is not None else '未提取'}",
        ])
    else:
        lines.append("- 简历画像：本次未上传简历，推荐主要基于岗位条件和本地记忆。")

    negative_terms = memory_context.get("negative_terms") or []
    disliked = memory_context.get("disliked_companies") or []
    interested = memory_context.get("interested_companies") or []
    if negative_terms:
        lines.append(f"- 历史避开项：{_join(negative_terms)}")
    if disliked:
        lines.append(f"- 曾标记不合适公司：{_join(disliked[:8])}")
    if interested:
        lines.append(f"- 曾感兴趣公司：{_join(interested[:8])}")
    lines.append("")
    return lines


def _build_search_quality_section(summary: dict[str, Any]) -> list[str]:
    lines = [
        "## 数据质量",
        "",
        f"- 原始候选：{summary.get('search_raw_total', 0)}",
        f"- 条件筛选后：{summary.get('search_filtered_total', 0)}",
        f"- 最终展示：{summary.get('search_final_total', 0)}",
    ]

    platform_fetch = summary.get("search_platform_fetch_counts") or {}
    platform_final = summary.get("search_final_platform_counts") or {}
    type_counts = summary.get("search_type_counts") or {}
    detail_counts = summary.get("search_detail_counts") or {}
    field_counts = summary.get("search_field_counts") or {}

    if platform_fetch:
        lines.append(f"- 平台抓取量：{_dict_text(platform_fetch)}")
    if platform_final:
        lines.append(f"- 最终平台分布：{_dict_text(platform_final)}")
    if type_counts:
        lines.append(f"- 原始岗位类型分布：{_dict_text(type_counts)}")
    if detail_counts:
        lines.append(f"- 二次抓取：{_dict_text(detail_counts)}")
    if field_counts:
        lines.append(f"- 字段完整度：{_field_counts_text(field_counts)}")

    lines.extend([
        "",
        "> 说明：招聘平台常会限制未登录访问，双休、公司地址、经验等字段如果页面未公开或详情页被验证拦截，就只能标记为未知，不能凭空补全。",
        "",
    ])
    return lines


def _build_decision_overview_section(jobs: list[dict[str, Any]]) -> list[str]:
    counts: dict[str, int] = {}
    for job in jobs:
        level = ((job.get("job_decision") or {}).get("level") or "未评估")
        counts[level] = counts.get(level, 0) + 1

    lines = ["## 推荐结论", ""]
    if not jobs:
        lines.extend([
            "- 当前没有岗位进入结果集。",
            "- 建议先放宽薪资或明确写出的硬筛选，再增加页数和关键词重新检索。",
            "",
        ])
        return lines

    lines.append(f"- 推荐等级分布：{_dict_text(counts)}")
    llm_requested = sum(1 for job in jobs if (job.get("resume_match") or {}).get("ai") or job.get("ai_match"))
    llm_success = sum(
        1
        for job in jobs
        if isinstance((job.get("ai_match") or (job.get("resume_match") or {}).get("ai") or {}).get("score"), (int, float))
    )
    if llm_requested:
        lines.append(f"- DeepSeek 简历精排：请求 {llm_requested} 个，成功 {llm_success} 个")
    top = jobs[0]
    top_decision = top.get("job_decision") or {}
    lines.append(
        f"- 当前最优先岗位：{_clean(top.get('company'))} / {_clean(top.get('title'))} / "
        f"{top_decision.get('level', '未评估')} {top_decision.get('score', '')} 分"
    )
    lines.append("")
    return lines


def _build_top_jobs_section(jobs: list[dict[str, Any]], limit: int = 10) -> list[str]:
    if not jobs:
        return []

    lines = [
        "## Top 岗位清单",
        "",
        "| # | 等级 | 分数 | 公司 | 岗位 | 薪资 | 经验 | 学历 | 来源 |",
        "|---|---|---:|---|---|---|---|---|---|",
    ]
    for index, job in enumerate(jobs[:limit], 1):
        decision = job.get("job_decision") or {}
        lines.append(
            "| {index} | {level} | {score} | {company} | {title} | {salary} | {experience} | {degree} | {platform} |".format(
                index=index,
                level=_md_cell(decision.get("level")),
                score=_md_cell(decision.get("score")),
                company=_md_cell(job.get("company")),
                title=_md_cell(job.get("title")),
                salary=_md_cell(job.get("salary")),
                experience=_md_cell(job.get("experience_display") or job.get("experience")),
                degree=_md_cell(job.get("degree_display") or job.get("degree")),
                platform=_md_cell(job.get("platform")),
            )
        )
    lines.append("")

    for index, job in enumerate(jobs[:limit], 1):
        decision = job.get("job_decision") or {}
        ai_match = job.get("ai_match") or (job.get("resume_match") or {}).get("ai") or {}
        matched_reasons = ai_match.get("matched_evidence") or decision.get("matched_reasons")
        risks = ai_match.get("risk_points") or ai_match.get("risks") or decision.get("risks")
        resume_actions = ai_match.get("resume_actions") or decision.get("resume_actions")
        interview_focus = ai_match.get("interview_focus") or decision.get("interview_focus")
        lines.extend([
            f"### {index}. {_clean(job.get('company'))} - {_clean(job.get('title'))}",
            "",
            f"- 推荐：{decision.get('level', '未评估')} / {decision.get('score', '')} 分",
            f"- 地点：{_clean(job.get('location'))}；地址：{_clean(job.get('company_address')) or '未知'}",
            f"- 工作制/福利：{_clean(job.get('weekend_display') or job.get('weekend_policy')) or '未知'}；{_clean(job.get('welfare')) or '无公开福利'}",
            f"- 匹配证据：{_join(matched_reasons) or '暂无'}",
            f"- 风险点：{_join(risks) or '暂无明显风险'}",
            f"- 简历动作：{_join(resume_actions) or '补充岗位关键词证据'}",
            f"- 面试准备：{_join(interview_focus) or '准备项目细节和岗位职责追问'}",
        ])
        url = job.get("source_url") or job.get("url")
        if url:
            lines.append(f"- 链接：{url}")
        lines.append("")
    return lines


def _build_next_actions_section(next_actions: list[str], jobs: list[dict[str, Any]]) -> list[str]:
    lines = ["## 下一步行动", ""]
    if next_actions:
        for action in next_actions:
            lines.append(f"- {_clean(action)}")
    elif jobs:
        lines.extend([
            "- 优先查看前 3 个岗位，确认职责、薪资和工作制。",
            "- 针对最想投的岗位生成简历优化意见和面试建议。",
            "- 把不合适原因记录到本地求职记忆，下一次搜索会自动避开。",
        ])
    else:
        lines.extend([
            "- 放宽筛选条件重新检索。",
            "- 增加同义关键词，例如 智能体、RAG、大模型应用、LLM 应用开发。",
        ])
    lines.append("")
    return lines


def _build_safety_section(plan: dict[str, Any], summary: dict[str, Any]) -> list[str]:
    safety = plan.get("safety") or {}
    lines = ["## 安全与限制", ""]
    if safety:
        lines.append(f"- 浏览器采集：{'开启' if safety.get('use_browser_crawlers') else '关闭'}")
        if safety.get("allow_browser_login"):
            lines.append("- Boss 登录浏览器：允许")
        else:
            lines.append("- Boss 登录浏览器：禁止；如需 BOSS 真实数据，请在目标里明确写“允许 Boss 登录浏览器”或手动勾选。")
    else:
        lines.append("- 浏览器采集：默认关闭")
        lines.append("- Boss 登录浏览器：默认禁止；如需 BOSS 真实数据，请显式授权。")
    if summary.get("search_detail_counts"):
        lines.append("- 二次抓取只用于补全公开详情页字段，遇到登录/滑块/验证会跳过。")
    lines.append("- 本报告是本地 Agent 的检索与决策记录，最终投递前仍建议打开原岗位页面人工确认。")
    lines.append("")
    return lines


def _salary_text(criteria: dict[str, Any]) -> str:
    min_salary = criteria.get("min_salary_k")
    max_salary = criteria.get("max_salary_k")
    preferred_max = criteria.get("salary_preferred_max_k")
    if min_salary and max_salary:
        return f"{min_salary}K-{max_salary}K"
    if min_salary:
        return f"{min_salary}K 以上"
    if max_salary:
        return f"{max_salary}K 以下"
    if preferred_max is not None:
        return f"偏好 {preferred_max}K 以下，仅排序提示"
    return "未限制"


def _experience_text(criteria: dict[str, Any]) -> str:
    max_years = criteria.get("max_experience_years")
    if max_years is not None:
        return f"{max_years} 年以内或未知保留"
    preferred_max = criteria.get("experience_preferred_max_years")
    if preferred_max is not None:
        return f"偏好 {preferred_max} 年以内，仅排序提示"
    return "未限制"


def _weekend_text(criteria: dict[str, Any]) -> str:
    if criteria.get("weekend_only"):
        return "只看公开双休/待确认工作制"
    if criteria.get("weekend_preferred"):
        return "优先双休，仅排序提示"
    return "未限制"


def _field_counts_text(field_counts: dict[str, Any]) -> str:
    labels = {
        "experience": "经验",
        "degree": "学历",
        "welfare": "福利/双休",
        "company_address": "地址",
        "salary": "薪资",
    }
    parts = []
    for key, label in labels.items():
        counts = field_counts.get(key) or {}
        filled = counts.get("filled", 0)
        missing = counts.get("missing", 0)
        total = filled + missing
        if total:
            parts.append(f"{label} {filled}/{total}")
    return "，".join(parts) if parts else "暂无统计"


def _dict_text(value: dict[str, Any]) -> str:
    return "，".join(f"{platform_label(_clean(k))} {v}" for k, v in value.items()) or "无"


def _join(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple, set)):
        return "、".join(_clean(item) for item in value if _clean(item))
    return _clean(value)


def _clean(value: Any) -> str:
    return str(value or "").replace("\n", " ").strip()


def _md_cell(value: Any) -> str:
    text = _clean(value)
    if not text:
        return ""
    return text.replace("|", "\\|")

