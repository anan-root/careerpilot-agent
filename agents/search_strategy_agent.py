"""Build safe, structured job search plans from natural-language goals."""

from __future__ import annotations

import re
from datetime import datetime

DEFAULT_LOCATION = "上海"
DEFAULT_PLATFORMS = ["zhilian", "51job", "liepin", "nowcoder"]
DEFAULT_DEGREES = ["不限", "大专", "本科", "硕士", "博士"]
DEFAULT_JOB_TYPES = ["社招"]

ROLE_KEYWORDS = [
    ("AI Agent", ("ai agent", "agent", "智能体")),
    ("大模型", ("大模型", "llm", "large language model")),
    ("RAG", ("rag", "检索增强", "知识库")),
    ("AI应用", ("ai应用", "ai 应用", "人工智能应用")),
    ("前端", ("前端", "react", "vue", "web")),
    ("后端", ("后端", "java", "python", "fastapi", "spring")),
    ("算法", ("算法", "机器学习", "深度学习", "nlp", "cv")),
]

CITY_NAMES = [
    "上海", "北京", "深圳", "广州", "杭州", "成都", "南京", "武汉", "苏州",
    "西安", "合肥", "重庆", "天津", "厦门", "长沙", "青岛", "郑州", "大连",
    "宁波", "福州", "昆明", "济南", "沈阳",
]


def build_search_plan(goal_text: str, resume_profile: dict | None = None) -> dict:
    """Convert a user's goal into a conservative executable search plan."""
    text = _normalize(goal_text)
    resume_profile = resume_profile or {}
    memory_context = dict(resume_profile.get("_memory_context") or {})

    keyword = _extract_keyword(text, resume_profile)
    expanded_keywords = _expand_keywords(keyword, text, resume_profile)
    location = _extract_location(text)
    job_types = _extract_job_types(text)
    platforms = _extract_platforms(text)
    criteria = _extract_criteria(text)
    excluded_terms = _merge_excluded_terms(_extract_excluded_terms(text), memory_context.get("negative_terms") or [])
    max_pages = _extract_max_pages(text)

    notes = _build_notes(text, job_types, criteria, platforms)

    return {
        "goal_text": goal_text.strip(),
        "keyword": keyword,
        "expanded_keywords": expanded_keywords,
        "location": location,
        "platforms": platforms,
        "job_types": job_types,
        "max_pages": max_pages,
        "criteria": criteria,
        "excluded_terms": excluded_terms,
        "safety": {
            "use_browser_crawlers": False,
            "allow_browser_login": False,
        },
        "notes": notes,
        "_memory_summary": str(memory_context.get("summary") or ""),
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def _extract_keyword(text: str, resume_profile: dict) -> str:
    for keyword, triggers in ROLE_KEYWORDS:
        if any(trigger.lower() in text.lower() for trigger in triggers):
            return keyword

    target_roles = resume_profile.get("target_roles") or []
    if target_roles:
        return str(target_roles[0]).strip() or "AI Agent"

    target_role = str(resume_profile.get("target_role") or "").strip()
    if target_role:
        return target_role

    match = re.search(r"(?:找|搜索|检索|看看|想要|目标)([^，。,.；;]{2,30})(?:岗位|职位|工作)", text)
    if match:
        return _clean_keyword(match.group(1))

    return "AI Agent"


def _expand_keywords(keyword: str, text: str, resume_profile: dict) -> list[str]:
    lower = f"{keyword} {text}".lower()
    candidates = [keyword]

    if any(token in lower for token in ("ai agent", "agent", "智能体")):
        candidates.extend(["大模型应用", "RAG", "LLM", "AI应用开发", "智能体"])
    elif any(token in lower for token in ("大模型", "llm", "aigc")):
        candidates.extend(["LLM", "大模型应用", "RAG", "AI应用开发", "AIGC"])
    elif "rag" in lower or "知识库" in lower:
        candidates.extend(["RAG", "大模型应用", "向量检索", "AI Agent"])
    elif "前端" in lower:
        candidates.extend(["前端开发", "Web前端", "React", "Vue"])
    elif "后端" in lower:
        candidates.extend(["后端开发", "Python", "Java", "FastAPI"])
    else:
        skills = resume_profile.get("skills") or []
        candidates.extend(str(skill) for skill in skills[:3])
        candidates.extend(["大模型", "AI应用"])

    return _unique_nonempty(candidates)[:5]


def _extract_location(text: str) -> str:
    for city in CITY_NAMES:
        if city in text:
            return city
    return DEFAULT_LOCATION


def _extract_job_types(text: str) -> list[str]:
    negative_intern = any(token in text for token in ("不要实习", "不看实习", "排除实习", "非实习"))
    negative_campus = any(token in text for token in ("不要校招", "不看校招", "排除校招", "非校招"))

    selected: list[str] = []
    if any(token in text for token in ("社招", "全职", "正式", "正式岗位")):
        selected.append("社招")
    if any(token in text for token in ("校招", "应届")) and not negative_campus:
        selected.append("校招")
    if "实习" in text and not negative_intern:
        selected.append("实习")

    if not selected:
        selected = list(DEFAULT_JOB_TYPES)

    if negative_intern:
        selected = [item for item in selected if item != "实习"]
    if negative_campus:
        selected = [item for item in selected if item != "校招"]
    if not selected:
        selected = ["社招"]
    return selected


def _extract_platforms(text: str) -> list[str]:
    mapping = {
        "智联": "zhilian",
        "zhaopin": "zhilian",
        "51job": "51job",
        "前程无忧": "51job",
        "猎聘": "liepin",
        "liepin": "liepin",
        "牛客": "nowcoder",
        "nowcoder": "nowcoder",
        "boss": "boss",
        "Boss": "boss",
        "BOSS": "boss",
    }
    selected = []
    for token, platform in mapping.items():
        if token in text and platform not in selected:
            selected.append(platform)
    return selected or list(DEFAULT_PLATFORMS)


def _extract_criteria(text: str) -> dict:
    min_salary, max_salary = _extract_salary_range(text)
    criteria = {
        "job_types": _extract_job_types(text),
        "min_salary_k": min_salary,
        "max_salary_k": max_salary,
        "max_experience_years": _extract_max_experience(text),
        "degrees": _extract_degrees(text),
        "weekend_only": any(token in text for token in ("双休", "周末双休", "五天工作制")),
    }
    return criteria


def _extract_salary_range(text: str) -> tuple[float | None, float | None]:
    match = re.search(r"(\d+(?:\.\d+)?)\s*[kK]\s*(?:以上|起|起步|及以上|\+)", text)
    if match:
        return float(match.group(1)), None

    match = re.search(r"(\d+(?:\.\d+)?)\s*(?:万|w|W)\s*(?:以上|起|起步|及以上|\+)", text)
    if match:
        return float(match.group(1)) * 10, None

    match = re.search(r"(\d+(?:\.\d+)?)\s*[-~到至]\s*(\d+(?:\.\d+)?)\s*[kK]", text)
    if match:
        return float(match.group(1)), float(match.group(2))

    match = re.search(r"(\d+(?:\.\d+)?)\s*[-~到至]\s*(\d+(?:\.\d+)?)\s*(?:万|w|W)", text)
    if match:
        return float(match.group(1)) * 10, float(match.group(2)) * 10

    match = re.search(r"月薪\s*(\d+(?:\.\d+)?)\s*(?:万|w|W)", text)
    if match:
        return float(match.group(1)) * 10, None

    return None, None


def _extract_max_experience(text: str) -> int | None:
    match = re.search(r"(\d+)\s*年\s*(?:以内|以下|内)", text)
    if match:
        return int(match.group(1))
    if any(token in text for token in ("经验不限", "不限经验", "无需经验")):
        return 0
    return None


def _extract_degrees(text: str) -> list[str]:
    if "博士" in text:
        return ["不限", "大专", "本科", "硕士", "博士"]
    if "硕士" in text or "研究生" in text:
        return ["不限", "大专", "本科", "硕士"]
    if "本科" in text:
        return ["不限", "大专", "本科"]
    if "大专" in text or "专科" in text:
        return ["不限", "大专"]
    return list(DEFAULT_DEGREES)


def _extract_excluded_terms(text: str) -> list[str]:
    terms = []
    mapping = {
        "外包": ("不要外包", "非外包", "排除外包", "不看外包"),
        "培训": ("不要培训", "培训机构", "不看培训"),
        "销售": ("不要销售", "不看销售"),
        "实习": ("不要实习", "不看实习", "排除实习"),
        "校招": ("不要校招", "不看校招", "排除校招"),
    }
    for term, triggers in mapping.items():
        if any(trigger in text for trigger in triggers):
            terms.append(term)
    return terms


def _merge_excluded_terms(explicit_terms: list[str], memory_terms: list[str]) -> list[str]:
    merged = []
    for term in [*explicit_terms, *memory_terms]:
        value = str(term or "").strip()
        if value and value not in merged:
            merged.append(value)
    return merged


def _extract_max_pages(text: str) -> int:
    match = re.search(r"(\d+)\s*页", text)
    if not match:
        return 1
    return max(1, min(int(match.group(1)), 10))


def _build_notes(text: str, job_types: list[str], criteria: dict, platforms: list[str]) -> list[str]:
    notes = ["默认不打开交互式浏览器，也不会自动打开 Boss 登录页。"]
    if "boss" in platforms:
        notes.append("Boss 普通模式只尝试非交互方式；需要真实登录浏览器时必须手动授权。")
    if criteria.get("weekend_only"):
        notes.append("双休字段不是所有平台列表页都会公开，系统会保留双休未知但其他条件匹配的岗位。")
    if job_types == ["社招"]:
        notes.append("已按社招/全职优先过滤，牛客等平台返回的实习岗位会被排除。")
    if any(token in text for token in ("外包", "培训")):
        notes.append("外包/培训会作为风险词记录，第一阶段先用于提示，后续 Ranking Agent 会做更严格过滤。")
    return notes


def _clean_keyword(value: str) -> str:
    text = value.strip()
    for token in ("的", "相关", "一些", "几个"):
        text = text.replace(token, "")
    return text.strip() or "AI Agent"


def _unique_nonempty(items: list[str]) -> list[str]:
    result = []
    for item in items:
        value = str(item or "").strip()
        if value and value not in result:
            result.append(value)
    return result


def _normalize(text: str) -> str:
    return str(text or "").strip()
