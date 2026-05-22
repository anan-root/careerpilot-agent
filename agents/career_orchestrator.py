"""Career Agent orchestration for goal-driven job search."""

from __future__ import annotations

from agents.memory_agent import build_memory_context
from agents.profile_agent import build_resume_profile
from agents.ranking_agent import rank_jobs_with_decisions
from agents.report_agent import build_agent_search_report
from agents.resume_matcher import rank_jobs_for_resume
from agents.search_strategy_agent import build_search_plan
from crawlers.aggregator import collect_all_jobs, get_last_search_summary
from memory.store import (
    add_agent_run_step,
    create_agent_run,
    fail_agent_run,
    finish_agent_run,
    load_profile,
    save_agent_run_report,
    save_search_history,
)
from platform_registry import platform_label, platform_label_text

DEFAULT_LLM_RERANK_TOP_N = 3


def run_agent_search(
    goal_text: str,
    resume_text: str | None = None,
    *,
    allow_browser_login: bool | None = None,
    progress_callback=None,
) -> dict:
    """Plan and execute a safe job search from a natural-language goal."""
    run = create_agent_run(goal_text, resume_present=bool(resume_text))
    run_id = run["run_id"]
    try:
        resume_profile = build_resume_profile(resume_text) if resume_text else load_profile()
        add_agent_run_step(
            run_id,
            "读取简历画像",
            detail="已从上传简历生成画像" if resume_text else "已读取本地画像或空画像",
        )
        _emit_progress(progress_callback, "已读取简历画像")

        memory_context = build_memory_context()
        add_agent_run_step(run_id, "读取求职记忆", detail=memory_context.get("summary", "暂无记忆"))
        _emit_progress(progress_callback, "已读取求职记忆")
        if resume_profile:
            resume_profile = {**resume_profile, "_memory_context": memory_context}
        plan = build_search_plan(goal_text, resume_profile)
        if allow_browser_login is not None:
            plan_safety = dict(plan.get("safety") or {})
            plan_safety["allow_browser_login"] = bool(allow_browser_login)
            plan["safety"] = plan_safety
        add_agent_run_step(
            run_id,
            "制定搜索计划",
            detail=f"{plan.get('location', '上海')} / {plan.get('keyword', '')} / {platform_label_text(plan.get('platforms'))}",
        )
        _emit_progress(
            progress_callback,
            f"搜索计划：{plan.get('location', '上海')} / {plan.get('keyword', '')} / {platform_label_text(plan.get('platforms'))}",
        )

        criteria = dict(plan.get("criteria") or {})
        safety = dict(plan.get("safety") or {})
        expanded_keywords = plan.get("expanded_keywords") or [plan.get("keyword", "AI Agent")]

        jobs = collect_all_jobs(
            plan.get("keyword", "AI Agent"),
            plan.get("location", "上海"),
            platforms=plan.get("platforms"),
            max_pages=int(plan.get("max_pages") or 1),
            criteria=criteria,
            expand_keywords=True,
            max_keywords=len(expanded_keywords),
            search_keywords=expanded_keywords,
            enrich_details=False,
            detail_limit=0,
            use_browser_crawlers=bool(safety.get("use_browser_crawlers", False)),
            allow_browser_login=bool(safety.get("allow_browser_login", False)),
            progress_callback=progress_callback,
        )
        summary = get_last_search_summary()
        add_agent_run_step(
            run_id,
            "执行多平台检索",
            detail=f"原始候选 {summary.get('search_raw_total', len(jobs))}，筛选后 {summary.get('search_final_total', len(jobs))}",
        )

        if resume_text and jobs:
            ai_top_n = min(DEFAULT_LLM_RERANK_TOP_N, len(jobs))
            jobs = rank_jobs_for_resume(
                resume_text,
                jobs,
                top_n=None,
                ai_top_n=ai_top_n,
                progress_callback=progress_callback,
                resume_cache_key=_resume_cache_key(resume_text),
            )
            ai_success = _ai_match_success_count(jobs)
            summary["llm_rerank_requested"] = ai_top_n
            summary["llm_rerank_success"] = ai_success
            add_agent_run_step(
                run_id,
                "DeepSeek 简历精排",
                detail=f"本地初筛 {len(jobs)} 个岗位，DeepSeek 精排前 {ai_top_n} 个，成功 {ai_success} 个",
            )
            _emit_progress(progress_callback, f"DeepSeek 精排完成：请求 {ai_top_n} 个，成功 {ai_success} 个")
        jobs = rank_jobs_with_decisions(jobs, resume_profile, plan)
        add_agent_run_step(run_id, "岗位决策排序", detail=f"已生成 {len(jobs)} 个岗位推荐判断")
        _emit_progress(progress_callback, f"岗位决策排序完成：{len(jobs)} 个岗位")
        summary["recommendation_level_counts"] = _decision_counts(jobs)

        save_search_history(goal_text, plan, summary)
        result = {
            "run_id": run_id,
            "plan": plan,
            "jobs": jobs,
            "summary": summary,
            "resume_profile": resume_profile,
            "memory_context": memory_context,
            "agent_message": build_agent_message(plan, summary, jobs, has_resume=bool(resume_profile)),
            "next_actions": build_next_actions(jobs, has_resume=bool(resume_profile)),
        }
        result["report"] = build_agent_search_report(result)
        report_path = save_agent_run_report(run_id, result["report"])
        result["report_path"] = str(report_path)
        result["run_record"] = finish_agent_run(run_id, result, report_path=str(report_path))
        return result
    except Exception as exc:
        fail_agent_run(run_id, str(exc))
        raise


def build_agent_message(plan: dict, summary: dict, jobs: list[dict], *, has_resume: bool = False) -> str:
    """Create a concise Chinese explanation for the completed search."""
    keywords = ", ".join(summary.get("search_keywords") or plan.get("expanded_keywords") or [])
    platforms = platform_label_text(plan.get("platforms"))
    raw_total = summary.get("search_raw_total", len(jobs))
    final_total = summary.get("search_final_total", len(jobs))
    type_counts = summary.get("search_type_counts", {})
    final_counts = summary.get("search_final_platform_counts", {})
    field_counts = summary.get("search_field_counts", {})
    llm_requested = int(summary.get("llm_rerank_requested", 0) or 0)
    llm_success = int(summary.get("llm_rerank_success", 0) or 0)
    memory_summary = (plan.get("_memory_summary") or "").strip()

    parts = [
        f"我按「{plan.get('location', '上海')} / {plan.get('keyword', '')} / {', '.join(plan.get('job_types', []))}」制定了搜索计划。",
        f"本次使用平台：{platforms or '默认平台'}；实际关键词：{keywords or plan.get('keyword', '')}。",
        f"原始候选 {raw_total} 个，按条件筛选后展示 {final_total} 个。",
    ]

    if final_counts:
        readable_counts = {platform_label(key): value for key, value in final_counts.items()}
        parts.append(f"最终平台分布：{readable_counts}。")
    if type_counts:
        parts.append(f"原始岗位类型分布：{type_counts}。")
    if field_counts:
        readable_fields = _format_field_counts(field_counts)
        parts.append(f"字段完整度：{readable_fields}。")
    if has_resume and llm_requested:
        parts.append(f"DeepSeek 简历精排：请求 {llm_requested} 个，成功 {llm_success} 个；失败岗位已自动保留本地规则评分。")

    notes = plan.get("notes") or []
    if notes:
        parts.append("注意：" + "；".join(notes))
    if "boss" in (plan.get("platforms") or []) and not bool((plan.get("safety") or {}).get("allow_browser_login", False)):
        parts.append("本次 Agent 路径没有启用 Boss 登录浏览器，所以 BOSS 结果可能偏少。")
    elif "boss" in (plan.get("platforms") or []) and bool((plan.get("safety") or {}).get("allow_browser_login", False)):
        parts.append("本次 Agent 路径已允许 Boss 登录浏览器；如需登录，系统会优先尝试弹窗登录。")
    if memory_summary:
        parts.append("记忆：" + memory_summary)

    if not jobs:
        parts.append("这次没有符合条件的岗位，优先放宽薪资或明确写出的硬筛选，再增加页数和关键词。")
    elif has_resume:
        decision_counts = _decision_counts(jobs)
        parts.append(f"我已经基于简历画像和岗位条件做了决策排序：{decision_counts}。下一步可以选择岗位生成简历优化和面试建议。")
    else:
        parts.append("上传简历后，我可以继续把这些岗位按你的真实经历重新排序。")

    return "\n\n".join(parts)


def build_next_actions(jobs: list[dict], *, has_resume: bool = False) -> list[str]:
    if not jobs:
        return [
            "放宽硬筛选后重新检索，例如先放宽薪资范围或明确写出的经验上限。",
            "增加关键词数量，尝试“大模型应用 / 智能体 / RAG / LLM / AI应用开发”。",
            "如需 Boss 真实数据，目标里写“允许 Boss 登录浏览器”，或改用左侧手动搜索并勾选授权。",
        ]

    actions = ["打开排名靠前的岗位，查看匹配理由和风险。"]
    if has_resume:
        actions.append("选择 1 个目标岗位，生成简历优化意见和面试建议。")
    else:
        actions.append("上传简历，让 Agent 按你的项目和技能重新排序。")
    actions.append("把不合适的岗位原因记录下来，后续可用于求职记忆。")
    return actions


def _format_field_counts(field_counts: dict) -> str:
    labels = {
        "experience": "经验",
        "degree": "学历",
        "welfare": "福利/双休",
        "company_address": "地址",
        "salary": "薪资",
    }
    items = []
    for key, label in labels.items():
        counts = field_counts.get(key) or {}
        filled = counts.get("filled", 0)
        missing = counts.get("missing", 0)
        total = filled + missing
        items.append(f"{label} {filled}/{total}")
    return "，".join(items)


def _decision_counts(jobs: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for job in jobs:
        level = job.get("job_decision", {}).get("level", "未评估")
        counts[level] = counts.get(level, 0) + 1
    return counts


def _ai_match_success_count(jobs: list[dict]) -> int:
    count = 0
    for job in jobs:
        match = job.get("ai_match") or (job.get("resume_match") or {}).get("ai") or {}
        if isinstance(match, dict) and isinstance(match.get("score"), (int, float)):
            count += 1
    return count


def _emit_progress(callback, message: str) -> None:
    if callback is None:
        return
    try:
        callback(message)
    except Exception:
        pass


def _resume_cache_key(resume_text: str) -> str:
    import hashlib

    return hashlib.sha1(str(resume_text or "").strip().encode("utf-8")).hexdigest()[:16]
