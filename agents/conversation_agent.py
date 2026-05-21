"""Local Q&A Agent for explaining a CareerPilot search result."""

from __future__ import annotations

from typing import Any

from memory.store import load_agent_run, load_agent_runs
from platform_registry import platform_label


def answer_agent_question(question: str, context: dict[str, Any] | None = None) -> str:
    """Answer a question using only local Agent search context."""
    question = str(question or "").strip()
    context = _normalize_context(context or _latest_context())
    if not question:
        return "你可以问我：为什么结果少、优先投哪个、哪些平台贡献最多、双休为什么缺、下一步怎么做。"
    if not context:
        return "我还没有可解释的 Agent 搜索结果。先运行一次 Agent 搜索后，我就能基于那次结果回答。"

    q = question.lower()
    if any(token in q for token in ("结果少", "结果这么少", "太少", "为什么少", "岗位少", "没结果", "没有结果")):
        return _answer_low_results(context)
    if any(token in q for token in ("平台", "来源", "哪个网站", "网站贡献")):
        return _answer_platforms(context)
    if any(token in q for token in ("双休", "周末", "大小周", "单休")):
        return _answer_weekend(context)
    if any(token in q for token in ("优先", "先投", "投哪个", "最值得", "推荐哪个", "top")):
        return _answer_priority(context)
    if any(token in q for token in ("简历", "优化", "怎么改", "修改")):
        return _answer_resume_actions(context)
    if any(token in q for token in ("面试", "准备", "问题")):
        return _answer_interview(context)
    if any(token in q for token in ("风险", "不建议", "避开", "外包", "培训")):
        return _answer_risks(context)
    if any(token in q for token in ("下一步", "怎么办", "行动", "计划")):
        return _answer_next_steps(context)
    if any(token in q for token in ("为什么", "解释", "总结")):
        return _answer_summary(context)
    return _answer_summary(context)


def _latest_context() -> dict[str, Any]:
    runs = load_agent_runs(limit=1)
    return runs[0] if runs else {}


def _normalize_context(context: dict[str, Any]) -> dict[str, Any]:
    if context.get("run_id") and not context.get("jobs") and not context.get("summary"):
        return context
    if context.get("run_id") and context.get("run_record"):
        return _from_result_context(context)
    if context.get("plan") or context.get("jobs") or context.get("summary"):
        return _from_result_context(context)
    run_id = context.get("run_id")
    if run_id:
        return load_agent_run(run_id)
    return context


def _from_result_context(result: dict[str, Any]) -> dict[str, Any]:
    jobs = result.get("jobs") or []
    summary = result.get("summary") or {}
    run_record = result.get("run_record") or {}
    plan = result.get("plan") or run_record.get("plan") or {}
    return {
        "run_id": result.get("run_id") or run_record.get("run_id", ""),
        "goal_text": plan.get("goal_text") or run_record.get("goal_text", ""),
        "status": run_record.get("status", "completed" if jobs else ""),
        "plan": plan,
        "job_count": len(jobs) or run_record.get("job_count", 0),
        "decision_counts": _decision_counts(jobs) or run_record.get("decision_counts", {}),
        "platform_counts": summary.get("search_final_platform_counts") or run_record.get("platform_counts", {}),
        "search_keywords": summary.get("search_keywords") or plan.get("expanded_keywords") or run_record.get("search_keywords", []),
        "raw_total": summary.get("search_raw_total", run_record.get("raw_total", 0)),
        "filtered_total": summary.get("search_filtered_total", run_record.get("filtered_total", 0)),
        "final_total": summary.get("search_final_total", len(jobs) or run_record.get("final_total", 0)),
        "field_counts": summary.get("search_field_counts") or {},
        "type_counts": summary.get("search_type_counts") or {},
        "detail_counts": summary.get("search_detail_counts") or {},
        "top_job": _top_job_summary(jobs) or run_record.get("top_job", {}),
        "top_jobs": _top_jobs_summary(jobs) or run_record.get("top_jobs", []),
        "steps": run_record.get("steps", []),
        "report_path": result.get("report_path") or run_record.get("report_path", ""),
        "next_actions": result.get("next_actions") or [],
    }


def _answer_summary(context: dict[str, Any]) -> str:
    plan = context.get("plan") or {}
    parts = [
        f"这次任务目标是：{context.get('goal_text') or plan.get('goal_text') or '未记录'}。",
        f"Agent 使用关键词：{_join(context.get('search_keywords')) or _join(plan.get('expanded_keywords'))}。",
        f"原始候选 {context.get('raw_total', 0)} 个，筛选后展示 {context.get('final_total', context.get('job_count', 0))} 个。",
    ]
    if context.get("decision_counts"):
        parts.append(f"推荐分布：{_dict_text(context.get('decision_counts'))}。")
    if context.get("top_job"):
        top = context["top_job"]
        parts.append(f"当前最优先看：{top.get('company', '')} - {top.get('title', '')}，{top.get('level', '')} {top.get('score', '')} 分。")
    return "\n\n".join(parts)


def _answer_low_results(context: dict[str, Any]) -> str:
    plan = context.get("plan") or {}
    criteria = plan.get("criteria") or {}
    type_counts = context.get("type_counts") or {}
    reasons = [
        f"原始候选有 {context.get('raw_total', 0)} 个，最后展示 {context.get('final_total', context.get('job_count', 0))} 个，主要是筛选条件叠加后变窄了。",
    ]
    if criteria.get("job_types") == ["社招"] or plan.get("job_types") == ["社招"]:
        reasons.append("当前只保留社招/全职，会排除实习和校招。")
    elif set(criteria.get("job_types") or plan.get("job_types") or []) == {"社招", "校招"}:
        reasons.append("当前保留社招和校招，但会排除实习岗位。")
    if type_counts:
        reasons.append(f"这次原始类型分布是：{_dict_text(type_counts)}。")
    if criteria.get("min_salary_k"):
        reasons.append(f"薪资下限设为 {criteria.get('min_salary_k')}K，低于预期的岗位会被过滤或降权。")
    if criteria.get("max_salary_k"):
        reasons.append(f"薪资上限设为 {criteria.get('max_salary_k')}K，高于预期的岗位会被过滤。")
    elif criteria.get("salary_preferred_max_k") is not None:
        reasons.append(f"薪资偏好设为 {criteria.get('salary_preferred_max_k')}K 以下，它只影响排序和风险提示，不会硬砍候选。")
    if criteria.get("max_experience_years") is not None:
        reasons.append(f"经验上限设为 {criteria.get('max_experience_years')} 年以内，经验门槛高的岗位会被过滤或标风险。")
    elif criteria.get("experience_preferred_max_years") is not None:
        reasons.append(f"毕业时间推断出偏好 {criteria.get('experience_preferred_max_years')} 年以内岗位，但它只影响排序和风险提示，不会单独清空候选。")
    if criteria.get("weekend_only"):
        reasons.append("当前写成了明确双休硬条件，公开工作制不匹配的岗位会被过滤。")
    elif criteria.get("weekend_preferred"):
        reasons.append("“双休优先”只影响排序和风险提示，不会单独清空候选。")
    reasons.append("想增加结果量，可以先把页数调到 2-3，再放宽薪资或明确写出的硬筛选；当前仍建议保留“不要实习”。")
    return "\n\n".join(reasons)


def _answer_platforms(context: dict[str, Any]) -> str:
    platform_counts = context.get("platform_counts") or {}
    if not platform_counts:
        return "这次没有可用的平台分布记录。建议重新运行一次 Agent 搜索，它会记录每个平台抓取、筛选和最终展示数量。"
    best = max(platform_counts.items(), key=lambda item: item[1])
    readable_counts = {platform_label(key): value for key, value in platform_counts.items()}
    return (
        f"最终结果的平台分布是：{_dict_text(readable_counts)}。\n\n"
        f"这次贡献最多的是 {platform_label(best[0])}，最终留下 {best[1]} 个岗位。平台越多不一定展示越多，因为最终表格会继续按社招、薪资、经验、双休、去重和推荐排序筛选。"
    )


def _answer_weekend(context: dict[str, Any]) -> str:
    fields = context.get("field_counts") or {}
    welfare = fields.get("welfare") or {}
    filled = welfare.get("filled")
    missing = welfare.get("missing")
    if filled is not None and missing is not None:
        return (
            f"这次福利/双休字段完整度是 {filled}/{filled + missing}。\n\n"
            "双休拿不到通常不是算法故意漏掉，而是平台列表页不公开，详情页又可能需要登录、滑块或反爬验证。CareerPilot 现在会把未知保留下来并标注风险，不会编造“双休”。"
        )
    return "双休字段只有部分平台会公开。当前策略是：公开双休就加分，未知双休保留但提示，不会凭空补全。"


def _answer_priority(context: dict[str, Any]) -> str:
    jobs = context.get("top_jobs") or []
    if not jobs and context.get("top_job"):
        jobs = [context["top_job"]]
    if not jobs:
        return "这次没有岗位可排序。先放宽条件重新搜索，我再帮你排优先级。"

    lines = ["建议先看这几个："]
    for index, job in enumerate(jobs[:3], 1):
        reasons = _join(job.get("matched_reasons")) or "基础条件较匹配"
        risks = _join(job.get("risks")) or "暂无明显风险"
        lines.append(
            f"{index}. {job.get('company', '')} - {job.get('title', '')}："
            f"{job.get('level', '')} {job.get('score', '')} 分，薪资 {job.get('salary', '')}。"
            f"理由：{reasons}。风险：{risks}。"
        )
    return "\n\n".join(lines)


def _answer_resume_actions(context: dict[str, Any]) -> str:
    jobs = context.get("top_jobs") or []
    actions: list[str] = []
    for job in jobs[:5]:
        actions.extend(job.get("resume_actions") or [])
    actions = _unique(actions)[:6]
    if not actions:
        return "当前结果里没有足够的简历动作记录。上传简历后重新跑 Agent 搜索，会生成更精准的简历优化方向。"
    return "简历优先这样改：\n\n" + "\n".join(f"- {item}" for item in actions)


def _answer_interview(context: dict[str, Any]) -> str:
    jobs = context.get("top_jobs") or []
    focus: list[str] = []
    for job in jobs[:5]:
        focus.extend(job.get("interview_focus") or [])
    focus = _unique(focus)[:8]
    if not focus:
        return "当前没有足够的面试准备记录。选择一个岗位后，可以生成更细的本地行动建议或 DeepSeek 精评建议。"
    return "面试先准备这些：\n\n" + "\n".join(f"- {item}" for item in focus)


def _answer_risks(context: dict[str, Any]) -> str:
    jobs = context.get("top_jobs") or []
    risks: list[str] = []
    for job in jobs:
        for risk in job.get("risks") or []:
            risks.append(f"{job.get('company', '')} - {job.get('title', '')}：{risk}")
    risks = _unique(risks)[:8]
    if not risks:
        return "Top 岗位暂时没有明显风险。不过仍建议打开原岗位页人工确认公司、薪资、工作制和岗位真实性。"
    return "当前主要风险是：\n\n" + "\n".join(f"- {item}" for item in risks)


def _answer_next_steps(context: dict[str, Any]) -> str:
    actions = context.get("next_actions") or []
    if actions:
        return "下一步建议：\n\n" + "\n".join(f"- {item}" for item in actions)
    if context.get("job_count", 0):
        return "下一步建议：\n\n- 先打开 Top 3 岗位确认真实性和工作制。\n- 选择最想投的岗位生成简历优化和面试建议。\n- 把不合适原因保存到求职记忆，下一轮 Agent 会自动参考。"
    return "下一步建议：\n\n- 放宽筛选条件重新检索。\n- 增加页数或扩展关键词。\n- 上传简历后再做精准排序。"


def _decision_counts(jobs: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for job in jobs:
        level = (job.get("job_decision") or {}).get("level", "未评估")
        counts[level] = counts.get(level, 0) + 1
    return counts


def _top_job_summary(jobs: list[dict[str, Any]]) -> dict[str, Any]:
    return _top_jobs_summary(jobs, limit=1)[0] if jobs else {}


def _top_jobs_summary(jobs: list[dict[str, Any]], limit: int = 10) -> list[dict[str, Any]]:
    rows = []
    for job in jobs[:limit]:
        decision = job.get("job_decision") or {}
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
            "matched_reasons": decision.get("matched_reasons", [])[:3],
            "risks": decision.get("risks", [])[:3],
            "resume_actions": decision.get("resume_actions", [])[:3],
            "interview_focus": decision.get("interview_focus", [])[:3],
        })
    return rows


def _dict_text(value: dict[str, Any]) -> str:
    return "，".join(f"{key} {count}" for key, count in value.items()) or "无"


def _join(value: Any) -> str:
    if not value:
        return ""
    if isinstance(value, (list, tuple, set)):
        return "；".join(str(item).strip() for item in value if str(item).strip())
    return str(value).strip()


def _unique(items: list[str]) -> list[str]:
    result = []
    for item in items:
        value = str(item or "").strip()
        if value and value not in result:
            result.append(value)
    return result

