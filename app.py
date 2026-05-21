"""Streamlit UI for CareerPilot resume matching and job advice."""

from __future__ import annotations

import json
import re
import tempfile
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
from platform_registry import (
    DEFAULT_PLATFORM_CODES,
    PLATFORM_LABELS,
    PLATFORM_ORDER,
    normalize_platform,
    platform_label,
    platform_label_text,
)

OUTPUT_DIR = Path(__file__).parent / "data" / "outputs"
DEFAULT_AGENT_GOAL = "帮我找上海 AI Agent 岗位，我是去年毕业的，薪资 20K 以内，社招和校招都可以，双休优先，不要实习。"
OLD_DEFAULT_AGENT_GOAL = "帮我找上海 AI Agent 社招，薪资 20K 以上，3 年以内，双休优先，不要实习不要校招。"


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
    return search_jobs_to_frame(jobs, show_recommendation=True)


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
    {"min": 90, "level": "王牌机会", "class": "gold"},
    {"min": 80, "level": "强烈推荐", "class": "orange"},
    {"min": 70, "level": "优先关注", "class": "purple"},
    {"min": 60, "level": "可以投递", "class": "blue"},
    {"min": 50, "level": "备选岗位", "class": "green"},
    {"min": 0, "level": "普通岗位", "class": "white"},
)

LEGACY_LEVEL_SCORES = {
    "强推": 85,
    "可投": 65,
    "谨慎": 52,
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
    legacy_level = clean_display_value(decision.get("level", ""))
    score = parse_recommendation_score(decision.get("score"))
    if score is None:
        score = parse_recommendation_score(match.get("score"))
    if score is None and legacy_level in LEGACY_LEVEL_SCORES:
        score = float(LEGACY_LEVEL_SCORES[legacy_level])
    if score is None:
        return {"level": "未评估", "score": None, "class": "white"}
    for tier in RECOMMENDATION_TIERS:
        if score >= tier["min"]:
            return {"level": tier["level"], "score": score, "class": tier["class"]}
    return {"level": "普通岗位", "score": score, "class": "white"}


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
        reasons = decision.get("matched_reasons", [])[:3]
        risks = decision.get("risks", [])[:3]
        resume_actions = decision.get("resume_actions", [])[:2]
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
            ("推荐理由", "；".join(reasons) if show_recommendation else ""),
            ("风险提醒", "；".join(risks) if show_recommendation else ""),
            ("简历动作", "；".join(resume_actions) if show_recommendation else ""),
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
        f"{location} / {keyword} / 平台:{platform_label_text(platforms)} / "
        f"页数:{int(max_pages)} / 类型:{', '.join(criteria.get('job_types') or ['全部'])}"
    )
    st.session_state["search_dirty"] = False
    clear_search_outputs()
    reset_result_pagination()
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
        "强推": "strong",
        "可投": "ok",
        "谨慎": "warn",
        "不建议": "no",
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
                st.success(f"已读取简历：{uploaded.name}，约 {len(resume_text)} 字符")
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
            result = run_agent_search(
                agent_goal,
                resume_text or None,
                allow_browser_login=allow_browser_login,
            )
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
        jobs = prepare_jobs_for_display(
            current_jobs,
            selected_platforms=platforms,
            location=location,
            criteria=criteria,
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

