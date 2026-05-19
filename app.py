"""Streamlit UI for CareerPilot resume matching and job advice."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from datetime import datetime

import pandas as pd
import streamlit as st

import db
from agents.resume_matcher import (
    SUPPORTED_EXTENSIONS,
    build_match_report,
    extract_resume_text,
    generate_resume_job_advice,
    rank_jobs_for_resume,
)
from agents.advice_agent import build_local_job_advice
from agents.career_orchestrator import run_agent_search
from agents.conversation_agent import answer_agent_question
from agents.profile_agent import build_resume_profile
from agents.ranking_agent import rank_jobs_with_decisions
from crawlers.aggregator import collect_all_jobs, get_last_search_summary
from job_filters import filter_jobs
from llm_client import get_llm_config
from memory.store import export_memory_snapshot, load_agent_runs, save_application_record, save_job_feedback

OUTPUT_DIR = Path(__file__).parent / "data" / "outputs"


st.set_page_config(page_title="CareerPilot", page_icon="🎯", layout="wide")


@st.cache_data(show_spinner=False)
def load_jobs() -> list[dict]:
    return db.get_all_jobs_df()


def clear_search_outputs():
    for key in ("ranked_jobs", "advice", "advice_path"):
        st.session_state.pop(key, None)


def save_upload(uploaded_file) -> Path:
    suffix = Path(uploaded_file.name).suffix.lower()
    temp_dir = Path(tempfile.mkdtemp(prefix="CareerPilot_resume_"))
    path = temp_dir / uploaded_file.name
    path.write_bytes(uploaded_file.getbuffer())
    return path


def jobs_to_frame(jobs: list[dict]) -> pd.DataFrame:
    rows = []
    for job in jobs:
        match = job.get("resume_match", {})
        decision = job.get("job_decision", {})
        rows.append({
            "推荐等级": decision.get("level", ""),
            "推荐分": decision.get("score", ""),
            "匹配分": match.get("score", 0),
            "公司": job.get("company", ""),
            "岗位": job.get("title", ""),
            "地点": job.get("location", ""),
            "公司地址": job.get("company_address", ""),
            "薪资": job.get("salary", ""),
            "月薪范围K": _salary_range_text(job),
            "经验": job.get("experience_display") or job.get("experience", ""),
            "学历": job.get("degree_display") or job.get("degree", ""),
            "双休": job.get("weekend_display") or job.get("weekend_policy", ""),
            "福利": job.get("welfare", ""),
            "类型": job.get("normalized_job_type") or job.get("job_type", ""),
            "抓取": job.get("crawl_status", ""),
            "详情": job.get("detail_status", ""),
            "关键词": job.get("crawl_keyword", ""),
            "来源": job.get("platform", ""),
            "链接": job.get("source_url") or job.get("url", ""),
            "推荐理由": "；".join(decision.get("matched_reasons", [])[:3]),
            "风险": "；".join(decision.get("risks", [])[:3]),
            "命中关键词": ", ".join(match.get("matched_keywords", [])[:12]),
            "缺口关键词": ", ".join(match.get("missing_keywords", [])[:12]),
            "建议": match.get("summary", ""),
        })
    return pd.DataFrame(rows)


def search_jobs_to_frame(jobs: list[dict]) -> pd.DataFrame:
    rows = []
    for job in jobs:
        decision = job.get("job_decision", {})
        rows.append({
            "推荐等级": decision.get("level", ""),
            "推荐分": decision.get("score", ""),
            "公司": job.get("company", ""),
            "岗位": job.get("title", ""),
            "地点": job.get("location", ""),
            "公司地址": job.get("company_address", ""),
            "薪资": job.get("salary", ""),
            "月薪范围K": _salary_range_text(job),
            "经验": job.get("experience_display") or job.get("experience", ""),
            "学历": job.get("degree_display") or job.get("degree", ""),
            "双休": job.get("weekend_display") or job.get("weekend_policy", ""),
            "福利": job.get("welfare", ""),
            "类型": job.get("normalized_job_type") or job.get("job_type", ""),
            "抓取": job.get("crawl_status", ""),
            "详情": job.get("detail_status", ""),
            "关键词": job.get("crawl_keyword", ""),
            "来源": job.get("platform", ""),
            "推荐理由": "；".join(decision.get("matched_reasons", [])[:3]),
            "风险": "；".join(decision.get("risks", [])[:3]),
            "链接": job.get("source_url") or job.get("url", ""),
        })
    return pd.DataFrame(rows)


def render_job_cards(jobs: list[dict], limit: int = 20):
    for index, job in enumerate(jobs[:limit], 1):
        decision = job.get("job_decision", {})
        level = decision.get("level", "未评估")
        score = decision.get("score", "")
        title = job.get("title", "")
        company = job.get("company", "")
        platform = job.get("platform", "")
        salary = job.get("salary", "")
        location = job.get("location", "")
        address = job.get("company_address", "")
        experience = job.get("experience_display") or job.get("experience", "")
        degree = job.get("degree_display") or job.get("degree", "")
        weekend = job.get("weekend_display") or job.get("weekend_policy", "")
        welfare = job.get("welfare", "")
        reasons = decision.get("matched_reasons", [])[:3]
        risks = decision.get("risks", [])[:3]
        resume_actions = decision.get("resume_actions", [])[:2]
        url = job.get("source_url") or job.get("url", "")

        with st.container(border=True):
            top_cols = st.columns([4, 1, 1])
            with top_cols[0]:
                st.markdown(f"**{index}. {company} - {title}**")
                st.caption(f"{platform} / {location} / {address or '地址未知'}")
            with top_cols[1]:
                st.metric("推荐", level)
            with top_cols[2]:
                st.metric("分数", score)

            info_cols = st.columns(4)
            info_cols[0].write(f"薪资：{salary or '未知'}")
            info_cols[1].write(f"经验：{experience or '未知'}")
            info_cols[2].write(f"学历：{degree or '未知'}")
            info_cols[3].write(f"双休：{weekend or '未知'}")

            if welfare:
                st.caption(f"福利：{welfare}")
            if reasons:
                st.markdown("推荐理由：" + "；".join(reasons))
            if risks:
                st.warning("风险：" + "；".join(risks))
            if resume_actions:
                st.info("简历动作：" + "；".join(resume_actions))
            if url:
                st.link_button("打开岗位来源", url)


def _salary_range_text(job: dict) -> str:
    lo = job.get("salary_min_k")
    hi = job.get("salary_max_k")
    if lo is None and hi is None:
        return ""
    if lo == hi:
        return f"{lo:g}K"
    return f"{lo:g}-{hi:g}K"


def run_search(
    keyword,
    location,
    platforms,
    max_pages,
    criteria,
    signature,
    *,
    expand_keywords=True,
    max_keywords=4,
    enrich_details=True,
    detail_limit=20,
    use_browser_crawlers=False,
    allow_browser_login=False,
):
    jobs = collect_all_jobs(
        keyword,
        location,
        platforms=platforms,
        max_pages=int(max_pages),
        criteria=criteria,
        expand_keywords=expand_keywords,
        max_keywords=int(max_keywords),
        enrich_details=enrich_details,
        detail_limit=int(detail_limit),
        use_browser_crawlers=use_browser_crawlers,
        allow_browser_login=allow_browser_login,
    )
    st.session_state["current_jobs"] = jobs
    st.session_state["search_summary"] = get_last_search_summary()
    st.session_state["search_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    st.session_state["search_signature"] = signature
    st.session_state["last_search_label"] = (
        f"{location} / {keyword} / 平台:{', '.join(platforms or ['全部'])} / "
        f"页数:{int(max_pages)} / 类型:{', '.join(criteria.get('job_types') or ['全部'])}"
    )
    st.session_state["search_dirty"] = False
    clear_search_outputs()
    load_jobs.clear()
    return jobs


def main():
    st.title("职航 Agent 求职操作台")
    uploaded = None
    resume_text = ""
    resume_path = None

    with st.sidebar:
        st.subheader("配置")
        cfg = get_llm_config()
        st.caption(f"LLM: {cfg.get('provider', 'unknown')} / {cfg.get('model', 'unknown')}")

        st.subheader("简历")
        uploaded = st.file_uploader(
            "上传简历",
            type=[ext.lstrip(".") for ext in sorted(SUPPORTED_EXTENSIONS)],
        )

        st.subheader("岗位检索")
        keyword = st.text_input("搜索关键词", value="AI Agent")
        location = st.text_input("城市", value="上海")
        job_types = st.multiselect(
            "岗位类型",
            ["社招", "校招", "实习"],
            default=["社招"],
            help="默认只看社招/全职。需要校招或实习时再手动勾选。",
        )
        use_browser_crawlers = st.checkbox(
            "启用浏览器列表采集（51job/猎聘）",
            value=False,
            key="use_browser_crawlers_v2",
            help="默认关闭，避免自动启动 Edge/Chrome。开启后会用无登录浏览器模式补充 51job/猎聘列表页结果。",
        )
        allow_browser_login = st.checkbox(
            "允许打开 Boss 登录浏览器",
            value=False,
            key="allow_boss_browser_login_v2",
            help="默认关闭。只有勾选后，Boss DrissionPage 才可以打开浏览器并提示扫码登录。",
        )
        platform_options = ["nowcoder", "liepin", "zhilian", "51job", "boss", "curated"]
        if allow_browser_login:
            platform_options.insert(5, "boss_drission")
        platforms = st.multiselect(
            "平台",
            platform_options,
            default=["zhilian", "51job", "liepin"],
            key="platforms_safe_v2",
            help="默认不选择 Boss 登录浏览器。Boss 普通模式只尝试无浏览器方式，拿不到时使用兜底数据。",
        )
        if not allow_browser_login and "boss_drission" in platforms:
            platforms = [p for p in platforms if p != "boss_drission"]
            st.warning("已忽略 boss_drission：未勾选“允许打开 Boss 登录浏览器”。")
        max_pages = st.number_input("每个平台页数", min_value=1, max_value=10, value=1)
        expand_keywords = st.checkbox(
            "扩展关键词检索",
            value=True,
            help="例如 AI Agent 会同时搜索 大模型、AI应用、智能体 等中文常用词。",
        )
        max_keywords = st.number_input(
            "最多扩展关键词数",
            min_value=1,
            max_value=8,
            value=4,
            help="关键词越多结果越多，但搜索会更慢。",
        )
        enrich_details = st.checkbox(
            "二次抓取详情页",
            value=True,
            help="对部分岗位尝试进入详情页补全 JD、地址、福利、双休等字段。51job/猎聘详情页常有滑块或登录验证，失败会自动跳过。",
        )
        detail_limit = st.number_input(
            "详情抓取上限",
            min_value=0,
            max_value=100,
            value=20,
            help="建议先 20；太高容易慢或触发平台验证。",
        )
        min_salary_k, max_salary_k = st.slider(
            "月薪范围（K）",
            min_value=0,
            max_value=100,
            value=(0, 80),
            help="按月薪粗略过滤；日薪会按每月22天估算。",
        )
        max_experience_years = st.slider(
            "最高经验要求（年）",
            min_value=0,
            max_value=10,
            value=10,
            help="例如选择 3，会过滤掉明确要求 5 年经验的岗位；未知经验要求会保留。",
        )
        degrees = st.multiselect(
            "最高可接受学历要求",
            ["不限", "大专", "本科", "硕士", "博士"],
            default=["不限", "大专", "本科", "硕士", "博士"],
            help="例如不想看硕博岗，就取消硕士/博士。",
        )
        weekend_only = st.checkbox("优先只看双休/双休不确定", value=False)
        criteria = {
            "job_types": job_types,
            "min_salary_k": min_salary_k if min_salary_k > 0 else None,
            "max_salary_k": max_salary_k if max_salary_k < 100 else None,
            "max_experience_years": max_experience_years if max_experience_years < 10 else None,
            "degrees": degrees,
            "weekend_only": weekend_only,
        }
        search_signature = json.dumps({
            "keyword": keyword,
            "location": location,
            "job_types": job_types,
            "platforms": platforms,
            "max_pages": int(max_pages),
            "expand_keywords": expand_keywords,
            "max_keywords": int(max_keywords),
            "enrich_details": enrich_details,
            "detail_limit": int(detail_limit),
            "use_browser_crawlers": use_browser_crawlers,
            "allow_browser_login": allow_browser_login,
            "criteria": criteria,
        }, ensure_ascii=False, sort_keys=True)
        signature_changed = st.session_state.get("search_signature") != search_signature
        if signature_changed:
            st.session_state["search_signature"] = search_signature
            st.session_state["search_dirty"] = True
            clear_search_outputs()

        auto_search = st.toggle(
            "修改条件后自动重新检索",
            value=False,
            key="auto_search_safe_v2",
            help="默认关闭，避免改平台或页数时反复触发爬虫。需要刷新请点下面的手动按钮。",
        )

        if auto_search and (signature_changed or "current_jobs" not in st.session_state):
            with st.spinner("搜索条件已变化，正在自动重新检索..."):
                jobs = run_search(
                    keyword,
                    location,
                    platforms,
                    max_pages,
                    criteria,
                    search_signature,
                    expand_keywords=expand_keywords,
                    max_keywords=max_keywords,
                    enrich_details=enrich_details,
                    detail_limit=detail_limit,
                    use_browser_crawlers=use_browser_crawlers,
                    allow_browser_login=allow_browser_login,
                )
            st.success(f"已按新条件刷新，本次结果 {len(jobs)} 个")

        if st.button("手动重新检索", width="stretch"):
            with st.spinner("正在按新条件检索并刷新本次结果..."):
                jobs = run_search(
                    keyword,
                    location,
                    platforms,
                    max_pages,
                    criteria,
                    search_signature,
                    expand_keywords=expand_keywords,
                    max_keywords=max_keywords,
                    enrich_details=enrich_details,
                    detail_limit=detail_limit,
                    use_browser_crawlers=use_browser_crawlers,
                    allow_browser_login=allow_browser_login,
                )
            st.success(f"检索完成，本次结果 {len(jobs)} 个")

    if uploaded:
        resume_path = save_upload(uploaded)
        try:
            resume_text = extract_resume_text(resume_path)
        except Exception as exc:
            st.error(str(exc))
            return

        if not resume_text.strip():
            st.error("没有从简历中解析出文字。请换成文本型 PDF、DOCX 或 TXT。")
            return

        st.success(f"已读取简历：{uploaded.name}，约 {len(resume_text)} 字符")

    st.subheader("Agent 求职目标")
    default_goal = "帮我找上海 AI Agent 社招，薪资 20K 以上，3 年以内，双休优先，不要实习不要校招。"
    agent_goal = st.text_area(
        "告诉 Agent 你的求职目标",
        value=st.session_state.get("agent_goal", default_goal),
        height=86,
        help="例如：帮我找上海 AI Agent 社招，薪资 20K 以上，3 年以内，双休优先，不要外包。",
    )
    col_agent_a, col_agent_b = st.columns([1, 3])
    with col_agent_a:
        run_agent = st.button("让 Agent 制定计划并检索", type="primary", width="stretch")
    with col_agent_b:
        st.caption("Agent 搜索默认不会打开浏览器，也不会打开 Boss 登录页。")

    if run_agent:
        st.session_state["agent_goal"] = agent_goal
        with st.spinner("Agent 正在制定搜索计划并检索岗位..."):
            result = run_agent_search(agent_goal, resume_text or None)
        st.session_state["agent_result"] = result
        st.session_state["current_jobs"] = result.get("jobs", [])
        st.session_state["search_summary"] = result.get("summary", {})
        st.session_state["search_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        plan = result.get("plan", {})
        st.session_state["search_signature"] = json.dumps(plan, ensure_ascii=False, sort_keys=True)
        st.session_state["last_search_label"] = (
            f"{plan.get('location', '')} / {plan.get('keyword', '')} / "
            f"平台:{', '.join(plan.get('platforms', []))} / "
            f"页数:{int(plan.get('max_pages') or 1)} / "
            f"类型:{', '.join(plan.get('job_types', []))}"
        )
        st.session_state["search_dirty"] = False
        clear_search_outputs()
        if result.get("resume_profile"):
            st.session_state["resume_profile"] = result["resume_profile"]
        load_jobs.clear()
        st.success(f"Agent 检索完成，本次结果 {len(result.get('jobs', []))} 个")

    agent_result = st.session_state.get("agent_result")
    if agent_result:
        st.markdown("#### Agent 计划与解释")
        run_label = agent_result.get("run_id")
        if run_label:
            st.caption(
                f"Agent 任务：{run_label}"
                + (f"；报告已保存到：{agent_result.get('report_path')}" if agent_result.get("report_path") else "")
            )
        st.info(agent_result.get("agent_message", ""))
        if agent_result.get("run_record"):
            with st.expander("查看 Agent 执行步骤", expanded=False):
                st.dataframe(
                    pd.DataFrame(agent_result.get("run_record", {}).get("steps", [])),
                    width="stretch",
                    hide_index=True,
                )
        if agent_result.get("resume_profile"):
            with st.expander("查看简历画像", expanded=False):
                st.json(agent_result.get("resume_profile", {}))
        if agent_result.get("memory_context"):
            with st.expander("查看求职记忆", expanded=False):
                st.write(agent_result.get("memory_context", {}).get("summary", ""))
                st.json({
                    key: value
                    for key, value in agent_result.get("memory_context", {}).items()
                    if key != "profile"
                })
        with st.expander("查看 Agent 搜索计划", expanded=False):
            st.json(agent_result.get("plan", {}))
        next_actions = agent_result.get("next_actions") or []
        if next_actions:
            st.markdown("下一步建议：" + "；".join(next_actions))
        if agent_result.get("report"):
            st.download_button(
                "下载 Agent 搜索报告 Markdown",
                agent_result["report"],
                file_name="CareerPilot_agent_search_report.md",
            )

        st.markdown("#### Agent 问答")
        agent_question = st.text_input(
            "问当前搜索结果",
            key="agent_question",
            placeholder="例如：为什么结果这么少？优先投哪个？双休为什么缺？",
        )
        col_ask, col_clear = st.columns([1, 5])
        with col_ask:
            ask_clicked = st.button("询问 Agent", width="stretch")
        with col_clear:
            st.caption("回答只基于本次搜索结果、运行记录和本地求职记忆。")
        if ask_clicked and agent_question.strip():
            answer = answer_agent_question(agent_question, agent_result)
            st.session_state.setdefault("agent_chat", []).append({
                "question": agent_question,
                "answer": answer,
            })
        for item in st.session_state.get("agent_chat", [])[-5:]:
            st.markdown(f"**你：** {item['question']}")
            st.markdown(item["answer"])

    with st.expander("最近 Agent 任务", expanded=False):
        runs = load_agent_runs(limit=10)
        if runs:
            rows = [
                {
                    "任务ID": item.get("run_id", ""),
                    "状态": item.get("status", ""),
                    "目标": item.get("goal_text", ""),
                    "岗位数": item.get("job_count", ""),
                    "推荐分布": item.get("decision_counts", {}),
                    "更新时间": item.get("updated_at", ""),
                    "报告": item.get("report_path", ""),
                }
                for item in runs
            ]
            st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
        else:
            st.caption("暂无 Agent 任务记录。")

    with st.expander("本地求职记忆", expanded=False):
        memory_snapshot = export_memory_snapshot()
        st.caption(
            f"反馈记录：{len(memory_snapshot.get('job_feedback', []))}；"
            f"投递记录：{len(memory_snapshot.get('applications', []))}；"
            f"搜索历史：{len(memory_snapshot.get('search_history', []))}"
        )
        st.download_button(
            "下载求职记忆 JSON",
            json.dumps(memory_snapshot, ensure_ascii=False, indent=2),
            file_name="CareerPilot_memory_snapshot.json",
        )

    db_jobs = load_jobs()
    current_jobs = st.session_state.get("current_jobs")
    jobs = current_jobs if current_jobs is not None else filter_jobs(db_jobs, criteria if "criteria" in locals() else {"job_types": ["社招"]})
    if jobs and any(job.get("job_decision") for job in jobs):
        level_options = ["强推", "可投", "谨慎", "不建议"]
        selected_levels = st.multiselect(
            "按 Agent 推荐等级过滤",
            level_options,
            default=level_options,
            key="decision_level_filter",
        )
        jobs = [
            job for job in jobs
            if job.get("job_decision", {}).get("level", "可投") in set(selected_levels)
        ]
    if current_jobs is not None:
        summary = st.session_state.get("search_summary", {})
        st.caption(
            f"本次搜索结果：{len(jobs)} 个；数据库总岗位数：{len(db_jobs)}。"
            f"{st.session_state.get('last_search_label', '')} / "
            f"搜索时间：{st.session_state.get('search_time', '')}"
        )
        if st.session_state.get("search_dirty"):
            st.info("搜索条件已变化，当前表格仍是上一次检索结果。点击左侧“手动重新检索”后，平台、页数和筛选条件才会真正刷新。")
        if summary:
            st.caption(
                f"平台抓取：{summary.get('search_platform_fetch_counts', {})}；"
                f"关键词合并后：{summary.get('search_platform_merged_counts', {})}；"
                f"筛选后：{summary.get('search_filtered_platform_counts', {})}；"
                f"最终展示：{summary.get('search_final_platform_counts', {})}"
            )
            st.caption(
                f"实际检索关键词：{', '.join(summary.get('search_keywords', []))}；"
                f"原始候选：{summary.get('search_raw_total', len(jobs))}；"
                f"筛选后：{summary.get('search_filtered_total', len(jobs))}；"
                f"最终展示：{summary.get('search_final_total', len(jobs))}；"
                f"详情抓取：{summary.get('search_detail_counts', {})}"
            )
            st.caption(
                f"岗位类型分布：{summary.get('search_type_counts', {})}；"
                f"筛选后类型：{summary.get('search_filtered_type_counts', {})}；"
                f"字段完整度：{summary.get('search_field_counts', {})}"
            )
    else:
        st.caption(f"当前筛选后岗位数：{len(jobs)}；数据库总岗位数：{len(db_jobs)}")
        if st.session_state.get("search_dirty"):
            st.info("搜索条件已变化。左侧开启自动检索时会自动刷新；关闭时请点击“手动重新检索”。")

    if jobs:
        st.subheader("岗位结果")
        result_view = st.segmented_control(
            "结果视图",
            ["表格", "卡片"],
            default="表格",
            key="job_result_view",
        )
        if result_view == "卡片":
            card_limit = st.number_input("卡片展示数量", min_value=1, max_value=100, value=min(20, len(jobs)))
            render_job_cards(jobs, limit=int(card_limit))
        else:
            st.dataframe(search_jobs_to_frame(jobs), width="stretch", hide_index=True)
    else:
        st.warning("当前条件下没有岗位结果。可以放宽平台、页数、薪资、经验、学历或双休筛选后重新采集。")

    if not uploaded:
        st.info("上传简历后，可以继续做岗位匹配和简历建议。")
        return

    tab_match, tab_advice, tab_resume = st.tabs(["岗位匹配", "简历优化与面试建议", "简历解析"])

    with tab_match:
        col_a, col_b, col_c = st.columns([1, 1, 2])
        with col_a:
            top_n = st.number_input("展示 Top N", min_value=1, max_value=100, value=20)
        with col_b:
            ai_top_n = st.number_input("DeepSeek 精评前 N 个", min_value=0, max_value=20, value=0, help="0 表示只做本地快速匹配。")

        if not jobs:
            st.warning("数据库里还没有岗位。请先在左侧采集，或用 CLI 导入/爬取岗位。")
        elif st.button("开始匹配", type="primary"):
            with st.spinner("正在匹配岗位..."):
                ranked = rank_jobs_for_resume(resume_text, jobs, top_n=int(top_n), ai_top_n=int(ai_top_n))
                profile = st.session_state.get("resume_profile") or build_resume_profile(resume_text)
                ranked = rank_jobs_with_decisions(ranked, profile, (agent_result or {}).get("plan", {}))
                st.session_state["resume_profile"] = profile
                st.session_state["ranked_jobs"] = ranked
            st.success("匹配完成")

        ranked = st.session_state.get("ranked_jobs", [])
        if ranked:
            df = jobs_to_frame(ranked)
            st.dataframe(df, width="stretch", hide_index=True)

            report = build_match_report(ranked)
            OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
            report_path = OUTPUT_DIR / "resume_job_match_report.md"
            report_path.write_text(report, encoding="utf-8")
            st.download_button("下载匹配报告 Markdown", report, file_name="resume_job_match_report.md")

    with tab_advice:
        ranked = st.session_state.get("ranked_jobs", [])
        source_jobs = ranked or jobs
        if not source_jobs:
            st.warning("还没有岗位可选。")
        else:
            labels = [
                f"{i+1}. {j.get('company', '')} - {j.get('title', '')} ({j.get('location', '')})"
                for i, j in enumerate(source_jobs)
            ]
            selected_idx = st.selectbox("选择目标岗位", range(len(source_jobs)), format_func=lambda i: labels[i], key="selected_job_idx")
            selected_job = source_jobs[selected_idx]

            with st.expander("岗位详情", expanded=False):
                st.json({k: v for k, v in selected_job.items() if k != "resume_match"})

            if selected_job.get("job_decision"):
                with st.expander("Agent 推荐判断", expanded=True):
                    st.json(selected_job.get("job_decision", {}))

            local_profile = st.session_state.get("resume_profile") or (agent_result or {}).get("resume_profile") or {}
            local_advice = build_local_job_advice(selected_job, local_profile)
            with st.expander("本地行动建议", expanded=True):
                st.markdown(local_advice)
                st.download_button(
                    "下载本地行动建议 Markdown",
                    local_advice,
                    file_name="CareerPilot_local_job_advice.md",
                )

            col_status, col_note = st.columns([1, 2])
            with col_status:
                feedback_status = st.selectbox(
                    "记录状态",
                    ["感兴趣", "已投递", "已沟通", "面试中", "不合适", "已拒绝"],
                    key="job_feedback_status",
                )
            with col_note:
                feedback_note = st.text_input("备注", key="job_feedback_note", placeholder="例如：外包风险/薪资低/值得投")
            if st.button("保存岗位状态"):
                if feedback_status in {"已投递", "已沟通", "面试中", "已拒绝"}:
                    save_application_record(selected_job, feedback_status, note=feedback_note)
                else:
                    save_job_feedback(selected_job, feedback_status, feedback_note)
                st.success("已保存到本地求职记忆")

            if st.button("生成简历优化意见和面试建议", type="primary"):
                with st.spinner("DeepSeek 正在生成建议..."):
                    advice = generate_resume_job_advice(resume_text, selected_job)
                    st.session_state["advice"] = advice
                    safe_name = f"{selected_job.get('company','job')}_{selected_job.get('title','')}".replace("/", "_").replace(" ", "_")[:50]
                    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
                    out = OUTPUT_DIR / f"resume_advice_{safe_name}.md"
                    out.write_text(advice, encoding="utf-8")
                    st.session_state["advice_path"] = str(out)

            if st.session_state.get("advice"):
                st.markdown(st.session_state["advice"])
                st.caption(f"已保存到：{st.session_state.get('advice_path')}")
                st.download_button("下载建议 Markdown", st.session_state["advice"], file_name="resume_advice.md")

    with tab_resume:
        st.write("这里用于把简历原文整理成结构化信息。")
        if st.button("解析简历结构"):
            with st.spinner("DeepSeek 正在解析简历..."):
                profile = build_resume_profile(resume_text)
                st.session_state["resume_profile"] = profile

        if st.session_state.get("resume_profile"):
            st.json(st.session_state["resume_profile"])

        with st.expander("查看解析出的简历文本", expanded=False):
            st.text_area("简历文本", resume_text, height=320)


if __name__ == "__main__":
    main()

