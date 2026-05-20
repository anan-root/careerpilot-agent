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


st.set_page_config(page_title="CareerPilot Agent", page_icon="CP", layout="wide")


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


def search_jobs_to_frame(jobs: list[dict], *, show_recommendation: bool = True) -> pd.DataFrame:
    rows = []
    for job in jobs:
        decision = job.get("job_decision", {})
        row = {
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
        }
        if show_recommendation:
            row = {
                "推荐等级": decision.get("level", ""),
                "推荐分": decision.get("score", ""),
                **row,
                "推荐理由": "；".join(decision.get("matched_reasons", [])[:3]),
                "风险": "；".join(decision.get("risks", [])[:3]),
            }
        rows.append(row)
    return pd.DataFrame(rows)


def render_job_cards(jobs: list[dict], limit: int = 20, *, show_recommendation: bool = True):
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
            top_cols = st.columns([4, 1, 1]) if show_recommendation else st.columns([1])
            with top_cols[0]:
                st.markdown(f"**{index}. {company} - {title}**")
                st.caption(f"{platform} / {location} / {address or '地址未知'}")
            if show_recommendation:
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
            if show_recommendation and reasons:
                st.markdown("推荐理由：" + "；".join(reasons))
            if show_recommendation and risks:
                st.warning("风险：" + "；".join(risks))
            if show_recommendation and resume_actions:
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
    st.session_state["manual_search_signature"] = signature
    st.session_state["active_search_source"] = "manual"
    st.session_state["last_search_label"] = (
        f"{location} / {keyword} / 平台:{', '.join(platforms or ['全部'])} / "
        f"页数:{int(max_pages)} / 类型:{', '.join(criteria.get('job_types') or ['全部'])}"
    )
    st.session_state["search_dirty"] = False
    clear_search_outputs()
    load_jobs.clear()
    return jobs


def inject_design_system():
    st.markdown(
        """
        <style>
        :root {
            --cp-bg: #f6f8fb;
            --cp-surface: #ffffff;
            --cp-surface-soft: #f9fafb;
            --cp-border: #d9e2ec;
            --cp-text: #0f172a;
            --cp-muted: #64748b;
            --cp-teal: #0f766e;
            --cp-blue: #2563eb;
            --cp-amber: #b45309;
            --cp-red: #b91c1c;
            --cp-green-soft: #ecfdf5;
            --cp-blue-soft: #eff6ff;
            --cp-amber-soft: #fffbeb;
            --cp-red-soft: #fef2f2;
        }
        .stApp {
            background: var(--cp-bg);
            color: var(--cp-text);
        }
        .block-container {
            max-width: 1520px;
            padding-top: 1.3rem;
            padding-bottom: 2.2rem;
        }
        h1, h2, h3 {
            letter-spacing: 0;
        }
        div[data-testid="stSidebar"] {
            display: none;
        }
        div[data-testid="stVerticalBlockBorderWrapper"] {
            border-color: var(--cp-border);
            border-radius: 8px;
            box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
        }
        div[data-testid="stMetric"] {
            background: var(--cp-surface);
            border: 1px solid var(--cp-border);
            border-radius: 8px;
            padding: 0.55rem 0.7rem;
        }
        div[data-testid="stMetricLabel"] {
            color: var(--cp-muted);
            font-size: 0.78rem;
        }
        div[data-testid="stMetricValue"] {
            font-size: 1.35rem;
        }
        div[data-testid="stButton"] button,
        div[data-testid="stDownloadButton"] button,
        div[data-testid="stLinkButton"] a {
            border-radius: 8px;
            min-height: 2.45rem;
            font-weight: 600;
        }
        .cp-header {
            display: flex;
            align-items: flex-start;
            justify-content: space-between;
            gap: 1rem;
            padding: 0.25rem 0 1rem 0;
            border-bottom: 1px solid var(--cp-border);
            margin-bottom: 1rem;
        }
        .cp-title {
            font-size: 1.65rem;
            font-weight: 760;
            color: var(--cp-text);
            line-height: 1.25;
        }
        .cp-subtitle {
            color: var(--cp-muted);
            margin-top: 0.3rem;
            line-height: 1.6;
        }
        .cp-chip-row {
            display: flex;
            flex-wrap: wrap;
            justify-content: flex-end;
            gap: 0.45rem;
        }
        .cp-chip {
            display: inline-flex;
            align-items: center;
            min-height: 1.75rem;
            padding: 0.15rem 0.55rem;
            border: 1px solid var(--cp-border);
            border-radius: 999px;
            background: var(--cp-surface);
            color: var(--cp-muted);
            font-size: 0.78rem;
            white-space: nowrap;
        }
        .cp-panel-title {
            font-size: 0.92rem;
            font-weight: 720;
            color: var(--cp-text);
            margin-bottom: 0.25rem;
        }
        .cp-panel-note {
            color: var(--cp-muted);
            font-size: 0.82rem;
            line-height: 1.55;
            margin-bottom: 0.8rem;
        }
        .cp-stepper {
            display: grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: 0.55rem;
            margin: 0.3rem 0 1rem 0;
        }
        .cp-step {
            border: 1px solid var(--cp-border);
            background: var(--cp-surface);
            border-radius: 8px;
            padding: 0.6rem 0.7rem;
        }
        .cp-step strong {
            display: block;
            font-size: 0.84rem;
            color: var(--cp-text);
        }
        .cp-step span {
            display: block;
            color: var(--cp-muted);
            font-size: 0.76rem;
            margin-top: 0.2rem;
        }
        .cp-alert {
            border-radius: 8px;
            border: 1px solid var(--cp-border);
            padding: 0.7rem 0.85rem;
            color: var(--cp-text);
            background: var(--cp-surface);
            line-height: 1.55;
        }
        .cp-alert.info {
            background: var(--cp-blue-soft);
            border-color: #bfdbfe;
        }
        .cp-alert.warn {
            background: var(--cp-amber-soft);
            border-color: #fde68a;
        }
        .cp-muted {
            color: var(--cp-muted);
            font-size: 0.82rem;
            line-height: 1.55;
        }
        .cp-empty {
            border: 1px dashed #cbd5e1;
            border-radius: 8px;
            padding: 1.25rem;
            background: var(--cp-surface-soft);
            color: var(--cp-muted);
            line-height: 1.6;
        }
        .cp-level {
            display: inline-block;
            padding: 0.14rem 0.45rem;
            border-radius: 999px;
            font-size: 0.76rem;
            font-weight: 700;
            border: 1px solid var(--cp-border);
            background: var(--cp-surface-soft);
        }
        .cp-level.strong {
            color: var(--cp-teal);
            background: var(--cp-green-soft);
            border-color: #bbf7d0;
        }
        .cp-level.ok {
            color: var(--cp-blue);
            background: var(--cp-blue-soft);
            border-color: #bfdbfe;
        }
        .cp-level.warn {
            color: var(--cp-amber);
            background: var(--cp-amber-soft);
            border-color: #fde68a;
        }
        .cp-level.no {
            color: var(--cp-red);
            background: var(--cp-red-soft);
            border-color: #fecaca;
        }
        @media (max-width: 900px) {
            .cp-header {
                display: block;
            }
            .cp-chip-row {
                justify-content: flex-start;
                margin-top: 0.8rem;
            }
            .cp-stepper {
                grid-template-columns: repeat(2, minmax(0, 1fr));
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def level_class(level: str) -> str:
    mapping = {
        "强推": "strong",
        "可投": "ok",
        "谨慎": "warn",
        "不建议": "no",
    }
    return mapping.get(level, "")


def count_decision_levels(jobs: list[dict]) -> dict[str, int]:
    counts = {"强推": 0, "可投": 0, "谨慎": 0, "不建议": 0}
    for job in jobs:
        level = job.get("job_decision", {}).get("level")
        if level in counts:
            counts[level] += 1
    return counts


def dict_to_rows(payload: dict) -> list[dict]:
    return [{"项目": key, "数量": value} for key, value in (payload or {}).items()]


def render_header(cfg: dict):
    provider = cfg.get("provider", "unknown")
    model = cfg.get("model", "unknown")
    st.markdown(
        f"""
        <div class="cp-header">
            <div>
                <div class="cp-title">职航 Agent 求职操作台</div>
                <div class="cp-subtitle">从目标输入到岗位决策、简历优化、面试准备和求职记忆，集中在一个工作台里完成。</div>
            </div>
            <div class="cp-chip-row">
                <span class="cp-chip">默认城市 上海</span>
                <span class="cp-chip">默认社招/全职</span>
                <span class="cp-chip">LLM {provider} / {model}</span>
                <span class="cp-chip">安全模式</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_stepper(has_resume: bool, has_plan: bool, has_jobs: bool, has_advice: bool):
    steps = [
        ("简历画像", "已上传" if has_resume else "可先跳过"),
        ("Agent 计划", "已生成" if has_plan else "等待目标"),
        ("岗位决策", "已有结果" if has_jobs else "等待检索"),
        ("行动建议", "已生成" if has_advice else "选择岗位后生成"),
    ]
    html = ['<div class="cp-stepper">']
    for title, status in steps:
        html.append(f'<div class="cp-step"><strong>{title}</strong><span>{status}</span></div>')
    html.append("</div>")
    st.markdown("".join(html), unsafe_allow_html=True)


def main():
    inject_design_system()
    cfg = get_llm_config()
    render_header(cfg)

    uploaded = None
    resume_text = ""
    criteria = {"job_types": ["社招"]}

    left_col, center_col, right_col = st.columns([1.05, 2.1, 1.25], gap="large")

    with left_col:
        with st.container(border=True):
            st.markdown('<div class="cp-panel-title">01 目标与简历</div>', unsafe_allow_html=True)
            st.markdown(
                '<div class="cp-panel-note">先告诉 Agent 你想找什么，再决定是否用简历做精准匹配。</div>',
                unsafe_allow_html=True,
            )
            uploaded = st.file_uploader(
                "上传简历",
                type=[ext.lstrip(".") for ext in sorted(SUPPORTED_EXTENSIONS)],
                help="支持 PDF、DOCX、TXT。上传后会用于画像、匹配和建议。",
            )
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
            else:
                st.markdown(
                    '<div class="cp-muted">可以先不上传简历直接检索；上传后推荐会更准。</div>',
                    unsafe_allow_html=True,
                )

            default_goal = "帮我找上海 AI Agent 社招，薪资 20K 以上，3 年以内，双休优先，不要实习不要校招。"
            agent_goal = st.text_area(
                "求职目标",
                value=st.session_state.get("agent_goal", default_goal),
                height=104,
                help="例如：帮我找上海 AI Agent 社招，薪资 20K 以上，3 年以内，双休优先，不要外包。",
            )
            run_agent = st.button("启动 Agent 检索", type="primary", width="stretch")
            st.caption("Agent 默认不会打开浏览器，也不会打开 Boss 登录页。")

        with st.container(border=True):
            st.markdown('<div class="cp-panel-title">02 搜索筛选</div>', unsafe_allow_html=True)
            st.markdown(
                '<div class="cp-panel-note">这里用于手动刷新检索条件。Agent 检索会优先使用目标文本生成计划。</div>',
                unsafe_allow_html=True,
            )
            keyword = st.text_input("搜索关键词", value="AI Agent")
            location_col, page_col = st.columns([1, 1])
            with location_col:
                location = st.text_input("城市", value="上海")
            with page_col:
                max_pages = st.number_input("页数", min_value=1, max_value=10, value=1)

            job_types = st.multiselect(
                "岗位类型",
                ["社招", "校招", "实习"],
                default=["社招"],
                help="默认只看社招/全职。需要校招或实习时再手动勾选。",
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

            with st.expander("高级采集与过滤", expanded=False):
                use_browser_crawlers = st.checkbox(
                    "启用浏览器列表采集（51job/猎聘）",
                    value=False,
                    key="use_browser_crawlers_v2",
                    help="默认关闭，避免自动启动 Edge/Chrome。",
                )
                expand_keywords = st.checkbox("扩展关键词检索", value=True)
                max_keywords = st.number_input("最多扩展关键词数", min_value=1, max_value=8, value=4)
                enrich_details = st.checkbox("二次抓取详情页", value=True)
                detail_limit = st.number_input("详情抓取上限", min_value=0, max_value=100, value=20)
                min_salary_k, max_salary_k = st.slider("月薪范围（K）", 0, 100, (0, 80))
                max_experience_years = st.slider("最高经验要求（年）", 0, 10, 10)
                degrees = st.multiselect(
                    "最高可接受学历要求",
                    ["不限", "大专", "本科", "硕士", "博士"],
                    default=["不限", "大专", "本科", "硕士", "博士"],
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
            last_manual_signature = st.session_state.get("manual_search_signature")
            signature_changed = bool(last_manual_signature and last_manual_signature != search_signature)
            if signature_changed and st.session_state.get("active_search_source") == "manual":
                st.session_state["search_dirty"] = True
                clear_search_outputs()

            auto_search = st.toggle(
                "修改条件后自动重新检索",
                value=False,
                key="auto_search_safe_v2",
                help="默认关闭，避免改平台或页数时反复触发爬虫。",
            )
            manual_search = st.button("按筛选重新检索", width="stretch")

            if auto_search and (signature_changed or "current_jobs" not in st.session_state):
                with st.spinner("正在按当前筛选检索..."):
                    jobs_found = run_search(
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
                st.success(f"已刷新，本次结果 {len(jobs_found)} 个")

            if manual_search:
                with st.spinner("正在按当前筛选检索..."):
                    jobs_found = run_search(
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
                st.success(f"检索完成，本次结果 {len(jobs_found)} 个")

    if run_agent:
        st.session_state["agent_goal"] = agent_goal
        with st.spinner("Agent 正在制定搜索计划并检索岗位..."):
            result = run_agent_search(agent_goal, resume_text or None)
        st.session_state["agent_result"] = result
        st.session_state["current_jobs"] = result.get("jobs", [])
        st.session_state["search_summary"] = result.get("summary", {})
        st.session_state["search_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        st.session_state["active_search_source"] = "agent"
        plan = result.get("plan", {})
        st.session_state["agent_search_signature"] = json.dumps(plan, ensure_ascii=False, sort_keys=True)
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
        st.toast(f"Agent 检索完成，本次结果 {len(result.get('jobs', []))} 个")

    agent_result = st.session_state.get("agent_result")
    db_jobs = load_jobs()
    current_jobs = st.session_state.get("current_jobs")
    jobs = current_jobs if current_jobs is not None else filter_jobs(db_jobs, criteria)

    with center_col:
        render_stepper(
            has_resume=bool(resume_text.strip()),
            has_plan=bool(agent_result),
            has_jobs=current_jobs is not None,
            has_advice=bool(st.session_state.get("advice")),
        )

        st.markdown('<div class="cp-panel-title">岗位决策区</div>', unsafe_allow_html=True)
        summary = st.session_state.get("search_summary", {})
        metric_cols = st.columns(4)
        metric_cols[0].metric("当前结果", len(jobs))
        metric_cols[1].metric("数据库岗位", len(db_jobs))
        metric_cols[2].metric("原始候选", summary.get("search_raw_total", "-") if summary else "-")
        metric_cols[3].metric("最终展示", summary.get("search_final_total", len(jobs)) if summary else len(jobs))

        if current_jobs is not None:
            st.caption(
                f"{st.session_state.get('last_search_label', '')} / "
                f"搜索时间：{st.session_state.get('search_time', '')}"
            )
            if st.session_state.get("search_dirty"):
                st.markdown(
                    '<div class="cp-alert warn">搜索条件已变化，当前结果仍来自上一次手动检索。点击左侧“按筛选重新检索”后，平台、页数和筛选条件才会真正刷新。</div>',
                    unsafe_allow_html=True,
                )
            if summary:
                with st.expander("搜索质量与字段完整度", expanded=False):
                    q1, q2 = st.columns(2)
                    with q1:
                        st.write("平台抓取")
                        st.dataframe(pd.DataFrame(dict_to_rows(summary.get("search_platform_fetch_counts", {}))), hide_index=True, width="stretch")
                        st.write("最终平台分布")
                        st.dataframe(pd.DataFrame(dict_to_rows(summary.get("search_final_platform_counts", {}))), hide_index=True, width="stretch")
                    with q2:
                        st.write("字段完整度")
                        st.dataframe(pd.DataFrame(dict_to_rows(summary.get("search_field_counts", {}))), hide_index=True, width="stretch")
                        st.write("详情抓取")
                        st.dataframe(pd.DataFrame(dict_to_rows(summary.get("search_detail_counts", {}))), hide_index=True, width="stretch")
                    st.caption(f"实际检索关键词：{', '.join(summary.get('search_keywords', []))}")
        else:
            st.markdown(
                '<div class="cp-empty">还没有本轮检索结果。可以启动 Agent 检索，也可以在左侧按筛选手动检索。</div>',
                unsafe_allow_html=True,
            )

        has_resume = bool(resume_text.strip())
        if jobs and not has_resume:
            st.markdown(
                '<div class="cp-alert info">上传简历后，可以查看每个岗位的推荐等级和推荐分，并获得更具体的简历优化与面试建议。</div>',
                unsafe_allow_html=True,
            )

        if has_resume and jobs and any(job.get("job_decision") for job in jobs):
            level_counts = count_decision_levels(jobs)
            st.caption(
                "推荐分布："
                + " / ".join(f"{level} {count}" for level, count in level_counts.items())
            )
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

        if jobs:
            view_cols = st.columns([1, 1])
            with view_cols[0]:
                result_view = st.segmented_control(
                    "结果视图",
                    ["表格", "卡片"],
                    default="表格",
                    key="job_result_view",
                )
            with view_cols[1]:
                card_limit = st.number_input(
                    "展示数量",
                    min_value=1,
                    max_value=100,
                    value=min(20, len(jobs)),
                    key="result_limit",
                )
            if result_view == "卡片":
                render_job_cards(jobs, limit=int(card_limit), show_recommendation=has_resume)
            else:
                st.dataframe(
                    search_jobs_to_frame(jobs[:int(card_limit)], show_recommendation=has_resume),
                    width="stretch",
                    hide_index=True,
                )
        else:
            st.warning("当前条件下没有岗位结果。可以放宽平台、页数、薪资、经验、学历或双休筛选后重新采集。")

        st.markdown('<div class="cp-panel-title">简历匹配与行动</div>', unsafe_allow_html=True)
        if not uploaded:
            st.markdown(
                '<div class="cp-empty">上传简历后，这里会开放岗位匹配、单岗位简历优化、面试建议和简历解析。</div>',
                unsafe_allow_html=True,
            )
        else:
            tab_match, tab_advice, tab_resume = st.tabs(["岗位匹配", "行动建议", "简历解析"])

            with tab_match:
                col_a, col_b = st.columns([1, 1])
                with col_a:
                    top_n = st.number_input("展示 Top N", min_value=1, max_value=100, value=20)
                with col_b:
                    ai_top_n = st.number_input("DeepSeek 精评前 N 个", min_value=0, max_value=20, value=0, help="0 表示只做本地快速匹配。")

                if not jobs:
                    st.warning("还没有岗位。请先检索岗位。")
                elif st.button("开始匹配", type="primary", width="stretch"):
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
                    selected_idx = st.selectbox(
                        "选择目标岗位",
                        range(len(source_jobs)),
                        format_func=lambda i: labels[i],
                        key="selected_job_idx",
                    )
                    selected_job = source_jobs[selected_idx]

                    if selected_job.get("job_decision"):
                        decision = selected_job.get("job_decision", {})
                        level = decision.get("level", "未评估")
                        st.markdown(
                            f'<span class="cp-level {level_class(level)}">{level}</span>',
                            unsafe_allow_html=True,
                        )
                        st.json(decision, expanded=False)

                    with st.expander("岗位详情", expanded=False):
                        st.json({k: v for k, v in selected_job.items() if k != "resume_match"})

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

                    if st.button("生成 DeepSeek 简历优化与面试建议", type="primary", width="stretch"):
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

    with right_col:
        with st.container(border=True):
            st.markdown('<div class="cp-panel-title">Agent 解释</div>', unsafe_allow_html=True)
            if agent_result:
                run_label = agent_result.get("run_id")
                if run_label:
                    st.caption(
                        f"任务：{run_label}"
                        + (f"；报告：{agent_result.get('report_path')}" if agent_result.get("report_path") else "")
                    )
                st.info(agent_result.get("agent_message", ""))
                next_actions = agent_result.get("next_actions") or []
                if next_actions:
                    st.markdown("**下一步**")
                    for item in next_actions:
                        st.write(f"- {item}")
                if agent_result.get("report"):
                    st.download_button(
                        "下载 Agent 报告",
                        agent_result["report"],
                        file_name="CareerPilot_agent_search_report.md",
                        width="stretch",
                    )
                with st.expander("执行步骤", expanded=False):
                    st.dataframe(
                        pd.DataFrame(agent_result.get("run_record", {}).get("steps", [])),
                        width="stretch",
                        hide_index=True,
                    )
                with st.expander("搜索计划", expanded=False):
                    st.json(agent_result.get("plan", {}))
                if agent_result.get("resume_profile"):
                    with st.expander("简历画像", expanded=False):
                        st.json(agent_result.get("resume_profile", {}))
            else:
                st.markdown(
                    '<div class="cp-empty">启动一次 Agent 检索后，这里会显示搜索计划、过程解释、报告和下一步建议。</div>',
                    unsafe_allow_html=True,
                )

        with st.container(border=True):
            st.markdown('<div class="cp-panel-title">Agent 问答</div>', unsafe_allow_html=True)
            agent_question = st.text_input(
                "问当前搜索结果",
                key="agent_question",
                placeholder="为什么结果少？优先投哪个？双休为什么缺？",
                disabled=not bool(agent_result),
            )
            ask_clicked = st.button("询问 Agent", width="stretch", disabled=not bool(agent_result))
            if ask_clicked and agent_question.strip() and agent_result:
                answer = answer_agent_question(agent_question, agent_result)
                st.session_state.setdefault("agent_chat", []).append({
                    "question": agent_question,
                    "answer": answer,
                })
            for item in st.session_state.get("agent_chat", [])[-5:]:
                st.markdown(f"**你：** {item['question']}")
                st.markdown(item["answer"])

        with st.container(border=True):
            st.markdown('<div class="cp-panel-title">记录与记忆</div>', unsafe_allow_html=True)
            runs = load_agent_runs(limit=5)
            with st.expander("最近 Agent 任务", expanded=False):
                if runs:
                    rows = [
                        {
                            "任务ID": item.get("run_id", ""),
                            "状态": item.get("status", ""),
                            "目标": item.get("goal_text", ""),
                            "岗位数": item.get("job_count", ""),
                            "更新时间": item.get("updated_at", ""),
                        }
                        for item in runs
                    ]
                    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
                else:
                    st.caption("暂无 Agent 任务记录。")

            memory_snapshot = export_memory_snapshot()
            st.caption(
                f"反馈 {len(memory_snapshot.get('job_feedback', []))} / "
                f"投递 {len(memory_snapshot.get('applications', []))} / "
                f"搜索 {len(memory_snapshot.get('search_history', []))}"
            )
            st.download_button(
                "下载求职记忆",
                json.dumps(memory_snapshot, ensure_ascii=False, indent=2),
                file_name="CareerPilot_memory_snapshot.json",
                width="stretch",
            )


if __name__ == "__main__":
    main()

