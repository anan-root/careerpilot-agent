"""Streamlit UI for CareerPilot resume matching and job advice."""

from __future__ import annotations

import json
import re
import hashlib
import tempfile
from collections import Counter
from pathlib import Path
from datetime import datetime
from html import escape

import pandas as pd
import streamlit as st

import db
from agents.resume_matcher import (
    SUPPORTED_EXTENSIONS,
    build_match_report,
    extract_resume_text,
    generate_interview_pack,
    generate_job_gap_analysis,
    generate_resume_job_advice,
    rank_jobs_for_resume,
)
from agents.advice_agent import build_local_job_advice
from agents.career_orchestrator import run_agent_search
from agents.conversation_agent import answer_agent_question
from agents.outreach_agent import (
    DEFAULT_GREETING_CONSTRAINT,
    DEFAULT_REPLY_CONSTRAINT,
    generate_boss_greeting,
    generate_boss_reply,
    normalize_max_chars,
)
from agents.profile_agent import build_resume_profile
from agents.ranking_agent import rank_jobs_with_decisions
from agents.search_strategy_agent import build_outreach_task_from_text
from crawlers.aggregator import collect_all_jobs, get_last_search_summary
from crawlers.boss_outreach import check_boss_chat, read_boss_chat_text, send_boss_message
from job_importer import build_job_from_url, build_manual_job, save_imported_job
from job_filters import filter_jobs
from job_actions import annotate_jobs_with_actions
from llm_client import get_llm_config
from match_dashboard import build_match_dashboard
from memory.store import (
    delete_outreach_task,
    export_memory_snapshot,
    load_application_records,
    load_agent_runs,
    load_job_feedback,
    load_outreach_tasks,
    move_outreach_task,
    save_application_record,
    save_job_feedback,
    save_outreach_record,
    save_outreach_task,
)
from platform_registry import (
    DEFAULT_PLATFORM_CODES,
    PLATFORM_LABELS,
    PLATFORM_ORDER,
    normalize_platform,
    platform_label,
    platform_label_text,
)
from search_summary import (
    merge_duplicate_summaries,
    merge_invalid_job_summaries,
    merge_job_quality_summaries,
)

OUTPUT_DIR = Path(__file__).parent / "data" / "outputs"
DEFAULT_AGENT_GOAL = "帮我找上海 AI Agent 岗位，我是去年毕业的，薪资 20K 以内，社招和校招都可以，双休优先，不要实习。"
OLD_DEFAULT_AGENT_GOAL = "帮我找上海 AI Agent 社招，薪资 20K 以上，3 年以内，双休优先，不要实习不要校招。"


st.set_page_config(page_title="CareerPilot Agent", page_icon="CP", layout="wide")


@st.cache_data(show_spinner=False)
def load_jobs() -> list[dict]:
    return db.get_all_jobs_df()


def clear_search_outputs():
    for key in (
        "ranked_jobs",
        "advice",
        "advice_path",
        "gap_analysis",
        "gap_analysis_path",
        "interview_pack",
        "interview_pack_path",
    ):
        st.session_state.pop(key, None)


def save_upload(uploaded_file) -> Path:
    suffix = Path(uploaded_file.name).suffix.lower()
    temp_dir = Path(tempfile.mkdtemp(prefix="CareerPilot_resume_"))
    path = temp_dir / uploaded_file.name
    path.write_bytes(uploaded_file.getbuffer())
    return path


def jobs_to_frame(jobs: list[dict]) -> pd.DataFrame:
    return search_jobs_to_frame(jobs, show_recommendation=True)


def resume_text_hash(text: str) -> str:
    return hashlib.sha1(str(text or "").strip().encode("utf-8")).hexdigest()[:16]


def resume_cache_key(uploaded_file, resume_text: str) -> str:
    name = getattr(uploaded_file, "name", "resume")
    return f"{name}:{resume_text_hash(resume_text)}"


def reset_result_pagination():
    st.session_state["result_page_v1"] = 1


def platform_key(value: object) -> str:
    code = normalize_platform(str(value or "").strip())
    if code in {"boss_drission", "boss_cookie"}:
        return "boss"
    return code


def platform_keys(values: list[str] | tuple[str, ...] | set[str] | None) -> list[str]:
    keys: list[str] = []
    for value in values or []:
        key = platform_key(value)
        if key and key not in keys:
            keys.append(key)
    return keys


def platform_display_order(selected_platforms: list[str] | tuple[str, ...] | set[str] | None) -> list[str]:
    selected_keys = set(platform_keys(selected_platforms or DEFAULT_PLATFORM_CODES))
    order: list[str] = []
    for source in (DEFAULT_PLATFORM_CODES, selected_platforms or [], PLATFORM_ORDER):
        for value in source:
            key = platform_key(value)
            if key and key not in order and (key in selected_keys or source is PLATFORM_ORDER):
                order.append(key)
    return order


def filter_jobs_by_platforms(jobs: list[dict], selected_platforms: list[str] | tuple[str, ...] | set[str] | None) -> list[dict]:
    selected_keys = set(platform_keys(selected_platforms or DEFAULT_PLATFORM_CODES))
    if not selected_keys:
        return list(jobs)
    return [job for job in jobs if platform_key(job.get("platform", "")) in selected_keys]


def filter_jobs_by_location(jobs: list[dict], location: str | None) -> list[dict]:
    target = clean_display_value(location)
    if not target:
        return list(jobs)
    return [
        job for job in jobs
        if target in clean_display_value(job.get("location", ""))
        or target in clean_display_value(job.get("company_address", ""))
        or target in clean_display_value(job.get("address", ""))
    ]


def sort_jobs_by_platform_priority(jobs: list[dict], selected_platforms: list[str] | tuple[str, ...] | set[str] | None) -> list[dict]:
    order = platform_display_order(selected_platforms)
    priority = {code: index for index, code in enumerate(order)}
    return sorted(jobs, key=lambda job: priority.get(platform_key(job.get("platform", "")), len(priority) + 1))


def prepare_jobs_for_display(
    source_jobs: list[dict],
    *,
    selected_platforms: list[str] | tuple[str, ...] | set[str] | None,
    location: str | None = None,
    criteria: dict | None,
    already_filtered: bool,
) -> list[dict]:
    jobs = list(source_jobs)
    if not already_filtered:
        jobs = filter_jobs(jobs, criteria)
    jobs = filter_jobs_by_location(jobs, location)
    jobs = filter_jobs_by_platforms(jobs, selected_platforms)
    return sort_jobs_by_platform_priority(jobs, selected_platforms)


UNKNOWN_MARKERS = {
    "",
    "-",
    "未知",
    "暂无",
    "无",
    "未提供",
    "列表页未提供",
    "不确定",
    "unknown",
    "none",
    "null",
    "nan",
}

COMPANY_SIZE_PATTERN = re.compile(r"(?:少于)?\d+\s*-\s*\d+\s*人|\d+\s*人以上|\d+\s*-\s*\d+\s*人|10000人以上")
TITLE_SALARY_PATTERN = re.compile(
    r"(?:\d+(?:\.\d+)?\s*[-~]\s*\d+(?:\.\d+)?\s*[kK](?:·\d+薪)?)|"
    r"(?:\d+(?:\.\d+)?\s*[kK](?:·\d+薪)?)|"
    r"(?:\d+\s*-\s*\d+\s*元/天)|"
    r"(?:薪资面议)",
    re.IGNORECASE,
)
TITLE_EXPERIENCE_PATTERN = re.compile(r"(?:经验不限|不限经验|无需经验|应届生|\d+\s*-\s*\d+\s*年|\d+\s*年以上?|\d+\s*年以内?)")
TITLE_DEGREE_PATTERN = re.compile(r"(博士|硕士|本科|大专|学历不限|不限)")
CITY_NAMES = ("上海", "北京", "杭州", "深圳", "广州", "成都", "南京", "武汉", "苏州", "西安", "重庆", "天津")
COMPANY_INDUSTRY_TOKENS = (
    "企业服务",
    "互联网",
    "人工智能",
    "智能硬件",
    "医疗健康",
    "金融",
    "基金",
    "证券",
    "咨询",
    "软件",
    "电子商务",
    "游戏",
    "广告营销",
    "数据服务",
    "大数据",
    "云计算",
    "通信",
    "汽车",
    "新能源",
    "机器人",
    "教育",
    "贸易",
    "物流",
    "制造业",
)
COMPANY_NAME_INDUSTRY_RULES = (
    (("私募", "基金", "证券", "期货", "资管", "资产管理", "投资"), "金融/基金"),
    (("人工智能", "智能科技", "AI", "Ai", "ai"), "人工智能"),
    (("人才", "人力资源", "猎头", "招聘"), "人力资源"),
    (("管理咨询", "咨询"), "咨询服务"),
    (("教育", "培训", "学校", "大学"), "教育"),
    (("医疗", "医药", "健康", "生物"), "医疗健康"),
    (("软件", "网络科技", "信息科技", "互联网"), "互联网/软件"),
    (("通信", "通讯"), "通信"),
    (("汽车", "新能源"), "汽车/新能源"),
    (("机器人",), "机器人"),
)
INLINE_NOISE_TOKENS = ("未知", "暂无")
TITLE_NOISE_TOKENS = ("直达官网投后必反馈", "绑定官网账号并投递", "官网闪投")

INSURANCE_TOKENS = (
    "五险一金",
    "五险",
    "六险",
    "七险",
    "社保",
    "公积金",
    "补充医疗",
    "商业保险",
)

RECOMMENDATION_TIERS = (
    {"min": 90, "level": "强推", "class": "gold"},
    {"min": 80, "level": "推荐", "class": "orange"},
    {"min": 70, "level": "可投", "class": "purple"},
    {"min": 60, "level": "谨慎", "class": "blue"},
    {"min": 50, "level": "备选", "class": "green"},
    {"min": 0, "level": "不建议", "class": "white"},
)

LEGACY_LEVEL_SCORES = {
    "王牌机会": 95,
    "强烈推荐": 85,
    "优先关注": 75,
    "可以投递": 65,
    "备选岗位": 55,
    "普通岗位": 45,
    "强推": 85,
    "推荐": 80,
    "可投": 65,
    "谨慎": 52,
    "备选": 55,
    "不建议": 35,
}


def clean_display_value(value) -> str:
    text = str(value or "").strip()
    if text.lower() in UNKNOWN_MARKERS:
        return ""
    return text


def has_display_value(value) -> bool:
    return bool(clean_display_value(value))


def extract_insurance_text(welfare: str) -> str:
    welfare_text = clean_display_value(welfare)
    if not welfare_text:
        return ""
    if "五险一金" in welfare_text:
        return "五险一金"
    found = [token for token in INSURANCE_TOKENS if token in welfare_text]
    return "、".join(dict.fromkeys(found))


def extract_weekend_text(job: dict) -> str:
    weekend = clean_display_value(job.get("weekend_display") or job.get("weekend_policy", ""))
    welfare = clean_display_value(job.get("welfare", ""))
    if weekend:
        return weekend
    if any(token in welfare for token in ("周末双休", "双休", "五天工作制", "周末休息")):
        return "双休"
    if any(token in welfare for token in ("单休", "单双休", "大小周")):
        return "非双休/不确定"
    return ""


def first_display_value(job: dict, keys: tuple[str, ...] | list[str]) -> str:
    for key in keys:
        value = clean_display_value(job.get(key, ""))
        if value:
            return value
    return ""


def trim_display_text(value, limit: int = 140) -> str:
    text = clean_display_value(value)
    if not text:
        return ""
    text = " ".join(text.replace("\r", " ").replace("\n", " ").split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def labeled_parts(items: list[tuple[str, str]], *, separator: str = " · ") -> str:
    parts = [f"{label}：{value}" for label, value in items if clean_display_value(value)]
    return separator.join(parts)


def compact_text(text: str) -> str:
    return " ".join(str(text or "").replace("\r", " ").replace("\n", " ").split()).strip()


def strip_inline_noise(text: str, *, strip_general: bool = False) -> str:
    result = str(text or "")
    for token in INLINE_NOISE_TOKENS:
        result = result.replace(token, "")
    if strip_general:
        result = result.replace("综合", "")
    return compact_text(result)


def normalize_company_size(value: str) -> str:
    text = strip_inline_noise(clean_display_value(value), strip_general=True)
    match = COMPANY_SIZE_PATTERN.search(text)
    return match.group(0).replace(" ", "") if match else ""


def infer_company_size(job: dict) -> str:
    return normalize_company_size(job.get("company_size", "")) or normalize_company_size(job.get("company", ""))


def normalize_company_industry(value: str) -> str:
    text = strip_inline_noise(clean_display_value(value), strip_general=True)
    if not text:
        return ""
    for token in COMPANY_INDUSTRY_TOKENS:
        if token in text:
            return token
    return text if len(text) <= 8 else ""


def infer_company_industry(job: dict) -> str:
    company_name = display_company_name(job)
    for keywords, industry in COMPANY_NAME_INDUSTRY_RULES:
        if any(keyword in company_name for keyword in keywords):
            return industry

    text = str(job.get("company", "") or "")
    text = COMPANY_SIZE_PATTERN.sub("", text)
    text = strip_inline_noise(text, strip_general=True)
    for token in sorted(COMPANY_INDUSTRY_TOKENS, key=len, reverse=True):
        if text.endswith(token):
            return token

    return normalize_company_industry(job.get("company_industry", ""))


def display_company_name(job: dict) -> str:
    text = str(job.get("company", "") or "")
    if not clean_display_value(text):
        return ""
    text = COMPANY_SIZE_PATTERN.sub("", text)
    text = strip_inline_noise(text, strip_general=True)
    for token in sorted(COMPANY_INDUSTRY_TOKENS, key=len, reverse=True):
        if text.endswith(token):
            text = text[: -len(token)].strip()
            break
    return text.strip(" -｜|·，,")


def display_job_title(job: dict) -> str:
    raw = compact_text(clean_display_value(job.get("title", "")))
    if not raw:
        return ""

    title = re.sub(r"^(社招|校招|实习|日常实习|暑期实习|全职)\s*[|｜·\-]\s*", "", raw)
    salary = salary_text(job)
    if salary and salary in title:
        title = title[: title.find(salary)]
    else:
        salary_match = TITLE_SALARY_PATTERN.search(title)
        if salary_match:
            title = title[: salary_match.start()]

    for token in TITLE_NOISE_TOKENS:
        title = title.replace(token, "")
    title = re.sub(r"^(社招|校招|实习|日常实习|暑期实习|全职)\s*[|｜·\-]\s*", "", title)
    title = re.sub(rf"({'|'.join(CITY_NAMES)})(?=(?:{TITLE_EXPERIENCE_PATTERN.pattern}|{TITLE_DEGREE_PATTERN.pattern}))", "", title)
    title = TITLE_EXPERIENCE_PATTERN.sub("", title)
    title = TITLE_DEGREE_PATTERN.sub("", title)
    title = compact_text(title).strip(" -｜|·，,")
    title = re.sub(r"(.{2,12}?工程师)工程师$", r"\1", title)
    return title or raw


def display_experience_text(job: dict) -> str:
    value = clean_display_value(job.get("experience_display") or job.get("experience", ""))
    if re.fullmatch(r"\d+年以", value):
        return f"{value}内"
    return value


def company_founded_text(job: dict) -> str:
    return first_display_value(
        job,
        (
            "company_founded",
            "company_founded_at",
            "company_found_date",
            "founded_at",
            "founded_date",
            "established_at",
            "established_date",
        ),
    )


def job_type_text(job: dict) -> str:
    return clean_display_value(job.get("normalized_job_type") or job.get("job_type", ""))


def salary_text(job: dict) -> str:
    return clean_display_value(job.get("salary", "")) or _salary_range_text(job)


def compact_requirements(job: dict, limit: int = 260) -> str:
    text = first_display_value(job, ("requirements", "description", "full_jd"))
    text = trim_display_text(text.replace(";", "；"), limit=limit)
    return text


def parse_recommendation_score(value) -> float | None:
    if value is None or value is False:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        if text.endswith("%"):
            score = float(text[:-1])
        else:
            score = float(text)
    except ValueError:
        return None
    return round(max(0.0, min(100.0, score)), 1)


def recommendation_view(job: dict) -> dict:
    decision = job.get("job_decision") or {}
    match = job.get("resume_match") or {}
    ai_match = job.get("ai_match") or match.get("ai") or {}
    legacy_level = clean_display_value(decision.get("level", ""))
    score = parse_recommendation_score(decision.get("score"))
    if score is None:
        score = parse_recommendation_score(ai_match.get("score"))
    if score is None:
        score = parse_recommendation_score(match.get("score"))
    if score is None and legacy_level in LEGACY_LEVEL_SCORES:
        score = float(LEGACY_LEVEL_SCORES[legacy_level])
    if score is None:
        return {"level": "未评估", "score": None, "class": "white"}
    for tier in RECOMMENDATION_TIERS:
        if score >= tier["min"]:
            return {"level": tier["level"], "score": score, "class": tier["class"]}
    return {"level": "不建议", "score": score, "class": "white"}


def ai_match_view(job: dict) -> dict:
    match = job.get("ai_match") or (job.get("resume_match") or {}).get("ai") or {}
    return match if isinstance(match, dict) else {}


def list_text(value: object, limit: int = 3) -> str:
    if not value:
        return ""
    if isinstance(value, (list, tuple, set)):
        items = [clean_display_value(item) for item in value]
    else:
        items = [clean_display_value(value)]
    return "；".join([item for item in items if item][:limit])


def build_company_block(job: dict, visible: dict[str, bool]) -> str:
    company = display_company_name(job)
    lines = [company] if company else []
    meta = labeled_parts([
        ("规模", infer_company_size(job)),
        ("行业", infer_company_industry(job)),
    ])
    if meta:
        lines.append(meta)
    founded = company_founded_text(job)
    if founded:
        lines.append(f"成立：{founded}")
    address = clean_display_value(job.get("company_address", ""))
    if visible.get("address") and address:
        lines.append(f"地址：{address}")
    return "\n".join(lines)


def build_job_block(job: dict, visible: dict[str, bool]) -> str:
    title = display_job_title(job)
    lines = [title] if title else []
    requirement_line = labeled_parts([
        ("薪资", salary_text(job)),
        ("学历", clean_display_value(job.get("degree_display") or job.get("degree", ""))),
        ("经验", display_experience_text(job)),
    ])
    if requirement_line:
        lines.append(requirement_line)
    work_line = labeled_parts([
        ("类型", job_type_text(job)),
        ("地点", clean_display_value(job.get("location", ""))),
        ("双休", extract_weekend_text(job) if visible.get("weekend") else ""),
    ])
    if work_line:
        lines.append(work_line)
    welfare = trim_display_text(job.get("welfare", ""), limit=120)
    if visible.get("welfare") and welfare:
        lines.append(f"福利：{welfare}")
    return "\n".join(lines)


def should_show_optional_column(jobs: list[dict], extractor) -> bool:
    return any(has_display_value(extractor(job)) for job in jobs)


def visible_job_columns(jobs: list[dict], *, show_recommendation: bool) -> dict[str, bool]:
    return {
        "recommendation": show_recommendation,
        "address": should_show_optional_column(jobs, lambda job: job.get("company_address")),
        "weekend": should_show_optional_column(jobs, extract_weekend_text),
        "welfare": should_show_optional_column(jobs, lambda job: job.get("welfare")),
    }


def search_jobs_to_frame(jobs: list[dict], *, show_recommendation: bool = True) -> pd.DataFrame:
    visible = visible_job_columns(jobs, show_recommendation=show_recommendation)
    rows = []
    for job in jobs:
        row = {
            "公司": build_company_block(job, visible),
            "岗位": build_job_block(job, visible),
        }
        if show_recommendation:
            recommendation = recommendation_view(job)
            row = {
                "推荐等级": recommendation["level"],
                "推荐分": recommendation["score"],
                **row,
            }
        rows.append(row)
    return pd.DataFrame(rows)


def block_lines_html(text: str) -> str:
    lines = [line.strip() for line in str(text or "").splitlines() if line.strip()]
    if not lines:
        return ""
    html = [f'<div class="cp-table-main">{escape(lines[0])}</div>']
    html.extend(f'<div class="cp-table-sub">{escape(line)}</div>' for line in lines[1:])
    return "".join(html)


def render_job_table(jobs: list[dict], limit: int, *, show_recommendation: bool = True):
    visible = visible_job_columns(jobs, show_recommendation=show_recommendation)
    headers = []
    if show_recommendation:
        headers.append('<th class="cp-table-reco-col">推荐</th>')
    headers.extend(["<th>公司</th>", "<th>岗位</th>"])

    rows = []
    for job in jobs[:limit]:
        recommendation = recommendation_view(job)
        cells = []
        if show_recommendation:
            score_text = "" if recommendation["score"] is None else f'{recommendation["score"]:.1f}'
            cells.append(
                '<td class="cp-table-reco-cell">'
                f'<span class="cp-level {escape(recommendation["class"])}">{escape(recommendation["level"])}</span>'
                f'<div class="cp-table-score">{escape(score_text)}</div>'
                '</td>'
            )
        cells.extend([
            f'<td>{block_lines_html(build_company_block(job, visible))}</td>',
            f'<td>{block_lines_html(build_job_block(job, visible))}</td>',
        ])
        rows.append(
            f'<tr class="tier-{escape(recommendation["class"] if show_recommendation else "white")}">'
            + "".join(cells)
            + "</tr>"
        )

    table_html = (
        '<div class="cp-job-table-wrap">'
        '<table class="cp-job-table">'
        f'<thead><tr>{"".join(headers)}</tr></thead>'
        f'<tbody>{"".join(rows)}</tbody>'
        '</table>'
        '</div>'
    )
    st.markdown(table_html, unsafe_allow_html=True)


def render_job_cards(
    jobs: list[dict],
    limit: int = 20,
    *,
    show_recommendation: bool = True,
    start_index: int = 1,
):
    visible = visible_job_columns(jobs, show_recommendation=show_recommendation)
    for index, job in enumerate(jobs[:limit], start_index):
        decision = job.get("job_decision", {})
        ai_match = ai_match_view(job)
        recommendation = recommendation_view(job)
        title = display_job_title(job)
        company = display_company_name(job)
        platform = clean_display_value(job.get("platform", ""))
        location = clean_display_value(job.get("location", ""))
        address = clean_display_value(job.get("company_address", ""))
        industry = infer_company_industry(job)
        company_size = infer_company_size(job)
        founded = company_founded_text(job)
        salary = salary_text(job)
        experience = display_experience_text(job)
        degree = clean_display_value(job.get("degree_display") or job.get("degree", ""))
        weekend = extract_weekend_text(job)
        welfare = clean_display_value(job.get("welfare", ""))
        reasons = (ai_match.get("matched_evidence") or decision.get("matched_reasons", []))[:3]
        risks = (ai_match.get("risk_points") or ai_match.get("risks") or decision.get("risks", []))[:3]
        missing = (ai_match.get("missing_requirements") or ai_match.get("missing_keywords") or decision.get("missing_requirements", []))[:3]
        resume_actions = (ai_match.get("resume_actions") or decision.get("resume_actions", []))[:2]
        interview_focus = (ai_match.get("interview_focus") or decision.get("interview_focus", []))[:3]
        posted_date = clean_display_value(job.get("posted_date", ""))
        requirement_brief = compact_requirements(job)
        url = clean_display_value(job.get("source_url") or job.get("url", ""))
        meta_line = labeled_parts([
            ("薪资", salary),
            ("学历", degree),
            ("经验", experience),
            ("类型", job_type_text(job)),
            ("地点", location),
            ("双休", weekend if visible.get("weekend") else ""),
        ])
        company_line = labeled_parts([
            ("规模", company_size),
            ("行业", industry),
            ("成立", founded),
            ("地址", address if visible.get("address") else ""),
        ])
        welfare_line = trim_display_text(welfare, limit=180) if visible.get("welfare") else ""
        recommendation_html = ""
        if show_recommendation:
            score_text = "" if recommendation["score"] is None else f'{recommendation["score"]:.1f}'
            recommendation_html = (
                f'<div class="cp-card-score">'
                f'<span>{escape(recommendation["level"])}</span>'
                f'<strong>{escape(score_text)}</strong>'
                f'</div>'
            )
        detail_rows = []
        for label, value in (
            ("岗位发布时间", posted_date),
            ("公司信息", company_line),
            ("简略招聘要求", requirement_brief),
            ("匹配证据", "；".join(reasons) if show_recommendation else ""),
            ("缺失能力", "；".join(missing) if show_recommendation else ""),
            ("风险提醒", "；".join(risks) if show_recommendation else ""),
            ("简历动作", "；".join(resume_actions) if show_recommendation else ""),
            ("面试重点", "；".join(interview_focus) if show_recommendation else ""),
            ("来源平台", platform),
        ):
            if clean_display_value(value):
                detail_rows.append(
                    f'<div class="cp-card-detail-row"><span>{escape(label)}</span><p>{escape(str(value))}</p></div>'
                )
        link_html = f'<a class="cp-card-link" href="{escape(url, quote=True)}" target="_blank">打开岗位来源</a>' if url else ""
        company_html = f'<div class="cp-card-company">{escape(company)}</div>' if company else ""
        welfare_html = f'<div class="cp-card-welfare">福利：{escape(welfare_line)}</div>' if welfare_line else ""
        card_class = escape(recommendation["class"] if show_recommendation else "white")
        card_html = (
            f'<details class="cp-job-card tier-{card_class}">'
            '<summary>'
            '<div class="cp-card-head">'
            '<div class="cp-card-main">'
            f'<div class="cp-card-title">{index}. {escape(title)}</div>'
            f'{company_html}'
            '</div>'
            f'{recommendation_html}'
            '</div>'
            f'<div class="cp-card-meta">{escape(meta_line)}</div>'
            f'{welfare_html}'
            '</summary>'
            '<div class="cp-card-detail">'
            f'{"".join(detail_rows)}'
            f'{link_html}'
            '</div>'
            '</details>'
        )
        st.markdown(card_html, unsafe_allow_html=True)


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
    progress_callback=None,
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
        progress_callback=progress_callback,
    )
    st.session_state["current_jobs"] = jobs
    st.session_state["search_summary"] = get_last_search_summary()
    st.session_state["search_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    st.session_state["search_signature"] = signature
    st.session_state["manual_search_signature"] = signature
    st.session_state["active_search_source"] = "manual"
    st.session_state["result_display_platforms"] = list(platforms or [])
    st.session_state["result_display_location"] = location
    st.session_state["result_display_criteria"] = dict(criteria or {})
    st.session_state["last_search_label"] = (
        f"{location} / {keyword} / 平台:{platform_label_text(platforms)} / "
        f"页数:{int(max_pages)} / 类型:{', '.join(criteria.get('job_types') or ['全部'])}"
    )
    st.session_state["search_dirty"] = False
    clear_search_outputs()
    reset_result_pagination()
    load_jobs.clear()
    return jobs


def run_task_search(
    task: dict,
    signature: str,
    *,
    use_browser_crawlers: bool = False,
    allow_browser_login: bool = False,
    progress_callback=None,
) -> list[dict]:
    criteria = task_criteria(task)
    cities = task_cities(task)
    platforms = task_platforms(task)
    keyword = str(task.get("search_text") or task.get("keyword") or "AI Agent").strip() or "AI Agent"
    max_pages = int(task.get("max_pages") or 2)
    expanded_keywords = [str(item).strip() for item in (task.get("expanded_keywords") or []) if str(item).strip()]

    all_jobs: list[dict] = []
    summaries: list[dict] = []
    for index, city in enumerate(cities):
        if progress_callback:
            progress_callback(f"任务城市 {city}（{index + 1}/{len(cities)}）")
        city_jobs = collect_all_jobs(
            keyword,
            city,
            platforms=platforms,
            max_pages=max_pages,
            criteria=criteria,
            expand_keywords=True,
            max_keywords=max(1, len(expanded_keywords) or 5),
            search_keywords=expanded_keywords or None,
            enrich_details=True,
            detail_limit=20,
            use_browser_crawlers=use_browser_crawlers,
            allow_browser_login=allow_browser_login,
            progress_callback=progress_callback,
        )
        for job in city_jobs:
            job.setdefault("task_city", city)
        all_jobs.extend(city_jobs)
        summaries.append(get_last_search_summary())

    deduped = dedupe_jobs_for_task(all_jobs)
    regex_filtered = apply_task_regex_filter(deduped, task.get("regex_include", ""), task.get("regex_exclude", ""))
    active_filtered = apply_task_active_hr_filter(regex_filtered, task)
    summary = merge_task_summaries(summaries, before_regex=len(deduped), after_regex=len(active_filtered), task=task)

    st.session_state["current_jobs"] = active_filtered
    st.session_state["search_summary"] = summary
    st.session_state["search_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    st.session_state["search_signature"] = signature
    st.session_state["task_search_signature"] = signature
    st.session_state["active_search_source"] = "task"
    st.session_state["active_outreach_task"] = dict(task)
    st.session_state["task_platforms"] = platforms
    st.session_state["task_criteria"] = criteria
    st.session_state["result_display_platforms"] = platforms
    st.session_state["result_display_location"] = None
    st.session_state["result_display_criteria"] = criteria
    st.session_state["last_search_label"] = (
        f"{'/'.join(cities)} / {keyword} / 平台:{platform_label_text(platforms)} / "
        f"页数:{max_pages} / 类型:{', '.join(criteria.get('job_types') or ['全部'])}"
    )
    st.session_state["search_dirty"] = False
    clear_search_outputs()
    reset_result_pagination()
    load_jobs.clear()
    return active_filtered


def add_imported_job_to_workspace(job: dict) -> list[dict]:
    current_jobs = list(st.session_state.get("current_jobs") or [])
    jobs = dedupe_jobs_for_task([job, *current_jobs])
    st.session_state["current_jobs"] = jobs

    source_platform = platform_key(job.get("platform", "")) or "manual"
    platforms = platform_keys(st.session_state.get("result_display_platforms") or [])
    if source_platform not in platforms:
        platforms = [source_platform, *platforms]
    st.session_state["result_display_platforms"] = platforms
    st.session_state["result_display_location"] = None
    st.session_state.setdefault("result_display_criteria", {})
    st.session_state["active_search_source"] = "manual_import"
    st.session_state["search_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    st.session_state["last_search_label"] = f"手动导入岗位 / 当前结果 {len(jobs)} 个"
    st.session_state["search_dirty"] = False

    summary = dict(st.session_state.get("search_summary") or {})
    summary["selected_platforms"] = platforms
    summary["search_raw_total"] = len(jobs)
    summary["search_filtered_total"] = len(jobs)
    summary["search_final_total"] = len(jobs)
    summary["search_keywords"] = summary.get("search_keywords") or ["手动导入"]
    for key in (
        "search_platform_fetch_counts",
        "search_platform_merged_counts",
        "search_raw_platform_counts",
        "search_filtered_platform_counts",
        "search_final_platform_counts",
    ):
        counts = Counter(summary.get(key) or {})
        counts[source_platform] = sum(
            1 for item in jobs
            if platform_key(item.get("platform", "")) == source_platform
        )
        summary[key] = dict(counts)
    summary["search_field_quality"] = summarize_field_quality(jobs)
    st.session_state["search_summary"] = summary
    clear_search_outputs()
    reset_result_pagination()
    load_jobs.clear()
    return jobs


def summarize_field_quality(jobs: list[dict]) -> dict[str, float | int]:
    scores = [float(job.get("field_quality_score") or 0) for job in jobs]
    if not scores:
        return {"avg_score": 0.0, "high_quality": 0, "total": 0}
    return {
        "avg_score": round(sum(scores) / len(scores), 1),
        "high_quality": sum(1 for score in scores if score >= 75),
        "total": len(scores),
    }


def task_criteria(task: dict) -> dict:
    criteria = dict(task.get("criteria") or {})
    job_types = task.get("job_types") or criteria.get("job_types") or ["社招"]
    criteria["job_types"] = [str(item) for item in job_types if str(item).strip()]
    return criteria


def task_cities(task: dict) -> list[str]:
    cities = task.get("cities")
    if isinstance(cities, str):
        values = re.split(r"[,，、\s/]+", cities)
    elif isinstance(cities, (list, tuple, set)):
        values = []
        for city in cities:
            values.extend(re.split(r"[,，、\s/]+", str(city)))
    else:
        values = re.split(r"[,，、\s/]+", str(task.get("cities_text") or task.get("location") or "上海"))
    result = []
    for city in values:
        text = str(city or "").strip()
        if text and text not in result:
            result.append(text)
    return result or ["上海"]


def task_platforms(task: dict) -> list[str]:
    values = task.get("platforms") or DEFAULT_PLATFORM_CODES
    if isinstance(values, str):
        raw = re.split(r"[,，、\s/]+", values)
    else:
        raw = list(values)
    result = []
    for value in raw:
        key = platform_key(value)
        if key and key not in result:
            result.append(key)
    return result or list(DEFAULT_PLATFORM_CODES)


def task_display_text(job: dict) -> str:
    keys = (
        "title",
        "company",
        "location",
        "salary",
        "job_type",
        "skills",
        "degree",
        "experience",
        "description",
        "requirements",
        "full_jd",
        "welfare",
        "hr_name",
        "hr_title",
    )
    return " ".join(str(job.get(key) or "") for key in keys)


def apply_task_regex_filter(jobs: list[dict], include_text: str = "", exclude_text: str = "") -> list[dict]:
    include_patterns = compile_task_patterns(include_text)
    exclude_patterns = compile_task_patterns(exclude_text)
    if not include_patterns and not exclude_patterns:
        return list(jobs)
    results = []
    for job in jobs:
        text = task_display_text(job)
        if include_patterns and not any(pattern.search(text) for pattern in include_patterns):
            continue
        if exclude_patterns and any(pattern.search(text) for pattern in exclude_patterns):
            continue
        results.append(job)
    return results


def apply_task_active_hr_filter(jobs: list[dict], task: dict) -> list[dict]:
    if not task.get("only_active_hr"):
        return list(jobs)
    results = []
    for job in jobs:
        if platform_key(job.get("platform", "")) != "boss":
            results.append(job)
            continue
        if job.get("chat_url") or job.get("hr_name") or job.get("hr_title"):
            results.append(job)
    return results


def compile_task_patterns(value: str) -> list[re.Pattern]:
    patterns = []
    for item in re.split(r"[,，、\n]+", str(value or "")):
        text = item.strip()
        if not text:
            continue
        try:
            patterns.append(re.compile(text, flags=re.IGNORECASE))
        except re.error:
            patterns.append(re.compile(re.escape(text), flags=re.IGNORECASE))
    return patterns


def dedupe_jobs_for_task(jobs: list[dict]) -> list[dict]:
    seen = set()
    results = []
    for job in jobs:
        key = "|".join(str(job.get(field) or "").strip() for field in ("platform", "job_id", "company", "title"))
        fallback_key = "|".join(str(job.get(field) or "").strip() for field in ("platform", "company", "title", "location"))
        dedupe_key = key if key.strip("|") else fallback_key
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        results.append(job)
    return results


def merge_task_summaries(summaries: list[dict], *, before_regex: int, after_regex: int, task: dict) -> dict:
    counter_keys = (
        "search_platform_fetch_counts",
        "search_platform_merged_counts",
        "search_raw_platform_counts",
        "search_filtered_platform_counts",
        "search_final_platform_counts",
        "search_type_counts",
        "search_filtered_type_counts",
        "search_detail_counts",
    )
    summary: dict = {
        "selected_platforms": task_platforms(task),
        "search_keywords": [],
        "search_raw_total": 0,
        "search_filtered_total": 0,
        "search_final_total": after_regex,
        "task_before_regex_total": before_regex,
        "task_after_regex_total": after_regex,
        "task_cities": task_cities(task),
        "criteria": task_criteria(task),
        "ai_filter_text": task.get("ai_filter_text", ""),
        "match_threshold": task.get("match_threshold", 70),
    }
    for key in counter_keys:
        merged = Counter()
        for item in summaries:
            merged.update(item.get(key) or {})
        summary[key] = dict(merged)
    field_counts: dict[str, Counter] = {}
    for item in summaries:
        for field, counts in (item.get("search_field_counts") or {}).items():
            field_counts.setdefault(field, Counter()).update(counts or {})
    summary["search_field_counts"] = {field: dict(counts) for field, counts in field_counts.items()}
    summary["search_invalid_jobs"] = merge_invalid_job_summaries(summaries)
    summary["search_duplicate_summary"] = merge_duplicate_summaries(summaries)
    summary["search_job_quality"] = merge_job_quality_summaries(summaries)
    keyword_fetch_counts: dict[str, int] = {}
    for item in summaries:
        for key, value in (item.get("search_keyword_fetch_counts") or {}).items():
            keyword_fetch_counts[key] = keyword_fetch_counts.get(key, 0) + int(value or 0)
        for keyword in item.get("search_keywords") or []:
            if keyword not in summary["search_keywords"]:
                summary["search_keywords"].append(keyword)
        summary["search_raw_total"] += int(item.get("search_raw_total", 0) or 0)
        summary["search_filtered_total"] += int(item.get("search_filtered_total", 0) or 0)
    summary["search_keyword_fetch_counts"] = keyword_fetch_counts
    return summary


def apply_task_match_threshold(jobs: list[dict], task: dict | None) -> list[dict]:
    if not task:
        return jobs
    threshold = int(task.get("match_threshold") or 0)
    if threshold <= 0:
        return jobs
    filtered = []
    for job in jobs:
        score = parse_recommendation_score((job.get("job_decision") or {}).get("score"))
        if score is None:
            score = parse_recommendation_score((job.get("resume_match") or {}).get("score"))
        if score is None or score >= threshold:
            filtered.append(job)
    return filtered


def render_outreach_task_panel(
    resume_profile: dict,
    *,
    platform_options: list[str],
    use_browser_crawlers: bool,
    allow_browser_login: bool,
):
    st.markdown('<div class="cp-panel-title">03 求职任务</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="cp-panel-note">用自然语言生成可编辑任务；保存后再手动执行搜索或生成沟通草稿。</div>',
        unsafe_allow_html=True,
    )

    default_task_text = "ai应用 rag 大模型应用，上海北京深圳杭州，本科，8到20K，只投活跃 HR，100 字以内介绍 RAG 项目，不提薪资，语气礼貌"
    natural_text = st.text_area(
        "自然语言任务",
        value=st.session_state.get("outreach_task_natural_text", default_task_text),
        height=118,
        key="outreach_task_natural_text",
    )
    parse_cols = st.columns([1, 1])
    with parse_cols[0]:
        parse_task = st.button("解析为草稿", width="stretch", key="outreach_task_parse")
    with parse_cols[1]:
        clear_draft = st.button("清空草稿", width="stretch", key="outreach_task_clear")
    if parse_task:
        draft = build_outreach_task_from_text(natural_text, resume_profile)
        st.session_state["outreach_task_draft"] = draft
        st.session_state["active_outreach_task"] = draft
        sync_outreach_task_widget_state(draft)
        st.success("已生成任务草稿，请检查后保存或直接检索。")
    if clear_draft:
        st.session_state.pop("outreach_task_draft", None)

    with st.expander("已保存任务", expanded=False):
        tasks = load_outreach_tasks()
        if tasks:
            for task in tasks[:12]:
                row = st.columns([2.6, 0.9, 0.75, 0.75, 0.75])
                with row[0]:
                    st.write(f"{task.get('name', '未命名任务')} / {task.get('cities_text', '')}")
                with row[1]:
                    if st.button("加载", key=f"outreach_task_load_{task.get('task_id')}", width="stretch"):
                        st.session_state["outreach_task_draft"] = dict(task)
                        st.session_state["active_outreach_task"] = dict(task)
                        sync_outreach_task_widget_state(task)
                        st.rerun()
                with row[2]:
                    if st.button("上移", key=f"outreach_task_up_{task.get('task_id')}", width="stretch"):
                        move_outreach_task(task.get("task_id", ""), -1)
                        st.rerun()
                with row[3]:
                    if st.button("下移", key=f"outreach_task_down_{task.get('task_id')}", width="stretch"):
                        move_outreach_task(task.get("task_id", ""), 1)
                        st.rerun()
                with row[4]:
                    if st.button("删除", key=f"outreach_task_delete_{task.get('task_id')}", width="stretch"):
                        delete_outreach_task(task.get("task_id", ""))
                        if (st.session_state.get("active_outreach_task") or {}).get("task_id") == task.get("task_id"):
                            st.session_state.pop("active_outreach_task", None)
                        st.rerun()
        else:
            st.markdown('<div class="cp-muted">暂无已保存任务。</div>', unsafe_allow_html=True)

    draft = dict(st.session_state.get("outreach_task_draft") or {})
    if not draft:
        return

    with st.expander("任务草稿与设置", expanded=True):
        name = st.text_input("任务名称", value=draft.get("name", ""), key="outreach_task_name")
        search_text = st.text_input("搜索职位", value=draft.get("search_text") or draft.get("keyword") or "AI Agent", key="outreach_task_search_text")
        cities_text = st.text_input("城市", value=draft.get("cities_text") or draft.get("location") or "上海", key="outreach_task_cities_text")
        selected_platforms = st.multiselect(
            "平台",
            platform_options,
            default=[p for p in task_platforms(draft) if p in platform_options],
            key="outreach_task_platforms",
            format_func=platform_label,
        )
        task_job_types = st.multiselect(
            "求职类型",
            ["社招", "校招", "实习"],
            default=[item for item in (draft.get("job_types") or (draft.get("criteria") or {}).get("job_types") or ["社招"]) if item in {"社招", "校招", "实习"}],
            key="outreach_task_job_types",
        )
        ai_filter_text = st.text_area(
            "AI 筛选职位说明",
            value=draft.get("ai_filter_text", ""),
            height=80,
            key="outreach_task_ai_filter",
        )
        regex_cols = st.columns(2)
        with regex_cols[0]:
            regex_include = st.text_input("包含关键词/正则", value=draft.get("regex_include", ""), key="outreach_task_regex_include")
        with regex_cols[1]:
            regex_exclude = st.text_input("排除关键词/正则", value=draft.get("regex_exclude", ""), key="outreach_task_regex_exclude")
        more_cols = st.columns(3)
        with more_cols[0]:
            match_threshold = st.number_input(
                "匹配度",
                min_value=0,
                max_value=100,
                value=int(draft.get("match_threshold") or 70),
                step=5,
                key="outreach_task_match_threshold",
            )
        with more_cols[1]:
            greeting_max_chars = st.number_input(
                "打招呼字数",
                min_value=20,
                max_value=300,
                value=normalize_max_chars(draft.get("greeting_max_chars") or 100),
                step=10,
                key="outreach_task_greeting_max",
            )
        with more_cols[2]:
            max_pages = st.number_input(
                "每城页数",
                min_value=1,
                max_value=10,
                value=int(draft.get("max_pages") or 2),
                key="outreach_task_max_pages",
            )
        only_active_hr = st.checkbox("只投活跃 HR", value=bool(draft.get("only_active_hr")), key="outreach_task_active_hr")
        greeting_prompt = st.text_area(
            "打招呼提示词边界",
            value=draft.get("greeting_prompt") or DEFAULT_GREETING_CONSTRAINT,
            height=86,
            key="outreach_task_greeting_prompt",
        )
        reply_prompt = st.text_area(
            "回复提示词边界",
            value=draft.get("reply_prompt") or DEFAULT_REPLY_CONSTRAINT,
            height=86,
            key="outreach_task_reply_prompt",
        )

        updated = dict(draft)
        updated.update({
            "name": name.strip() or search_text.strip() or "未命名任务",
            "keyword": search_text.strip() or "AI Agent",
            "search_text": search_text.strip() or "AI Agent",
            "cities_text": cities_text.strip() or "上海",
            "cities": [item for item in re.split(r"[,，、\s/]+", cities_text) if item.strip()],
            "location": next((item for item in re.split(r"[,，、\s/]+", cities_text) if item.strip()), "上海"),
            "platforms": selected_platforms or ["boss"],
            "job_types": task_job_types or ["社招"],
            "ai_filter_text": ai_filter_text,
            "regex_include": regex_include,
            "regex_exclude": regex_exclude,
            "match_threshold": int(match_threshold),
            "greeting_max_chars": int(greeting_max_chars),
            "greeting_prompt": greeting_prompt,
            "reply_prompt": reply_prompt,
            "only_active_hr": bool(only_active_hr),
            "max_pages": int(max_pages),
        })
        criteria = dict(updated.get("criteria") or {})
        criteria["job_types"] = updated["job_types"]
        updated["criteria"] = criteria
        st.session_state["outreach_task_draft"] = updated
        st.session_state["active_outreach_task"] = updated

        if updated.get("notes"):
            st.caption("；".join(str(item) for item in updated.get("notes", [])[:3]))

        action_cols = st.columns([1, 1])
        with action_cols[0]:
            if st.button("保存任务", type="primary", width="stretch", key="outreach_task_save"):
                saved = save_outreach_task(updated)
                st.session_state["outreach_task_draft"] = saved
                st.session_state["active_outreach_task"] = saved
                st.success("任务已保存到本地 JSON。")
                st.rerun()
        with action_cols[1]:
            if st.button("按任务检索", width="stretch", key="outreach_task_search"):
                signature = json.dumps(updated, ensure_ascii=False, sort_keys=True)
                with st.status("正在按任务检索...", expanded=True) as status:
                    jobs_found = run_task_search(
                        updated,
                        signature,
                        use_browser_crawlers=use_browser_crawlers,
                        allow_browser_login=allow_browser_login,
                        progress_callback=make_status_progress(status),
                    )
                    status.update(label=f"任务检索完成，本次结果 {len(jobs_found)} 个", state="complete")
                st.success(f"任务检索完成，本次结果 {len(jobs_found)} 个")
                st.session_state["career_workspace_v1"] = "岗位结果"
                st.rerun()


def sync_outreach_task_widget_state(task: dict) -> None:
    cities_text = task.get("cities_text") or " ".join(task_cities(task))
    values = {
        "outreach_task_name": task.get("name", ""),
        "outreach_task_search_text": task.get("search_text") or task.get("keyword") or "AI Agent",
        "outreach_task_cities_text": cities_text or "上海",
        "outreach_task_platforms": task_platforms(task),
        "outreach_task_job_types": task.get("job_types") or (task.get("criteria") or {}).get("job_types") or ["社招"],
        "outreach_task_ai_filter": task.get("ai_filter_text", ""),
        "outreach_task_regex_include": task.get("regex_include", ""),
        "outreach_task_regex_exclude": task.get("regex_exclude", ""),
        "outreach_task_match_threshold": int(task.get("match_threshold") or 70),
        "outreach_task_greeting_max": normalize_max_chars(task.get("greeting_max_chars") or 100),
        "outreach_task_max_pages": int(task.get("max_pages") or 2),
        "outreach_task_active_hr": bool(task.get("only_active_hr")),
        "outreach_task_greeting_prompt": task.get("greeting_prompt") or DEFAULT_GREETING_CONSTRAINT,
        "outreach_task_reply_prompt": task.get("reply_prompt") or DEFAULT_REPLY_CONSTRAINT,
    }
    for key, value in values.items():
        st.session_state[key] = value


def render_boss_outreach_panel(selected_job: dict, profile: dict, task: dict | None):
    task = task or {}
    is_boss = platform_key(selected_job.get("platform", "")) == "boss"
    chat_url = str(selected_job.get("chat_url") or "").strip()
    task_id = str(task.get("task_id") or "")
    outreach_key = "|".join(
        str(selected_job.get(field) or "").strip()
        for field in ("platform", "job_id", "company", "title")
    )
    if st.session_state.get("boss_outreach_job_key") != outreach_key:
        st.session_state["boss_outreach_job_key"] = outreach_key
        for key in (
            "boss_outreach_greeting_text",
            "boss_outreach_reply_text",
            "boss_outreach_hr_text",
            "boss_outreach_pending_hr_text",
            "boss_outreach_confirm_greeting",
            "boss_outreach_confirm_reply",
        ):
            st.session_state.pop(key, None)

    with st.expander("BOSS 沟通区", expanded=True):
        st.caption("先生成草稿，再编辑确认；非 BOSS 或没有沟通链接时只生成文本。")
        if not is_boss:
            st.info("当前岗位不是 BOSS 岗位，只生成沟通文本。")
        elif not chat_url:
            st.info("当前 BOSS 岗位没有沟通链接，只生成沟通文本。")

        match_payload = {
            "job_decision": selected_job.get("job_decision", {}),
            "ai_match": selected_job.get("ai_match", {}),
            "resume_match": selected_job.get("resume_match", {}),
        }
        max_chars = st.number_input(
            "打招呼字数上限",
            min_value=20,
            max_value=300,
            value=normalize_max_chars(task.get("greeting_max_chars") or 100),
            step=10,
            key="boss_outreach_greeting_max",
        )
        custom_prompt = st.text_area(
            "打招呼提示词边界",
            value=task.get("greeting_prompt") or DEFAULT_GREETING_CONSTRAINT,
            height=92,
            key="boss_outreach_greeting_prompt",
        )
        if st.button("生成招呼语草稿", type="primary", key="boss_outreach_generate_greeting"):
            draft = generate_boss_greeting(
                selected_job,
                profile,
                match_payload,
                max_chars=int(max_chars),
                custom_prompt=custom_prompt,
            )
            st.session_state["boss_outreach_greeting_text"] = draft["message"]
            save_outreach_record(
                selected_job,
                task_id=task_id,
                action_type="greeting",
                message_text=draft["message"],
                max_chars=int(max_chars),
                custom_prompt=custom_prompt,
                status="drafted",
                send_result=draft.get("source", ""),
                platform_url=chat_url,
            )
            st.caption(f"草稿来源：{draft.get('source')}；字数：{len(draft['message'])}/{int(max_chars)}")
        st.session_state.setdefault("boss_outreach_greeting_text", "")
        greeting_text = st.text_area(
            "最终招呼语",
            height=104,
            key="boss_outreach_greeting_text",
        )
        st.caption(f"当前字数：{len(greeting_text.strip())}/{int(max_chars)}")

        greet_cols = st.columns([1, 1])
        with greet_cols[0]:
            if st.button("干跑检查", key="boss_outreach_dry_run", disabled=not (is_boss and chat_url), width="stretch"):
                result = check_boss_chat(selected_job, dry_run=True)
                save_outreach_record(
                    selected_job,
                    task_id=task_id,
                    action_type="greeting",
                    message_text=greeting_text,
                    max_chars=int(max_chars),
                    custom_prompt=custom_prompt,
                    status=result.get("status", "dry_run"),
                    send_result=result.get("status", ""),
                    platform_url=result.get("platform_url", chat_url),
                    error=result.get("error", ""),
                )
                _render_outreach_result(result)
        with greet_cols[1]:
            confirm_send = st.checkbox("确认发送这条招呼语", key="boss_outreach_confirm_greeting")
            if st.button(
                "发送到 BOSS",
                key="boss_outreach_send_greeting",
                disabled=not (is_boss and chat_url and greeting_text.strip() and confirm_send),
                width="stretch",
            ):
                result = send_boss_message(selected_job, greeting_text, confirm_send=True)
                save_outreach_record(
                    selected_job,
                    task_id=task_id,
                    action_type="greeting",
                    message_text=greeting_text,
                    max_chars=int(max_chars),
                    custom_prompt=custom_prompt,
                    status=result.get("status", ""),
                    send_result=result.get("status", ""),
                    platform_url=result.get("platform_url", chat_url),
                    error=result.get("error", ""),
                )
                _render_outreach_result(result)

        st.divider()
        st.markdown("**回复建议**")
        if "boss_outreach_pending_hr_text" in st.session_state:
            st.session_state["boss_outreach_hr_text"] = st.session_state.pop("boss_outreach_pending_hr_text")
        st.session_state.setdefault("boss_outreach_hr_text", "")
        reply_source = st.text_area(
            "HR 消息或当前会话文本",
            height=96,
            key="boss_outreach_hr_text",
        )
        read_disabled = not (is_boss and chat_url)
        read_cols = st.columns([1, 1])
        with read_cols[0]:
            if st.button("读取当前会话文本", key="boss_outreach_read_chat", disabled=read_disabled, width="stretch"):
                result = read_boss_chat_text(selected_job)
                if result.get("chat_text"):
                    st.session_state["boss_outreach_pending_hr_text"] = result["chat_text"]
                    st.rerun()
                _render_outreach_result(result)
        with read_cols[1]:
            reply_max_chars = st.number_input(
                "回复字数上限",
                min_value=20,
                max_value=300,
                value=normalize_max_chars(120),
                step=10,
                key="boss_outreach_reply_max",
            )
        reply_prompt = st.text_area(
            "回复提示词边界",
            value=task.get("reply_prompt") or DEFAULT_REPLY_CONSTRAINT,
            height=84,
            key="boss_outreach_reply_prompt",
        )
        if st.button("生成回复建议", key="boss_outreach_generate_reply"):
            draft = generate_boss_reply(
                selected_job,
                profile,
                reply_source,
                max_chars=int(reply_max_chars),
                custom_prompt=reply_prompt,
            )
            st.session_state["boss_outreach_reply_text"] = draft["message"]
            save_outreach_record(
                selected_job,
                task_id=task_id,
                action_type="reply",
                message_text=draft["message"],
                max_chars=int(reply_max_chars),
                custom_prompt=reply_prompt,
                status="drafted",
                send_result=draft.get("source", ""),
                platform_url=chat_url,
            )
            st.caption(f"回复来源：{draft.get('source')}；字数：{len(draft['message'])}/{int(reply_max_chars)}")
        st.session_state.setdefault("boss_outreach_reply_text", "")
        reply_text = st.text_area(
            "最终回复文本",
            height=92,
            key="boss_outreach_reply_text",
        )
        confirm_reply = st.checkbox("确认发送这条回复", key="boss_outreach_confirm_reply")
        if st.button(
            "发送回复到 BOSS",
            key="boss_outreach_send_reply",
            disabled=not (is_boss and chat_url and reply_text.strip() and confirm_reply),
            width="stretch",
        ):
            result = send_boss_message(selected_job, reply_text, confirm_send=True)
            save_outreach_record(
                selected_job,
                task_id=task_id,
                action_type="reply",
                message_text=reply_text,
                max_chars=int(reply_max_chars),
                custom_prompt=reply_prompt,
                status=result.get("status", ""),
                send_result=result.get("status", ""),
                platform_url=result.get("platform_url", chat_url),
                error=result.get("error", ""),
            )
            _render_outreach_result(result)


def _render_outreach_result(result: dict):
    status = result.get("status", "")
    message = result.get("message", "")
    if status in {"sent", "dry_run_ok", "ready", "read_ok"}:
        st.success(message or status)
    elif status in {"missing_chat_url", "confirm_required", "empty_message"}:
        st.info(message or status)
    else:
        st.warning(message or status)
    if result.get("error"):
        st.caption(result.get("error"))


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
            --cp-gold-soft: #fff7d6;
            --cp-gold-border: #f0c04a;
            --cp-orange-soft: #fff1e6;
            --cp-orange-border: #fb923c;
            --cp-purple-soft: #f5f0ff;
            --cp-purple-border: #a78bfa;
            --cp-green-border: #86efac;
        }
        .stApp {
            background: var(--cp-bg);
            color: var(--cp-text);
        }
        .block-container {
            max-width: 1520px;
            padding-top: 4.2rem;
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
            padding: 0.4rem 0 1rem 0;
            border-bottom: 1px solid var(--cp-border);
            margin-bottom: 1rem;
            position: relative;
            z-index: 0;
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
        .cp-level.gold {
            color: #854d0e;
            background: var(--cp-gold-soft);
            border-color: var(--cp-gold-border);
        }
        .cp-level.orange {
            color: #9a3412;
            background: var(--cp-orange-soft);
            border-color: var(--cp-orange-border);
        }
        .cp-level.purple {
            color: #6d28d9;
            background: var(--cp-purple-soft);
            border-color: var(--cp-purple-border);
        }
        .cp-level.blue {
            color: var(--cp-blue);
            background: var(--cp-blue-soft);
            border-color: #bfdbfe;
        }
        .cp-level.green {
            color: var(--cp-teal);
            background: var(--cp-green-soft);
            border-color: var(--cp-green-border);
        }
        .cp-level.white {
            color: var(--cp-muted);
            background: var(--cp-surface);
            border-color: var(--cp-border);
        }
        .cp-job-table-wrap {
            border: 1px solid var(--cp-border);
            border-radius: 8px;
            background: var(--cp-surface);
            overflow: auto;
            max-height: 640px;
            box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
        }
        .cp-job-table {
            width: 100%;
            border-collapse: separate;
            border-spacing: 0;
            table-layout: fixed;
            font-size: 0.84rem;
        }
        .cp-job-table th {
            position: sticky;
            top: 0;
            z-index: 1;
            background: #f8fafc;
            color: var(--cp-muted);
            text-align: left;
            font-weight: 720;
            padding: 0.72rem 0.85rem;
            border-bottom: 1px solid var(--cp-border);
        }
        .cp-job-table th:first-child,
        .cp-job-table td:first-child {
            border-left: 0;
        }
        .cp-job-table td {
            vertical-align: top;
            padding: 0.82rem 0.85rem;
            border-bottom: 1px solid var(--cp-border);
            border-left: 1px solid #eef2f7;
            line-height: 1.55;
            word-break: break-word;
        }
        .cp-job-table tbody tr:last-child td {
            border-bottom: 0;
        }
        .cp-job-table tbody tr.tier-gold td:first-child {
            border-left: 5px solid var(--cp-gold-border);
        }
        .cp-job-table tbody tr.tier-orange td:first-child {
            border-left: 5px solid var(--cp-orange-border);
        }
        .cp-job-table tbody tr.tier-purple td:first-child {
            border-left: 5px solid var(--cp-purple-border);
        }
        .cp-job-table tbody tr.tier-blue td:first-child {
            border-left: 5px solid #93c5fd;
        }
        .cp-job-table tbody tr.tier-green td:first-child {
            border-left: 5px solid var(--cp-green-border);
        }
        .cp-table-main {
            color: var(--cp-text);
            font-weight: 740;
            line-height: 1.45;
            margin-bottom: 0.3rem;
        }
        .cp-table-sub {
            color: var(--cp-muted);
            line-height: 1.65;
        }
        .cp-table-reco-col {
            width: 7rem;
        }
        .cp-table-reco-cell {
            text-align: left;
            background: #fcfcfd;
        }
        .cp-table-score {
            margin-top: 0.4rem;
            color: var(--cp-text);
            font-size: 1.05rem;
            font-weight: 760;
        }
        .cp-job-card {
            display: block;
            border: 1px solid var(--cp-border);
            border-left-width: 5px;
            border-radius: 8px;
            background: var(--cp-surface);
            padding: 0.85rem 0.95rem;
            margin: 0.65rem 0;
            box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
        }
        .cp-job-card summary {
            list-style: none;
            cursor: pointer;
        }
        .cp-job-card summary::-webkit-details-marker {
            display: none;
        }
        .cp-job-card summary::after {
            content: "展开详情";
            display: inline-flex;
            margin-top: 0.55rem;
            color: var(--cp-muted);
            font-size: 0.78rem;
        }
        .cp-job-card[open] summary::after {
            content: "收起详情";
        }
        .cp-job-card.tier-gold {
            background: linear-gradient(180deg, #fffaf0 0%, #ffffff 72%);
            border-left-color: var(--cp-gold-border);
        }
        .cp-job-card.tier-orange {
            background: linear-gradient(180deg, #fff7ed 0%, #ffffff 72%);
            border-left-color: var(--cp-orange-border);
        }
        .cp-job-card.tier-purple {
            background: linear-gradient(180deg, #faf5ff 0%, #ffffff 72%);
            border-left-color: var(--cp-purple-border);
        }
        .cp-job-card.tier-blue {
            background: linear-gradient(180deg, #eff6ff 0%, #ffffff 72%);
            border-left-color: #93c5fd;
        }
        .cp-job-card.tier-green {
            background: linear-gradient(180deg, #ecfdf5 0%, #ffffff 72%);
            border-left-color: var(--cp-green-border);
        }
        .cp-job-card.tier-white {
            border-left-color: var(--cp-border);
        }
        .cp-card-head {
            display: flex;
            align-items: flex-start;
            justify-content: space-between;
            gap: 0.9rem;
        }
        .cp-card-main {
            min-width: 0;
            flex: 1 1 auto;
        }
        .cp-card-title {
            color: var(--cp-text);
            font-size: 1rem;
            line-height: 1.35;
            font-weight: 760;
            overflow-wrap: anywhere;
        }
        .cp-card-company {
            margin-top: 0.18rem;
            color: var(--cp-muted);
            font-size: 0.84rem;
            line-height: 1.45;
        }
        .cp-card-meta,
        .cp-card-welfare {
            color: var(--cp-text);
            font-size: 0.84rem;
            line-height: 1.6;
            margin-top: 0.55rem;
        }
        .cp-card-welfare {
            color: var(--cp-muted);
        }
        .cp-card-score {
            min-width: 5.6rem;
            border: 1px solid var(--cp-border);
            border-radius: 8px;
            background: rgba(255, 255, 255, 0.78);
            padding: 0.36rem 0.5rem;
            text-align: center;
        }
        .cp-card-score span {
            display: block;
            color: var(--cp-muted);
            font-size: 0.72rem;
            font-weight: 700;
            line-height: 1.2;
        }
        .cp-card-score strong {
            display: block;
            color: var(--cp-text);
            font-size: 1.05rem;
            line-height: 1.35;
        }
        .cp-card-detail {
            border-top: 1px solid var(--cp-border);
            margin-top: 0.75rem;
            padding-top: 0.75rem;
        }
        .cp-card-detail-row {
            display: grid;
            grid-template-columns: 6.5rem minmax(0, 1fr);
            gap: 0.75rem;
            margin: 0.45rem 0;
        }
        .cp-card-detail-row span {
            color: var(--cp-muted);
            font-size: 0.78rem;
            line-height: 1.55;
        }
        .cp-card-detail-row p {
            margin: 0;
            color: var(--cp-text);
            font-size: 0.84rem;
            line-height: 1.6;
        }
        .cp-card-link {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            min-height: 2.2rem;
            margin-top: 0.6rem;
            padding: 0 0.75rem;
            border: 1px solid var(--cp-border);
            border-radius: 8px;
            color: var(--cp-blue);
            font-weight: 700;
            text-decoration: none;
            background: var(--cp-surface);
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
            .cp-card-head,
            .cp-card-detail-row {
                display: block;
            }
            .cp-card-score {
                margin-top: 0.6rem;
                text-align: left;
            }
            .cp-job-table {
                min-width: 760px;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def level_class(level: str) -> str:
    mapping = {
        "王牌机会": "gold",
        "强烈推荐": "orange",
        "优先关注": "purple",
        "可以投递": "blue",
        "备选岗位": "green",
        "普通岗位": "white",
        "强推": "gold",
        "推荐": "orange",
        "可投": "purple",
        "谨慎": "blue",
        "备选": "green",
        "不建议": "white",
    }
    return mapping.get(level, "")


def recommendation_level_options() -> list[str]:
    return [str(tier["level"]) for tier in RECOMMENDATION_TIERS]


def count_recommendation_levels(jobs: list[dict]) -> dict[str, int]:
    counts = {level: 0 for level in recommendation_level_options()}
    for job in jobs:
        level = recommendation_view(job)["level"]
        if level in counts:
            counts[level] += 1
    return counts


def dict_to_rows(payload: dict) -> list[dict]:
    return [{"项目": platform_label(key), "数量": value} for key, value in (payload or {}).items()]


def field_counts_rows(payload: dict) -> list[dict]:
    labels = {
        "experience": "经验要求",
        "degree": "学历要求",
        "welfare": "福利/双休",
        "company_address": "公司地址",
        "salary": "薪资",
    }
    rows = []
    for key, label in labels.items():
        counts = (payload or {}).get(key) or {}
        filled = int(counts.get("filled", 0) or 0)
        missing = int(counts.get("missing", 0) or 0)
        total = filled + missing
        rows.append({
            "字段": label,
            "已获取": filled,
            "总数": total,
            "完整度": f"{round(filled / total * 100)}%" if total else "-",
        })
    return rows


def render_agent_trace(agent_result: dict, summary: dict, jobs: list[dict]):
    plan = agent_result.get("plan", {}) if agent_result else {}
    run_record = agent_result.get("run_record", {}) if agent_result else {}
    with st.expander("Agent 执行记录", expanded=True):
        trace_rows = [
            {"阶段": "搜索计划", "结果": f"{plan.get('location', '上海')} / {plan.get('keyword', '')} / {platform_label_text(plan.get('platforms', []))}"},
            {"阶段": "实际关键词", "结果": "，".join(summary.get("search_keywords") or plan.get("expanded_keywords") or [])},
            {"阶段": "候选数量", "结果": f"原始 {summary.get('search_raw_total', len(jobs))} / 筛选 {summary.get('search_filtered_total', len(jobs))} / 展示 {summary.get('search_final_total', len(jobs))}"},
            {"阶段": "DeepSeek 精排", "结果": f"请求 {summary.get('llm_rerank_requested', 0)} / 成功 {summary.get('llm_rerank_success', 0)}"},
            {"阶段": "推荐分布", "结果": json.dumps(summary.get('recommendation_level_counts') or count_recommendation_levels(jobs), ensure_ascii=False)},
        ]
        st.dataframe(pd.DataFrame(trace_rows), width="stretch", hide_index=True)
        steps = run_record.get("steps") or []
        if steps:
            st.write("执行步骤")
            st.dataframe(pd.DataFrame(steps), width="stretch", hide_index=True)
        field_counts = summary.get("search_field_counts") or {}
        if field_counts:
            st.write("字段完整度")
            st.dataframe(pd.DataFrame(field_counts_rows(field_counts)), width="stretch", hide_index=True)
        platform_counts = summary.get("search_final_platform_counts") or {}
        if platform_counts:
            st.write("最终平台分布")
            st.dataframe(pd.DataFrame(dict_to_rows(platform_counts)), width="stretch", hide_index=True)


def make_status_progress(status):
    def _progress(message: str):
        text = clean_display_value(message)
        if text:
            status.write(text)
    return _progress


def render_text_list(title: str, items: object, *, empty: str = "暂无", limit: int = 6):
    st.markdown(f"**{title}**")
    values = []
    if isinstance(items, (list, tuple, set)):
        values = [clean_display_value(item) for item in items]
    elif items:
        values = [clean_display_value(items)]
    values = [item for item in values if item][:limit]
    if not values:
        st.caption(empty)
        return
    for item in values:
        st.write(f"- {item}")


def render_resume_profile_summary(profile: dict):
    if not profile:
        st.caption("简历画像尚未生成。")
        return
    role = clean_display_value(profile.get("target_role")) or list_text(profile.get("target_roles"), limit=2)
    exp = profile.get("experience_years")
    st.markdown(f"**目标方向：** {role or '暂未判断'}")
    st.markdown(f"**经验年限：** {exp if exp is not None else '暂未提取'}")
    render_text_list("核心技能", profile.get("skills"), limit=10)
    project_names = [
        project.get("name") or project.get("summary")
        for project in profile.get("projects", [])
        if isinstance(project, dict)
    ]
    render_text_list("项目证据", project_names, empty="简历中暂未提取到明确项目", limit=5)
    render_text_list("优势", profile.get("strengths"), limit=5)
    render_text_list("风险/待补充", profile.get("gaps") or profile.get("risks"), empty="暂无明显风险", limit=5)


def render_match_summary(job: dict):
    recommendation = recommendation_view(job)
    st.markdown(
        f'<span class="cp-level {recommendation["class"]}">{recommendation["level"]}</span>'
        + (f"　**推荐分：** {recommendation['score']:.1f}" if recommendation["score"] is not None else ""),
        unsafe_allow_html=True,
    )
    decision = job.get("job_decision") or {}
    ai_match = ai_match_view(job)
    render_text_list("匹配证据", ai_match.get("matched_evidence") or decision.get("matched_reasons"), empty="暂无明确匹配证据")
    render_text_list("缺失能力", ai_match.get("missing_requirements") or decision.get("missing_requirements"), empty="暂无明显缺口")
    render_text_list("风险点", ai_match.get("risk_points") or ai_match.get("risks") or decision.get("risks"), empty="暂无明显风险")
    render_text_list("简历动作", ai_match.get("resume_actions") or decision.get("resume_actions"), empty="暂无建议")
    render_text_list("面试重点", ai_match.get("interview_focus") or decision.get("interview_focus"), empty="暂无建议")


def render_job_detail_summary(job: dict):
    rows = [
        ("公司", display_company_name(job)),
        ("岗位", display_job_title(job)),
        ("薪资", salary_text(job)),
        ("经验", display_experience_text(job)),
        ("学历", clean_display_value(job.get("degree_display") or job.get("degree", ""))),
        ("福利", trim_display_text(job.get("welfare", ""), limit=220)),
        ("双休", extract_weekend_text(job)),
        ("公司地址", clean_display_value(job.get("company_address", ""))),
        ("工作地点", clean_display_value(job.get("location", ""))),
        ("发布时间", clean_display_value(job.get("posted_date", ""))),
        ("来源平台", platform_label(job.get("platform", ""))),
    ]
    for label, value in rows:
        if clean_display_value(value):
            st.markdown(f"**{label}：** {value}")
    requirements = compact_requirements(job, limit=800)
    if requirements:
        st.markdown("**招聘要求：**")
        st.write(requirements)


def render_agent_plan_summary(plan: dict):
    criteria = plan.get("criteria") or {}
    rows = [
        ("城市", plan.get("location")),
        ("主关键词", plan.get("keyword")),
        ("扩展关键词", "、".join(plan.get("expanded_keywords") or [])),
        ("使用平台", platform_label_text(plan.get("platforms"))),
        ("页数", plan.get("max_pages")),
        ("岗位类型", "、".join(plan.get("job_types") or [])),
        ("薪资", _criteria_salary_text(criteria)),
        ("经验", _criteria_experience_text(criteria)),
        ("学历", "、".join(criteria.get("degrees") or [])),
    ]
    for label, value in rows:
        if clean_display_value(value):
            st.markdown(f"**{label}：** {value}")


def _criteria_salary_text(criteria: dict) -> str:
    if criteria.get("min_salary_k") and criteria.get("max_salary_k"):
        return f"{criteria.get('min_salary_k')}K-{criteria.get('max_salary_k')}K"
    if criteria.get("min_salary_k"):
        return f"{criteria.get('min_salary_k')}K 以上"
    if criteria.get("max_salary_k"):
        return f"{criteria.get('max_salary_k')}K 以下"
    if criteria.get("salary_preferred_max_k") is not None:
        return f"偏好 {criteria.get('salary_preferred_max_k')}K 以下"
    return ""


def _criteria_experience_text(criteria: dict) -> str:
    if criteria.get("max_experience_years") is not None:
        return f"{criteria.get('max_experience_years')} 年以内"
    if criteria.get("experience_preferred_max_years") is not None:
        return f"偏好 {criteria.get('experience_preferred_max_years')} 年以内"
    return ""


def auto_rank_jobs_if_needed(resume_text: str, jobs: list[dict], profile: dict, plan: dict | None = None) -> list[dict]:
    if not resume_text.strip() or not jobs:
        return []
    signature = json.dumps(
        {
            "resume": resume_text_hash(resume_text),
            "jobs": [
                [job.get("platform"), job.get("job_id"), job.get("company"), job.get("title"), job.get("salary")]
                for job in jobs[:80]
            ],
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    if st.session_state.get("local_match_signature") == signature and st.session_state.get("ranked_jobs"):
        return annotate_workspace_job_actions(st.session_state["ranked_jobs"])
    if st.session_state.get("deep_match_signature") == signature and st.session_state.get("ranked_jobs"):
        return annotate_workspace_job_actions(st.session_state["ranked_jobs"])
    ranked = rank_jobs_for_resume(resume_text, jobs, top_n=None, ai_top_n=0)
    ranked = rank_jobs_with_decisions(ranked, profile, plan or {})
    ranked = annotate_workspace_job_actions(ranked)
    st.session_state["ranked_jobs"] = ranked
    st.session_state["current_jobs"] = ranked
    st.session_state["active_search_source"] = "matched"
    st.session_state["local_match_signature"] = signature
    st.session_state.setdefault("search_summary", {})["recommendation_level_counts"] = count_recommendation_levels(ranked)
    return ranked


def annotate_workspace_job_actions(jobs: list[dict]) -> list[dict]:
    return annotate_jobs_with_actions(
        jobs,
        feedback=load_job_feedback(limit=500),
        applications=load_application_records(limit=500),
    )


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


def render_workspace_app():
    workspace_options = ["任务配置", "岗位结果", "沟通行动", "记录记忆"]
    if st.session_state.get("career_workspace_v1") not in workspace_options:
        st.session_state["career_workspace_v1"] = "任务配置"
    workspace = st.segmented_control(
        "工作区",
        workspace_options,
        key="career_workspace_v1",
    )
    st.caption("按流程切换工作区，当前页面只显示本阶段需要的控件。")

    if workspace == "任务配置":
        render_config_workspace()
    elif workspace == "岗位结果":
        render_results_workspace()
    elif workspace == "沟通行动":
        render_action_workspace()
    else:
        render_memory_workspace()


def render_config_workspace():
    platform_options = [
        code for code in PLATFORM_ORDER
        if code in PLATFORM_LABELS and code not in {"boss_drission", "boss_cookie"}
    ]
    left, right = st.columns([0.9, 1.45], gap="large")

    with left:
        with st.container(border=True):
            st.markdown('<div class="cp-panel-title">简历与目标</div>', unsafe_allow_html=True)
            uploaded = st.file_uploader(
                "上传简历",
                type=[ext.lstrip(".") for ext in sorted(SUPPORTED_EXTENSIONS)],
                help="可选。上传后用于画像、匹配和话术证据。",
                key="ws_resume_upload",
            )
            if uploaded:
                resume_path = save_upload(uploaded)
                try:
                    resume_text = extract_resume_text(resume_path)
                except Exception as exc:
                    st.error(str(exc))
                    return
                if not resume_text.strip():
                    st.error("没有从简历中解析出文字。")
                    return
                cache_key = resume_cache_key(uploaded, resume_text)
                st.session_state["resume_text_current"] = resume_text
                st.session_state["resume_text_hash"] = resume_text_hash(resume_text)
                if st.session_state.get("resume_profile_key") != cache_key:
                    with st.status("正在解析简历画像...", expanded=False) as status:
                        profile = build_resume_profile(resume_text)
                        st.session_state["resume_profile"] = profile
                        st.session_state["resume_profile_key"] = cache_key
                        status.update(label="简历画像已解析", state="complete")
                st.success(f"已读取简历：{uploaded.name}")
            elif st.session_state.get("resume_text_current"):
                st.info("已保留本轮上传的简历画像。")
            else:
                st.markdown('<div class="cp-muted">可以先不上传简历，直接配置任务。</div>', unsafe_allow_html=True)

            if st.session_state.get("resume_profile"):
                with st.expander("简历画像", expanded=False):
                    render_resume_profile_summary(st.session_state.get("resume_profile", {}))

        with st.container(border=True):
            st.markdown('<div class="cp-panel-title">快速 Agent 检索</div>', unsafe_allow_html=True)
            default_goal = DEFAULT_AGENT_GOAL
            if st.session_state.get("agent_goal") == OLD_DEFAULT_AGENT_GOAL:
                st.session_state["agent_goal"] = default_goal
            agent_goal = st.text_area(
                "求职目标",
                value=st.session_state.get("agent_goal", default_goal),
                height=104,
                key="ws_agent_goal",
            )
            allow_browser_login = st.checkbox(
                "允许打开 Boss 登录浏览器",
                value=False,
                key="ws_allow_boss_browser_login",
            )
            if st.button("启动 Agent 检索", type="primary", width="stretch", key="ws_run_agent"):
                st.session_state["agent_goal"] = agent_goal
                with st.status("Agent 正在检索岗位...", expanded=True) as status:
                    result = run_agent_search(
                        agent_goal,
                        st.session_state.get("resume_text_current") or None,
                        allow_browser_login=allow_browser_login,
                        progress_callback=make_status_progress(status),
                    )
                    status.update(label=f"Agent 检索完成，本次结果 {len(result.get('jobs', []))} 个", state="complete")
                _store_agent_result_for_workspace(result)
                st.session_state["career_workspace_v1"] = "岗位结果"
                st.rerun()

    with right:
        with st.container(border=True):
            render_outreach_task_panel(
                st.session_state.get("resume_profile", {}),
                platform_options=platform_options,
                use_browser_crawlers=bool(st.session_state.get("ws_use_browser_crawlers", False)),
                allow_browser_login=bool(st.session_state.get("ws_allow_boss_browser_login", False)),
            )

        with st.expander("手动搜索", expanded=False):
            keyword = st.text_input("搜索关键词", value="AI Agent", key="ws_keyword")
            city_col, page_col = st.columns(2)
            with city_col:
                location = st.text_input("城市", value="上海", key="ws_location")
            with page_col:
                max_pages = st.number_input("页数", min_value=1, max_value=10, value=2, key="ws_max_pages")
            job_types = st.multiselect("岗位类型", ["社招", "校招", "实习"], default=["社招", "校招"], key="ws_job_types")
            platforms = st.multiselect(
                "招聘平台",
                platform_options,
                default=[p for p in DEFAULT_PLATFORM_CODES if p in platform_options],
                key="ws_platforms",
                format_func=platform_label,
            )
            use_browser_crawlers = st.checkbox("启用浏览器列表采集", value=False, key="ws_use_browser_crawlers")
            min_salary_k, max_salary_k = st.slider("月薪范围（K）", 0, 100, (0, 20), key="ws_salary_range")
            criteria = {
                "job_types": job_types,
                "min_salary_k": min_salary_k if min_salary_k > 0 else None,
                "max_salary_k": max_salary_k if max_salary_k < 100 else None,
                "degrees": ["不限", "大专", "本科", "硕士", "博士"],
            }
            signature = json.dumps({
                "keyword": keyword,
                "location": location,
                "platforms": platforms,
                "max_pages": int(max_pages),
                "criteria": criteria,
            }, ensure_ascii=False, sort_keys=True)
            if st.button("按筛选检索", width="stretch", key="ws_manual_search"):
                with st.status("正在检索岗位...", expanded=True) as status:
                    jobs_found = run_search(
                        keyword,
                        location,
                        platforms,
                        max_pages,
                        criteria,
                        signature,
                        expand_keywords=True,
                        max_keywords=5,
                        enrich_details=True,
                        detail_limit=20,
                        use_browser_crawlers=use_browser_crawlers,
                        allow_browser_login=bool(st.session_state.get("ws_allow_boss_browser_login", False)),
                        progress_callback=make_status_progress(status),
                    )
                    status.update(label=f"检索完成，本次结果 {len(jobs_found)} 个", state="complete")
                st.session_state["career_workspace_v1"] = "岗位结果"
                st.rerun()

        with st.expander("导入岗位 JD / 链接", expanded=False):
            with st.form("ws_import_job_form"):
                title_col, company_col = st.columns(2)
                with title_col:
                    import_title = st.text_input("岗位名称", key="ws_import_title")
                with company_col:
                    import_company = st.text_input("公司名称", key="ws_import_company")
                location_col, salary_col = st.columns(2)
                with location_col:
                    import_location = st.text_input("工作地点", key="ws_import_location")
                with salary_col:
                    import_salary = st.text_input("薪资", key="ws_import_salary")
                import_url = st.text_input("岗位链接", key="ws_import_url")
                import_fetch_url = st.checkbox("尝试读取链接内容", value=True, key="ws_import_fetch_url")
                import_jd = st.text_area(
                    "岗位 JD",
                    height=180,
                    key="ws_import_jd",
                    placeholder="可以粘贴职位描述、任职要求、学历经验、福利等文本。",
                )
                submitted = st.form_submit_button("导入到当前结果", width="stretch")
            if submitted:
                if not any(value.strip() for value in (import_title, import_company, import_url, import_jd)):
                    st.warning("请至少填写岗位名称、公司、链接或 JD 文本中的一项。")
                else:
                    if import_fetch_url and import_url.strip():
                        with st.spinner("正在读取链接内容..."):
                            imported_job = build_job_from_url(
                                import_url,
                                title=import_title,
                                company=import_company,
                                location=import_location,
                                salary=import_salary,
                                jd_text=import_jd,
                            )
                    else:
                        imported_job = build_manual_job(
                            title=import_title,
                            company=import_company,
                            location=import_location,
                            salary=import_salary,
                            jd_text=import_jd,
                            url=import_url,
                        )
                    saved_job = save_imported_job(imported_job)
                    add_imported_job_to_workspace(saved_job)
                    st.success(f"已导入岗位：{saved_job.get('company', '')} {saved_job.get('title', '')}")
                    st.session_state["career_workspace_v1"] = "岗位结果"
                    st.rerun()


def render_results_workspace():
    jobs, db_jobs, summary = workspace_jobs()
    st.markdown('<div class="cp-panel-title">岗位结果</div>', unsafe_allow_html=True)
    metric_cols = st.columns(4)
    metric_cols[0].metric("当前结果", len(jobs))
    metric_cols[1].metric("数据库岗位", len(db_jobs))
    metric_cols[2].metric("原始候选", summary.get("search_raw_total", "-") if summary else "-")
    metric_cols[3].metric("最终展示", summary.get("search_final_total", len(jobs)) if summary else len(jobs))

    if st.session_state.get("last_search_label"):
        st.caption(
            f"{st.session_state.get('last_search_label')} / "
            f"搜索时间：{st.session_state.get('search_time', '')}"
        )
    if summary:
        with st.expander("搜索质量", expanded=False):
            quality = summary.get("search_field_quality") or {}
            if quality:
                st.caption(
                    f"字段质量均分：{quality.get('avg_score', 0)} / "
                    f"高质量岗位：{quality.get('high_quality', 0)} / "
                    f"总数：{quality.get('total', 0)}"
                )
            st.write("平台命中")
            st.dataframe(pd.DataFrame(dict_to_rows(summary.get("search_final_platform_counts", {}))), hide_index=True, width="stretch")
            job_quality = summary.get("search_job_quality") or {}
            if job_quality:
                st.write("岗位质量")
                st.caption(
                    f"置信度均分：{job_quality.get('avg_confidence', 0)} / "
                    f"统计岗位：{job_quality.get('total', 0)}"
                )
                label_counts = job_quality.get("label_counts") or {}
                if label_counts:
                    st.dataframe(pd.DataFrame(dict_to_rows(label_counts)), hide_index=True, width="stretch")
                field_confidence = job_quality.get("avg_field_confidence") or {}
                if field_confidence:
                    rows = [
                        {"字段": key, "平均置信度": value}
                        for key, value in field_confidence.items()
                    ]
                    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
            invalid = summary.get("search_invalid_jobs") or {}
            if invalid.get("total"):
                st.write("无效候选过滤")
                st.caption(f"已过滤：{invalid.get('total', 0)}")
                st.dataframe(pd.DataFrame(dict_to_rows(invalid.get("reason_counts", {}))), hide_index=True, width="stretch")
            duplicate = summary.get("search_duplicate_summary") or {}
            if duplicate.get("dropped"):
                st.write("去重摘要")
                st.caption(
                    f"输入 {duplicate.get('input', 0)} / "
                    f"保留 {duplicate.get('kept', 0)} / "
                    f"去重 {duplicate.get('dropped', 0)}"
                )
                st.dataframe(pd.DataFrame(dict_to_rows(duplicate.get("reason_counts", {}))), hide_index=True, width="stretch")
            st.caption(f"实际关键词：{', '.join(summary.get('search_keywords', []))}")

    if not jobs:
        st.warning("当前没有岗位结果。请先到“任务配置”工作区执行检索。")
        return

    if st.session_state.get("resume_text_current"):
        render_match_dashboard_panel(jobs)

    view_col, size_col = st.columns([1, 1])
    with view_col:
        result_view = st.segmented_control("结果视图", ["表格", "卡片"], default="表格", key="ws_result_view")
    with size_col:
        page_size = st.selectbox("每页数量", [10, 20, 30, 50], index=0, key="ws_result_page_size")
    total_pages = max(1, (len(jobs) + int(page_size) - 1) // int(page_size))
    page_num = st.number_input("页码", min_value=1, max_value=total_pages, value=1, key="ws_result_page")
    start = (int(page_num) - 1) * int(page_size)
    page_jobs = jobs[start:start + int(page_size)]
    st.caption(f"第 {int(page_num)}/{total_pages} 页，共 {len(jobs)} 个岗位")
    if result_view == "卡片":
        render_job_cards(page_jobs, limit=len(page_jobs), show_recommendation=bool(st.session_state.get("resume_text_current")), start_index=start + 1)
    else:
        render_job_table(page_jobs, len(page_jobs), show_recommendation=bool(st.session_state.get("resume_text_current")))


def render_match_dashboard_panel(jobs: list[dict]) -> None:
    dashboard = build_match_dashboard(jobs)
    with st.expander("匹配看板", expanded=True):
        metric_cols = st.columns(4)
        metric_cols[0].metric("已评估", dashboard.get("evaluated_count", 0))
        metric_cols[1].metric("平均匹配分", dashboard.get("avg_score", 0))
        metric_cols[2].metric("强/优先岗位", dashboard.get("high_match_count", 0))
        metric_cols[3].metric("字段质量均分", dashboard.get("avg_field_quality", 0))

        left, right = st.columns([1.25, 1], gap="large")
        with left:
            top_jobs = dashboard.get("top_jobs") or []
            if top_jobs:
                rows = [
                    {
                        "排名": item.get("rank"),
                        "推荐": item.get("level"),
                        "分数": item.get("score"),
                        "公司": item.get("company"),
                        "岗位": item.get("title"),
                        "来源": platform_label(item.get("platform", "")),
                        "命中": "；".join(item.get("matched_keywords") or []),
                        "缺口": "；".join(item.get("missing_keywords") or []),
                    }
                    for item in top_jobs
                ]
                st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
        with right:
            level_counts = dashboard.get("level_counts") or {}
            platform_counts = dashboard.get("platform_counts") or {}
            if level_counts:
                st.write("匹配等级")
                st.dataframe(pd.DataFrame(dict_to_rows(level_counts)), hide_index=True, width="stretch")
            if platform_counts:
                st.write("平台分布")
                st.dataframe(pd.DataFrame(dict_to_rows(platform_counts)), hide_index=True, width="stretch")
            missing = dashboard.get("top_missing_keywords") or []
            matched = dashboard.get("top_matched_keywords") or []
            if matched:
                st.caption(f"主要命中：{'、'.join(matched[:8])}")
            if missing:
                st.caption(f"主要缺口：{'、'.join(missing[:8])}")
            actions = (dashboard.get("action_summary") or {}).get("status_counts") or {}
            if actions:
                st.write("动作状态")
                st.dataframe(pd.DataFrame(dict_to_rows(actions)), hide_index=True, width="stretch")
        st.download_button(
            "下载匹配看板 JSON",
            json.dumps(dashboard, ensure_ascii=False, indent=2),
            file_name="careerpilot_match_dashboard.json",
            mime="application/json",
            width="stretch",
        )


def render_action_workspace():
    jobs, _, _ = workspace_jobs()
    ranked = st.session_state.get("ranked_jobs", [])
    source_jobs = ranked or jobs
    if not source_jobs:
        st.warning("还没有岗位可选。请先到“任务配置”或“岗位结果”工作区完成检索。")
        return

    st.markdown('<div class="cp-panel-title">沟通行动</div>', unsafe_allow_html=True)
    labels = [
        f"{i+1}. {job.get('company', '')} - {job.get('title', '')} ({job.get('location', '')})"
        for i, job in enumerate(source_jobs)
    ]
    selected_idx = st.selectbox("选择目标岗位", range(len(source_jobs)), format_func=lambda i: labels[i], key="ws_action_job_idx")
    selected_job = source_jobs[selected_idx]
    local_profile = st.session_state.get("resume_profile") or {}

    top, side = st.columns([1.35, 1], gap="large")
    with top:
        with st.expander("匹配结论", expanded=True):
            render_match_summary(selected_job)
        with st.expander("岗位详情", expanded=False):
            render_job_detail_summary(selected_job)
        with st.expander("本地行动建议", expanded=True):
            st.markdown(build_local_job_advice(selected_job, local_profile))
        render_boss_outreach_panel(selected_job, local_profile, st.session_state.get("active_outreach_task"))

    with side:
        resume_text = st.session_state.get("resume_text_current", "")
        with st.container(border=True):
            st.markdown('<div class="cp-panel-title">简历匹配与材料</div>', unsafe_allow_html=True)
            if not resume_text:
                st.markdown('<div class="cp-muted">上传简历后可生成简历优化、JD 差距和面试准备包。</div>', unsafe_allow_html=True)
            else:
                ai_top_n = st.selectbox("DeepSeek 精排数量", [0, 3, 5, 10], index=1, key="ws_ai_top_n")
                if st.button("精排当前结果", type="primary", width="stretch", key="ws_deep_match"):
                    with st.status("正在精排当前岗位...", expanded=True) as status:
                        ranked_jobs = rank_jobs_for_resume(
                            resume_text,
                            jobs,
                            top_n=None,
                            ai_top_n=int(ai_top_n),
                            progress_callback=make_status_progress(status),
                            resume_cache_key=st.session_state.get("resume_text_hash"),
                        )
                        ranked_jobs = rank_jobs_with_decisions(ranked_jobs, local_profile, (st.session_state.get("agent_result") or {}).get("plan", {}))
                        ranked_jobs = annotate_workspace_job_actions(ranked_jobs)
                        st.session_state["ranked_jobs"] = ranked_jobs
                        st.session_state["current_jobs"] = ranked_jobs
                        status.update(label="精排完成", state="complete")
                    st.rerun()
                if st.button("生成简历优化建议", width="stretch", key="ws_generate_advice"):
                    with st.spinner("正在生成建议..."):
                        st.session_state["advice"] = generate_resume_job_advice(resume_text, selected_job)
                if st.button("生成 JD 差距分析", width="stretch", key="ws_generate_gap"):
                    with st.spinner("正在生成差距分析..."):
                        st.session_state["gap_analysis"] = generate_job_gap_analysis(resume_text, selected_job)
                if st.button("生成面试准备包", width="stretch", key="ws_generate_pack"):
                    with st.spinner("正在生成面试准备包..."):
                        st.session_state["interview_pack"] = generate_interview_pack(resume_text, selected_job)

        for title, key in (("简历优化建议", "advice"), ("JD 差距分析", "gap_analysis"), ("面试准备包", "interview_pack")):
            if st.session_state.get(key):
                with st.expander(title, expanded=False):
                    st.markdown(st.session_state[key])


def render_memory_workspace():
    jobs, _, summary = workspace_jobs()
    agent_result = st.session_state.get("agent_result")
    left, right = st.columns([1.2, 1], gap="large")
    with left:
        with st.container(border=True):
            st.markdown('<div class="cp-panel-title">Agent 解释</div>', unsafe_allow_html=True)
            if agent_result:
                st.info(agent_result.get("agent_message", ""))
                render_agent_trace(agent_result, agent_result.get("summary", {}) or summary, jobs)
                if agent_result.get("report"):
                    st.download_button("下载 Agent 报告", agent_result["report"], file_name="CareerPilot_agent_search_report.md", width="stretch")
                with st.expander("搜索计划", expanded=False):
                    render_agent_plan_summary(agent_result.get("plan", {}))
            else:
                st.markdown('<div class="cp-empty">还没有 Agent 任务记录。</div>', unsafe_allow_html=True)
        with st.container(border=True):
            st.markdown('<div class="cp-panel-title">Agent 问答</div>', unsafe_allow_html=True)
            question = st.text_input("问当前搜索结果", key="ws_agent_question", disabled=not bool(agent_result))
            if st.button("询问 Agent", width="stretch", disabled=not bool(agent_result), key="ws_ask_agent") and question.strip():
                answer = answer_agent_question(question, agent_result)
                st.session_state.setdefault("agent_chat", []).append({"question": question, "answer": answer})
            for item in st.session_state.get("agent_chat", [])[-5:]:
                st.markdown(f"**你：** {item['question']}")
                st.markdown(item["answer"])
    with right:
        with st.container(border=True):
            st.markdown('<div class="cp-panel-title">记录与记忆</div>', unsafe_allow_html=True)
            runs = load_agent_runs(limit=8)
            if runs:
                st.dataframe(pd.DataFrame([
                    {
                        "任务ID": item.get("run_id", ""),
                        "状态": item.get("status", ""),
                        "岗位数": int(item.get("job_count") or 0),
                        "更新时间": item.get("updated_at", ""),
                    }
                    for item in runs
                ]), width="stretch", hide_index=True)
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


def workspace_jobs() -> tuple[list[dict], list[dict], dict]:
    db_jobs = load_jobs()
    current_jobs = st.session_state.get("current_jobs")
    summary = st.session_state.get("search_summary", {}) or {}
    if current_jobs is not None:
        display_platforms = st.session_state.get("result_display_platforms") or st.session_state.get("task_platforms") or DEFAULT_PLATFORM_CODES
        display_location = st.session_state.get("result_display_location")
        display_criteria = st.session_state.get("result_display_criteria") or st.session_state.get("task_criteria") or {}
        jobs = prepare_jobs_for_display(
            current_jobs,
            selected_platforms=display_platforms,
            location=display_location,
            criteria=display_criteria,
            already_filtered=True,
        )
    else:
        jobs = prepare_jobs_for_display(
            db_jobs,
            selected_platforms=DEFAULT_PLATFORM_CODES,
            location="上海",
            criteria={"job_types": ["社招", "校招"], "max_salary_k": 20, "max_experience_years": 1},
            already_filtered=False,
        )
    resume_text = st.session_state.get("resume_text_current", "")
    if resume_text.strip() and jobs and st.session_state.get("resume_profile"):
        jobs = auto_rank_jobs_if_needed(
            resume_text,
            jobs,
            st.session_state.get("resume_profile", {}),
            (st.session_state.get("agent_result") or {}).get("plan", {}),
        )
        if st.session_state.get("active_search_source") == "task":
            jobs = apply_task_match_threshold(jobs, st.session_state.get("active_outreach_task"))
    return jobs, db_jobs, summary


def _store_agent_result_for_workspace(result: dict) -> None:
    st.session_state["agent_result"] = result
    st.session_state["current_jobs"] = result.get("jobs", [])
    st.session_state["search_summary"] = result.get("summary", {})
    st.session_state["search_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    st.session_state["active_search_source"] = "agent"
    plan = result.get("plan", {})
    st.session_state["result_display_platforms"] = plan.get("platforms") or DEFAULT_PLATFORM_CODES
    st.session_state["result_display_location"] = plan.get("location")
    st.session_state["result_display_criteria"] = plan.get("criteria") or {}
    st.session_state["last_search_label"] = (
        f"{plan.get('location', '')} / {plan.get('keyword', '')} / "
        f"平台:{platform_label_text(plan.get('platforms', []))} / "
        f"页数:{int(plan.get('max_pages') or 1)} / "
        f"类型:{', '.join(plan.get('job_types', []))}"
    )
    if result.get("resume_profile"):
        st.session_state["resume_profile"] = result["resume_profile"]
    clear_search_outputs()
    reset_result_pagination()
    load_jobs.clear()


def main():
    inject_design_system()
    cfg = get_llm_config()
    render_header(cfg)
    render_workspace_app()
    return

    uploaded = None
    resume_text = ""
    criteria = {"job_types": ["社招", "校招"], "max_salary_k": 20, "max_experience_years": 1}

    left_col, center_col, right_col = st.columns([0.95, 2.7, 1.05], gap="large")

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
                current_resume_key = resume_cache_key(uploaded, resume_text)
                st.session_state["resume_text_hash"] = resume_text_hash(resume_text)
                st.session_state["resume_cache_key"] = current_resume_key
                st.success(f"已读取简历：{uploaded.name}，约 {len(resume_text)} 字符")
                if st.session_state.get("resume_profile_key") != current_resume_key:
                    with st.status("正在自动解析简历画像...", expanded=False) as status:
                        profile = build_resume_profile(resume_text)
                        st.session_state["resume_profile"] = profile
                        st.session_state["resume_profile_key"] = current_resume_key
                        status.update(label="简历画像已解析", state="complete")
                else:
                    st.caption("已命中简历画像缓存。")
                with st.expander("简历画像摘要", expanded=True):
                    render_resume_profile_summary(st.session_state.get("resume_profile", {}))
            else:
                st.markdown(
                    '<div class="cp-muted">可以先不上传简历直接检索；上传后推荐会更准。</div>',
                    unsafe_allow_html=True,
                )

            default_goal = DEFAULT_AGENT_GOAL
            if st.session_state.get("agent_goal") == OLD_DEFAULT_AGENT_GOAL:
                st.session_state["agent_goal"] = default_goal
            agent_goal = st.text_area(
                "求职目标",
                value=st.session_state.get("agent_goal", default_goal),
                height=104,
                help="例如：帮我找上海 AI Agent 岗位，我是去年毕业的，薪资 20K 以内，社招和校招都可以，双休优先，不要实习。",
            )
            run_agent = st.button("启动 Agent 检索", type="primary", width="stretch")
            st.caption("Boss 登录浏览器默认关闭；需要时请手动开启，并按页面提示完成登录。")

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
                max_pages = st.number_input(
                    "页数",
                    min_value=1,
                    max_value=10,
                    value=2,
                    help="默认抓 2 页。结果偏少时可以再往上加。",
                )

            job_types = st.multiselect(
                "岗位类型",
                ["社招", "校招", "实习"],
                default=["社招", "校招"],
                help="默认看社招和校招，排除实习。",
            )
            allow_browser_login = st.checkbox(
                "允许打开 Boss 登录浏览器",
                value=False,
                key="allow_boss_browser_login_v3",
                help="默认关闭。勾选后，已选择的 BOSS直聘会改走同一个登录浏览器窗口。",
            )
            if allow_browser_login:
                st.warning(
                    "已允许 Boss 登录浏览器：本次 BOSS直聘会复用同一个弹窗窗口完成登录和搜索。"
                    "登录态由平台控制，遇到手机号、验证码或登录失效时需要你手动处理。"
                )
            platform_options = [
                code for code in PLATFORM_ORDER
                if code in PLATFORM_LABELS and code not in {"boss_drission", "boss_cookie"}
            ]
            current_platforms = list(st.session_state.get("platforms_safe_v2", DEFAULT_PLATFORM_CODES))
            current_platforms = [p for p in current_platforms if p in platform_options]
            st.session_state["platforms_safe_v2"] = current_platforms
            platforms = st.multiselect(
                "招聘平台",
                platform_options,
                default=current_platforms,
                key="platforms_safe_v2",
                format_func=platform_label,
                help="默认只选 BOSS直聘、智联招聘、前程无忧。其他平台可手动勾选；Boss 登录浏览器需要单独授权。",
            )
            if not allow_browser_login and "boss_drission" in platforms:
                platforms = [p for p in platforms if p != "boss_drission"]
                st.warning("已忽略 BOSS直聘（登录浏览器）：未勾选“允许打开 Boss 登录浏览器”。")
            elif allow_browser_login and "boss" in platforms:
                st.info("本次 BOSS直聘会使用同一个登录浏览器窗口；提交后如需登录会弹出窗口。")

            with st.expander("高级采集与过滤", expanded=False):
                use_browser_crawlers = st.checkbox(
                    "启用浏览器列表采集（前程无忧/猎聘）",
                    value=False,
                    key="use_browser_crawlers_v2",
                    help="默认关闭，避免自动启动 Edge/Chrome。",
                )
                expand_keywords = st.checkbox("扩展关键词检索", value=True)
                max_keywords = st.number_input("最多扩展关键词数", min_value=1, max_value=8, value=5)
                enrich_details = st.checkbox("二次抓取详情页", value=True)
                detail_limit = st.number_input("详情抓取上限", min_value=0, max_value=100, value=20)
                min_salary_k, max_salary_k = st.slider("月薪范围（K）", 0, 100, (0, 20))
                max_experience_years = st.slider("最高经验要求（年）", 0, 10, 1)
                degrees = st.multiselect(
                    "最高可接受学历要求",
                    ["不限", "大专", "本科", "硕士", "博士"],
                    default=["不限", "大专", "本科", "硕士", "博士"],
                )
                weekend_only = st.checkbox("只看公开双休/待确认工作制", value=False)

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
                with st.status("正在按当前筛选检索...", expanded=True) as status:
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
                        progress_callback=make_status_progress(status),
                    )
                    status.update(label=f"检索完成，本次结果 {len(jobs_found)} 个", state="complete")
                st.success(f"已刷新，本次结果 {len(jobs_found)} 个")

            if manual_search:
                with st.status("正在按当前筛选检索...", expanded=True) as status:
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
                        progress_callback=make_status_progress(status),
                    )
                    status.update(label=f"检索完成，本次结果 {len(jobs_found)} 个", state="complete")
                st.success(f"检索完成，本次结果 {len(jobs_found)} 个")

        with st.container(border=True):
            render_outreach_task_panel(
                st.session_state.get("resume_profile", {}),
                platform_options=platform_options,
                use_browser_crawlers=use_browser_crawlers,
                allow_browser_login=allow_browser_login,
            )

    if run_agent:
        st.session_state["agent_goal"] = agent_goal
        with st.status("Agent 正在制定搜索计划并检索岗位...", expanded=True) as status:
            result = run_agent_search(
                agent_goal,
                resume_text or None,
                allow_browser_login=allow_browser_login,
                progress_callback=make_status_progress(status),
            )
            status.update(label=f"Agent 检索完成，本次结果 {len(result.get('jobs', []))} 个", state="complete")
        st.session_state["agent_result"] = result
        st.session_state["current_jobs"] = result.get("jobs", [])
        st.session_state["search_summary"] = result.get("summary", {})
        st.session_state["search_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        st.session_state["active_search_source"] = "agent"
        plan = result.get("plan", {})
        st.session_state["agent_search_signature"] = json.dumps(plan, ensure_ascii=False, sort_keys=True)
        st.session_state["last_search_label"] = (
            f"{plan.get('location', '')} / {plan.get('keyword', '')} / "
            f"平台:{platform_label_text(plan.get('platforms', []))} / "
            f"页数:{int(plan.get('max_pages') or 1)} / "
            f"类型:{', '.join(plan.get('job_types', []))}"
        )
        st.session_state["search_dirty"] = False
        clear_search_outputs()
        reset_result_pagination()
        if result.get("resume_profile"):
            st.session_state["resume_profile"] = result["resume_profile"]
        load_jobs.clear()
        st.toast(f"Agent 检索完成，本次结果 {len(result.get('jobs', []))} 个")

    agent_result = st.session_state.get("agent_result")
    db_jobs = load_jobs()
    current_jobs = st.session_state.get("current_jobs")
    if current_jobs is not None:
        if st.session_state.get("active_search_source") == "task":
            active_task = st.session_state.get("active_outreach_task") or {}
            display_platforms = st.session_state.get("task_platforms") or task_platforms(active_task)
            display_location = None
            display_criteria = st.session_state.get("task_criteria") or task_criteria(active_task)
        else:
            display_platforms = platforms
            display_location = location
            display_criteria = criteria
        jobs = prepare_jobs_for_display(
            current_jobs,
            selected_platforms=display_platforms,
            location=display_location,
            criteria=display_criteria,
            already_filtered=True,
        )
    else:
        jobs = prepare_jobs_for_display(
            db_jobs,
            selected_platforms=platforms,
            location=location,
            criteria=criteria,
            already_filtered=False,
        )

    if resume_text.strip() and jobs:
        profile_for_match = st.session_state.get("resume_profile") or {}
        if profile_for_match:
            jobs = auto_rank_jobs_if_needed(
                resume_text,
                jobs,
                profile_for_match,
                (agent_result or {}).get("plan", {}),
            )
        if st.session_state.get("active_search_source") == "task":
            jobs = apply_task_match_threshold(jobs, st.session_state.get("active_outreach_task"))

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

        if summary:
            selected_platforms = summary.get("selected_platforms") or []
            platform_fetch_counts = summary.get("search_platform_fetch_counts", {})
            if "boss" in selected_platforms and int(platform_fetch_counts.get("boss", 0)) == 0:
                st.warning(
                    "BOSS 这次没有拿到有效岗位，通常是没有登录态、被安全验证拦截，或者当前关键词/页数太浅。"
                    "想提升结果，优先把页数调到 2-3 页；确实需要时再手动开启并选择“BOSS直聘（登录浏览器）”。"
                )
            if int(summary.get("search_raw_total", 0) or 0) <= 10:
                st.info("本轮候选偏少，优先把页数提高到 2-3 页，再放宽薪资、明确经验上限或关键词。")

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
                    platform_rows = []
                    selected_platforms = summary.get("selected_platforms") or []
                    for code in platform_display_order(selected_platforms):
                        platform_rows.append({
                            "平台": platform_label(code),
                            "抓取候选": int((summary.get("search_platform_fetch_counts", {}) or {}).get(code, 0)),
                            "最终保留": int((summary.get("search_final_platform_counts", {}) or {}).get(code, 0)),
                        })
                    if platform_rows:
                        st.write("平台命中总览")
                        st.dataframe(pd.DataFrame(platform_rows), hide_index=True, width="stretch")
                    q1, q2 = st.columns(2)
                    with q1:
                        st.write("字段完整度")
                        st.dataframe(pd.DataFrame(dict_to_rows(summary.get("search_field_counts", {}))), hide_index=True, width="stretch")
                        st.write("详情抓取")
                        st.dataframe(pd.DataFrame(dict_to_rows(summary.get("search_detail_counts", {}))), hide_index=True, width="stretch")
                    with q2:
                        st.write("原始平台抓取")
                        st.dataframe(pd.DataFrame(dict_to_rows(summary.get("search_platform_fetch_counts", {}))), hide_index=True, width="stretch")
                        st.write("最终平台分布")
                        st.dataframe(pd.DataFrame(dict_to_rows(summary.get("search_final_platform_counts", {}))), hide_index=True, width="stretch")
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
            level_counts = count_recommendation_levels(jobs)
            st.caption(
                "推荐分布："
                + " / ".join(f"{level} {count}" for level, count in level_counts.items())
            )
            level_options = recommendation_level_options()
            selected_levels = st.multiselect(
                "按 Agent 推荐等级过滤",
                level_options,
                default=level_options,
                key="decision_level_filter",
            )
            jobs = [
                job for job in jobs
                if recommendation_view(job)["level"] in set(selected_levels)
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
                page_size = st.selectbox(
                    "每页数量",
                    [10, 20, 30, 50],
                    index=0,
                    key="result_page_size_v1",
                )

            total_pages = max(1, (len(jobs) + int(page_size) - 1) // int(page_size))
            current_page = int(st.session_state.get("result_page_v1", 1) or 1)
            current_page = max(1, min(current_page, total_pages))
            st.session_state["result_page_v1"] = current_page

            page_cols = st.columns([1, 1, 2])
            with page_cols[0]:
                page_num = st.number_input(
                    "页码",
                    min_value=1,
                    max_value=total_pages,
                    value=current_page,
                    step=1,
                    key="result_page_v1",
                )
            start = (int(page_num) - 1) * int(page_size)
            end = start + int(page_size)
            page_jobs = jobs[start:end]
            with page_cols[1]:
                st.caption(f"第 {int(page_num)}/{total_pages} 页")
            with page_cols[2]:
                st.caption(f"共 {len(jobs)} 个岗位，每页 {int(page_size)} 个")

            if result_view == "卡片":
                render_job_cards(
                    page_jobs,
                    limit=len(page_jobs),
                    show_recommendation=has_resume,
                    start_index=start + 1,
                )
            else:
                render_job_table(page_jobs, len(page_jobs), show_recommendation=has_resume)
        else:
            st.warning("当前条件下没有岗位结果。可以增加平台和页数，或放宽薪资、学历、明确经验上限等硬筛选后重新采集。")

        st.markdown('<div class="cp-panel-title">简历匹配与行动</div>', unsafe_allow_html=True)
        if not uploaded:
            st.markdown(
                '<div class="cp-empty">上传简历后，这里会开放岗位匹配、简历优化、面试建议和简历解析；未上传简历时仍可选择岗位生成 BOSS 沟通草稿。</div>',
                unsafe_allow_html=True,
            )
            if jobs:
                labels = [
                    f"{i+1}. {j.get('company', '')} - {j.get('title', '')} ({j.get('location', '')})"
                    for i, j in enumerate(jobs)
                ]
                selected_idx = st.selectbox(
                    "选择目标岗位",
                    range(len(jobs)),
                    format_func=lambda i: labels[i],
                    key="selected_job_idx_no_resume",
                )
                selected_job = jobs[selected_idx]
                with st.expander("岗位详情", expanded=False):
                    render_job_detail_summary(selected_job)
                local_profile = st.session_state.get("resume_profile") or {}
                with st.expander("本地行动建议", expanded=True):
                    st.markdown(build_local_job_advice(selected_job, local_profile))
                render_boss_outreach_panel(
                    selected_job,
                    local_profile,
                    st.session_state.get("active_outreach_task"),
                )
        else:
            tab_match, tab_advice, tab_resume = st.tabs(["岗位匹配", "行动建议", "简历解析"])

            with tab_match:
                col_a, col_b = st.columns([1, 1])
                with col_a:
                    top_n = st.number_input("展示 Top N", min_value=1, max_value=100, value=20)
                with col_b:
                    ai_top_n = st.selectbox(
                        "DeepSeek 精排数量",
                        [0, 3, 5, 10],
                        index=1,
                        help="默认只精排本地 Top 3，0 表示只做本地快速匹配。",
                    )

                if not jobs:
                    st.warning("还没有岗位。请先检索岗位。")
                else:
                    matched_with_ai = sum(1 for job in jobs if isinstance(ai_match_view(job).get("score"), (int, float)))
                    if matched_with_ai:
                        st.success(f"已完成本地快速匹配，并有 {matched_with_ai} 个岗位命中 DeepSeek 精排缓存/结果。")
                    else:
                        st.info("已根据简历完成本地快速匹配；需要更准时，再对排名靠前岗位做 DeepSeek 精排。")

                if jobs and st.button("DeepSeek 精排当前结果", type="primary", width="stretch"):
                    with st.status("正在精排当前岗位...", expanded=True) as status:
                        status.write(f"本地匹配已完成，准备精排 Top {int(ai_top_n)}")
                        ranked = rank_jobs_for_resume(
                            resume_text,
                            jobs,
                            top_n=int(top_n),
                            ai_top_n=int(ai_top_n),
                            progress_callback=make_status_progress(status),
                            resume_cache_key=st.session_state.get("resume_text_hash"),
                        )
                        profile = st.session_state.get("resume_profile") or build_resume_profile(resume_text)
                        ranked = rank_jobs_with_decisions(ranked, profile, (agent_result or {}).get("plan", {}))
                        ranked = annotate_workspace_job_actions(ranked)
                        st.session_state["resume_profile"] = profile
                        st.session_state["ranked_jobs"] = ranked
                        st.session_state["current_jobs"] = ranked
                        st.session_state["active_search_source"] = "matched"
                        st.session_state["deep_match_signature"] = st.session_state.get("local_match_signature")
                        st.session_state.setdefault("search_summary", {})["llm_rerank_requested"] = int(ai_top_n)
                        st.session_state.setdefault("search_summary", {})["llm_rerank_success"] = sum(
                            1 for job in ranked if isinstance(ai_match_view(job).get("score"), (int, float))
                        )
                        st.session_state.setdefault("search_summary", {})["recommendation_level_counts"] = count_recommendation_levels(ranked)
                        status.update(label="DeepSeek 精排完成", state="complete")
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

                    with st.expander("匹配结论", expanded=True):
                        render_match_summary(selected_job)

                    with st.expander("岗位详情", expanded=False):
                        render_job_detail_summary(selected_job)

                    with st.expander("开发者调试信息", expanded=False):
                        st.json({
                            "ai_match": ai_match_view(selected_job),
                            "job_decision": selected_job.get("job_decision", {}),
                            "job_raw": {k: v for k, v in selected_job.items() if k != "resume_match"},
                        }, expanded=False)

                    local_profile = st.session_state.get("resume_profile") or (agent_result or {}).get("resume_profile") or {}
                    local_advice = build_local_job_advice(selected_job, local_profile)
                    with st.expander("本地行动建议", expanded=True):
                        st.markdown(local_advice)
                        st.download_button(
                            "下载本地行动建议 Markdown",
                            local_advice,
                            file_name="CareerPilot_local_job_advice.md",
                        )

                    render_boss_outreach_panel(
                        selected_job,
                        local_profile,
                        st.session_state.get("active_outreach_task"),
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

                    action_cols = st.columns(3)
                    with action_cols[0]:
                        generate_advice = st.button("生成简历优化建议", type="primary", width="stretch")
                    with action_cols[1]:
                        generate_gap = st.button("生成 JD 差距分析", width="stretch")
                    with action_cols[2]:
                        generate_pack = st.button("生成面试准备包", width="stretch")

                    if generate_advice:
                        with st.spinner("DeepSeek 正在生成建议..."):
                            advice = generate_resume_job_advice(resume_text, selected_job)
                            st.session_state["advice"] = advice
                            safe_name = f"{selected_job.get('company','job')}_{selected_job.get('title','')}".replace("/", "_").replace(" ", "_")[:50]
                            OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
                            out = OUTPUT_DIR / f"resume_advice_{safe_name}.md"
                            out.write_text(advice, encoding="utf-8")
                            st.session_state["advice_path"] = str(out)

                    if generate_gap:
                        with st.spinner("DeepSeek 正在生成 JD 差距分析..."):
                            gap = generate_job_gap_analysis(resume_text, selected_job)
                            st.session_state["gap_analysis"] = gap
                            safe_name = f"{selected_job.get('company','job')}_{selected_job.get('title','')}".replace("/", "_").replace(" ", "_")[:50]
                            OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
                            out = OUTPUT_DIR / f"job_gap_analysis_{safe_name}.md"
                            out.write_text(gap, encoding="utf-8")
                            st.session_state["gap_analysis_path"] = str(out)

                    if generate_pack:
                        with st.spinner("DeepSeek 正在生成面试准备包..."):
                            pack = generate_interview_pack(resume_text, selected_job)
                            st.session_state["interview_pack"] = pack
                            safe_name = f"{selected_job.get('company','job')}_{selected_job.get('title','')}".replace("/", "_").replace(" ", "_")[:50]
                            OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
                            out = OUTPUT_DIR / f"interview_pack_{safe_name}.md"
                            out.write_text(pack, encoding="utf-8")
                            st.session_state["interview_pack_path"] = str(out)

                    if st.session_state.get("advice"):
                        st.markdown("### 简历优化建议")
                        st.markdown(st.session_state["advice"])
                        st.caption(f"已保存到：{st.session_state.get('advice_path')}")
                        st.download_button("下载建议 Markdown", st.session_state["advice"], file_name="resume_advice.md")
                    if st.session_state.get("gap_analysis"):
                        st.markdown("### JD 差距分析")
                        st.markdown(st.session_state["gap_analysis"])
                        st.caption(f"已保存到：{st.session_state.get('gap_analysis_path')}")
                        st.download_button("下载差距分析 Markdown", st.session_state["gap_analysis"], file_name="job_gap_analysis.md")
                    if st.session_state.get("interview_pack"):
                        st.markdown("### 面试准备包")
                        st.markdown(st.session_state["interview_pack"])
                        st.caption(f"已保存到：{st.session_state.get('interview_pack_path')}")
                        st.download_button("下载面试准备包 Markdown", st.session_state["interview_pack"], file_name="interview_pack.md")

            with tab_resume:
                st.write("上传简历后会自动解析画像，这里只展示可读摘要。")
                render_resume_profile_summary(st.session_state.get("resume_profile", {}))

                with st.expander("查看解析出的简历文本", expanded=False):
                    st.text_area("简历文本", resume_text, height=320)

                with st.expander("开发者调试信息", expanded=False):
                    st.json(st.session_state.get("resume_profile", {}), expanded=False)

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
                render_agent_trace(agent_result, agent_result.get("summary", {}) or summary, jobs)
                if agent_result.get("report"):
                    st.download_button(
                        "下载 Agent 报告",
                        agent_result["report"],
                        file_name="CareerPilot_agent_search_report.md",
                        width="stretch",
                    )
                with st.expander("搜索计划", expanded=False):
                    render_agent_plan_summary(agent_result.get("plan", {}))
                if agent_result.get("resume_profile"):
                    with st.expander("简历画像", expanded=False):
                        render_resume_profile_summary(agent_result.get("resume_profile", {}))
                with st.expander("开发者调试信息", expanded=False):
                    st.json({
                        "plan": agent_result.get("plan", {}),
                        "resume_profile": agent_result.get("resume_profile", {}),
                    }, expanded=False)
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
                            "岗位数": int(item.get("job_count") or 0),
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

