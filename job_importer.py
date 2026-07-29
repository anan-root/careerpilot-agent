"""Manual job import helpers for pasted JD text and job links."""

from __future__ import annotations

import hashlib
import re

import requests
from bs4 import BeautifulSoup

import db
from job_filters import enrich_job_fields
from job_schema import apply_job_schema

FIELD_ALIASES = {
    "title": ("岗位名称", "职位名称", "职位", "title"),
    "company": ("公司名称", "企业名称", "公司", "企业", "company"),
    "location": ("工作地点", "办公地点", "地点", "城市", "location"),
    "salary": ("薪资范围", "薪资待遇", "薪资", "薪酬", "月薪", "salary"),
    "degree": ("学历要求", "学历", "degree"),
    "experience": ("经验要求", "工作经验", "经验", "experience"),
    "skills": ("技术栈", "技能要求", "核心技能", "技能", "skills"),
    "welfare": ("福利待遇", "福利", "welfare"),
    "url": ("岗位链接", "职位链接", "链接", "url", "source_url"),
}

DESCRIPTION_LABELS = ("岗位职责", "工作职责", "职位描述", "职责描述", "工作内容")
REQUIREMENT_LABELS = ("任职要求", "岗位要求", "职位要求", "任职资格", "任职条件", "能力要求")
STOP_SECTION_LABELS = (
    *DESCRIPTION_LABELS,
    *REQUIREMENT_LABELS,
    "公司介绍",
    "公司简介",
    "福利待遇",
    "工作地点",
    "办公地点",
    "薪资待遇",
    "薪资",
)

COMMON_CITIES = (
    "北京",
    "上海",
    "广州",
    "深圳",
    "杭州",
    "南京",
    "苏州",
    "成都",
    "武汉",
    "西安",
    "天津",
    "重庆",
    "长沙",
    "合肥",
    "郑州",
    "青岛",
    "厦门",
    "宁波",
    "无锡",
    "远程",
)

TECH_TERMS = (
    "Python",
    "Java",
    "JavaScript",
    "TypeScript",
    "SQL",
    "FastAPI",
    "Flask",
    "Django",
    "React",
    "Vue",
    "Docker",
    "Linux",
    "MySQL",
    "PostgreSQL",
    "Redis",
    "Elasticsearch",
    "LangChain",
    "LangGraph",
    "RAG",
    "Agent",
    "LLM",
    "大模型",
    "智能体",
    "向量检索",
    "Embedding",
    "BM25",
    "Rerank",
    "Prompt",
    "MCP",
    "Function Calling",
    "LoRA",
    "Transformer",
)

PLATFORM_URL_PATTERNS = (
    ("boss", (r"zhipin\.com", r"bosszhipin\.com")),
    ("zhilian", (r"zhaopin\.com", r"zhipin\.zhaopin\.com")),
    ("51job", (r"51job\.com", r"jobs\.51job\.com")),
    ("liepin", (r"liepin\.com",)),
    ("lagou", (r"lagou\.com",)),
    ("nowcoder", (r"nowcoder\.com",)),
)

COMPANY_SUFFIXES = (
    "有限公司",
    "股份有限公司",
    "集团",
    "科技",
    "网络",
    "信息",
    "智能",
    "数据",
    "软件",
    "咨询",
)


def parse_manual_job_text(text: str, *, source_url: str = "") -> dict:
    """Build a normalized manual job from pasted JD text."""
    return build_manual_job(jd_text=text, url=source_url)


def build_job_from_url(
    url: str,
    *,
    title: str = "",
    company: str = "",
    location: str = "",
    salary: str = "",
    jd_text: str = "",
    timeout: int = 10,
) -> dict:
    """Fetch a job page and build a canonical manual job record."""
    page = fetch_job_page_text(url, timeout=timeout)
    combined_text = "\n\n".join(
        part for part in (page.get("text", ""), jd_text)
        if str(part or "").strip()
    )
    job = build_manual_job(
        title=title,
        company=company,
        location=location,
        salary=salary,
        jd_text=combined_text,
        url=url,
        platform=detect_platform_from_url(url),
    )
    job["detail_status"] = page.get("status", "") or job.get("detail_status", "")
    job["import_fetch_error"] = page.get("error", "")
    return apply_job_schema(enrich_job_fields(job))


def detect_platform_from_url(url: str) -> str:
    """Infer recruitment platform code from a source URL."""
    text = str(url or "").lower()
    for platform, patterns in PLATFORM_URL_PATTERNS:
        if any(re.search(pattern, text) for pattern in patterns):
            return platform
    return ""


def fetch_job_page_text(url: str, *, timeout: int = 10) -> dict[str, str]:
    """Return readable text extracted from a job URL."""
    clean_url = str(url or "").strip()
    if not clean_url:
        return {"text": "", "status": "url_missing", "error": ""}
    if not re.match(r"^https?://", clean_url, flags=re.I):
        return {"text": "", "status": "url_invalid", "error": "仅支持 http/https 链接"}

    try:
        response = requests.get(
            clean_url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/126.0 Safari/537.36"
                ),
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            },
            timeout=max(1, int(timeout)),
        )
        response.raise_for_status()
    except Exception as exc:
        return {"text": "", "status": "url_fetch_failed", "error": exc.__class__.__name__}

    text = extract_text_from_html(response.text)
    return {
        "text": text,
        "status": "url_fetched" if text else "url_empty",
        "error": "",
    }


def extract_text_from_html(html: str, *, limit: int = 20000) -> str:
    """Extract useful visible text from a job page HTML document."""
    soup = BeautifulSoup(str(html or ""), "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()

    parts: list[str] = []
    for selector in (
        "meta[property='og:title']",
        "meta[name='title']",
        "title",
        "meta[property='og:description']",
        "meta[name='description']",
        "h1",
        "h2",
        "h3",
        "main",
        "article",
        "body",
    ):
        for node in soup.select(selector):
            if node.name == "meta":
                text = node.get("content", "")
            else:
                text = node.get_text("\n", strip=True)
            _append_unique_text(parts, text)

    return _normalize_text("\n".join(parts))[:limit]


def build_manual_job(
    *,
    title: str = "",
    company: str = "",
    location: str = "",
    salary: str = "",
    jd_text: str = "",
    url: str = "",
    platform: str = "",
) -> dict:
    """Build a canonical job record from optional fields and free-form JD text."""
    full_jd = _normalize_text(jd_text)
    parsed = _parse_text_fields(full_jd)
    source_url = _first_non_empty(url, parsed.get("url"))
    source_platform = _first_non_empty(platform, detect_platform_from_url(source_url), "manual")
    description = _first_non_empty(parsed.get("description"), full_jd)
    requirements = _first_non_empty(parsed.get("requirements"), full_jd)

    job = {
        "platform": source_platform,
        "job_id": "",
        "title": _first_non_empty(title, parsed.get("title"), _infer_title(full_jd, source_platform)),
        "company": _first_non_empty(company, parsed.get("company"), _extract_company(full_jd, source_platform)),
        "location": _first_non_empty(location, parsed.get("location"), _extract_location(full_jd)),
        "salary": _first_non_empty(salary, parsed.get("salary"), _extract_salary(full_jd)),
        "job_type": _extract_job_type(full_jd),
        "description": description,
        "requirements": requirements,
        "skills": _first_non_empty(parsed.get("skills"), _extract_skills(full_jd)),
        "degree": _first_non_empty(parsed.get("degree"), _extract_degree(full_jd)),
        "experience": _first_non_empty(parsed.get("experience"), _extract_experience(full_jd)),
        "company_size": "",
        "company_industry": "",
        "company_stage": "",
        "welfare": _first_non_empty(parsed.get("welfare"), _extract_welfare(full_jd)),
        "company_address": _first_non_empty(parsed.get("location"), _extract_location(full_jd)),
        "url": source_url,
        "source_url": source_url,
        "posted_date": "",
        "crawl_status": "manual_import",
        "crawl_keyword": "",
        "detail_status": "manual_text" if full_jd else "manual_fields",
        "detail_source_url": source_url,
        "full_jd": full_jd,
        "import_source_platform": source_platform,
    }
    job["job_id"] = _manual_job_id(job, full_jd)
    enrich_job_fields(job)
    return apply_job_schema(job)


def save_imported_job(job: dict) -> dict:
    """Store an imported job in SQLite and return the job with db_id attached."""
    current = apply_job_schema(enrich_job_fields(dict(job)))
    row_id = db.insert_job(
        platform=current.get("platform", "manual"),
        title=current.get("title", ""),
        company=current.get("company", ""),
        job_id=current.get("job_id", ""),
        location=current.get("location", ""),
        salary=current.get("salary", ""),
        job_type=current.get("job_type", ""),
        description=current.get("description", ""),
        requirements=current.get("requirements", ""),
        url=current.get("url", ""),
        posted_date=current.get("posted_date", ""),
        skills=current.get("skills", ""),
        degree=current.get("degree", ""),
        experience=current.get("experience", ""),
        company_size=current.get("company_size", ""),
        company_industry=current.get("company_industry", ""),
        company_stage=current.get("company_stage", ""),
        welfare=current.get("welfare", ""),
        full_jd=current.get("full_jd", ""),
        source_url=current.get("source_url", ""),
        company_address=current.get("company_address", ""),
        crawl_status=current.get("crawl_status", ""),
        crawl_keyword=current.get("crawl_keyword", ""),
        detail_status=current.get("detail_status", ""),
        detail_source_url=current.get("detail_source_url", ""),
    )
    if row_id:
        current["db_id"] = row_id
    return current


def _parse_text_fields(text: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip().strip("-*# \t")
        if not line:
            continue
        match = re.match(r"^([A-Za-z_\u4e00-\u9fff]{2,12})\s*[:：]\s*(.+)$", line)
        if not match:
            continue
        label, value = match.group(1).strip(), match.group(2).strip()
        field = _field_for_label(label)
        if field and value and field not in fields:
            fields[field] = value

    fields.setdefault("description", _extract_section(text, DESCRIPTION_LABELS))
    fields.setdefault("requirements", _extract_section(text, REQUIREMENT_LABELS))
    fields.setdefault("url", _extract_url(text))
    fields.setdefault("company", _extract_company(text, detect_platform_from_url(fields.get("url", ""))))
    fields.setdefault("title", _infer_title(text, ""))
    fields.setdefault("salary", _extract_salary(text))
    fields.setdefault("location", _extract_location(text))
    return {key: value for key, value in fields.items() if value}


def _field_for_label(label: str) -> str:
    normalized = label.strip().lower()
    for field, aliases in FIELD_ALIASES.items():
        if normalized in {alias.lower() for alias in aliases}:
            return field
    return ""


def _extract_section(text: str, labels: tuple[str, ...]) -> str:
    if not text:
        return ""
    label_pattern = "|".join(re.escape(label) for label in labels)
    stop_pattern = "|".join(re.escape(label) for label in STOP_SECTION_LABELS)
    pattern = rf"(?:^|\n)\s*(?:{label_pattern})\s*[:：]?\s*(.*?)(?=\n\s*(?:{stop_pattern})\s*[:：]?|\Z)"
    match = re.search(pattern, text, flags=re.S)
    if not match:
        return ""
    return _normalize_text(match.group(1))


def _extract_salary(text: str) -> str:
    patterns = (
        r"\d+(?:\.\d+)?\s*[kK]\s*[-~—到至]\s*\d+(?:\.\d+)?\s*[kK](?:·\d+薪)?",
        r"\d+(?:\.\d+)?\s*[-~—到至]\s*\d+(?:\.\d+)?\s*[kK](?:·\d+薪)?",
        r"\d+(?:\.\d+)?\s*[-~—到至]\s*\d+(?:\.\d+)?\s*万(?:/月|/年|·\d+薪)?",
        r"\d+(?:\.\d+)?\s*万(?:/月|/年|·\d+薪)?",
        r"\d+\s*[-~—到至]\s*\d+\s*元/天",
        r"\d+\s*元/天",
        r"薪资面议|面议",
    )
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return re.sub(r"\s+", "", match.group(0))
    return ""


def _extract_location(text: str) -> str:
    for city in COMMON_CITIES:
        if city in text:
            return city
    return ""


def _extract_company(text: str, platform: str = "") -> str:
    patterns = (
        r"(?:公司名称|企业名称|公司|企业)\s*[:：]\s*([^\n]{2,60})",
        r"_([^\n_]{2,60}?)(?:招聘信息|招聘)",
        r"([^\n_]{2,60}?)(?:招聘信息|招聘)[_-]?(?:智联招聘|BOSS直聘|猎聘|前程无忧)?",
    )
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            value = _clean_company(match.group(1))
            if value:
                return value

    lines = _text_lines(text)
    for line in lines[:30]:
        clean = _clean_company(line)
        if not clean or len(clean) > 40:
            continue
        if any(suffix in clean for suffix in COMPANY_SUFFIXES):
            if clean not in COMMON_CITIES and not _looks_like_title(clean):
                return clean
    return ""


def _extract_degree(text: str) -> str:
    for degree in ("博士", "硕士", "研究生", "本科", "大专", "专科", "学历不限", "不限"):
        if degree in text:
            return "大专" if degree == "专科" else degree.replace("学历不限", "不限")
    return ""


def _extract_experience(text: str) -> str:
    if any(token in text for token in ("经验不限", "不限经验", "应届生", "应届毕业生", "接受应届")):
        return "经验不限"
    match = re.search(r"\d+\s*[-~—到至]\s*\d+\s*年", text)
    if match:
        return re.sub(r"\s+", "", match.group(0))
    match = re.search(r"\d+\s*年(?:以上|经验)?", text)
    if match:
        return re.sub(r"\s+", "", match.group(0))
    return ""


def _extract_job_type(text: str) -> str:
    if any(token in text for token in ("实习", "日常实习", "暑期实习")):
        return "实习"
    if any(token in text for token in ("校招", "校园招聘", "应届生", "应届毕业生")):
        return "校招"
    return "社招"


def _extract_skills(text: str) -> str:
    lower_text = text.lower()
    found = []
    for term in TECH_TERMS:
        if term.lower() in lower_text and term not in found:
            found.append(term)
    return ", ".join(found)


def _extract_welfare(text: str) -> str:
    found = []
    for term in ("双休", "五险一金", "年终奖", "带薪年假", "弹性工作", "远程", "不加班"):
        if term in text:
            found.append(term)
    return "、".join(found)


def _extract_url(text: str) -> str:
    match = re.search(r"https?://[^\s，。；;）)]+", text)
    return match.group(0) if match else ""


def _infer_title(text: str, platform: str = "") -> str:
    for line in text.splitlines():
        value = line.strip().strip("-*# \t")
        if not value or re.match(r"^[A-Za-z_\u4e00-\u9fff]{2,12}\s*[:：]", value):
            continue
        if "_" in value and any(token in value for token in ("招聘", "智联", "BOSS", "猎聘")):
            value = value.split("_", 1)[0].strip()
        value = re.sub(r"招聘(?:信息)?[-_]?.*$", "", value).strip()
        if value and not _looks_like_company(value):
            return value[:80]
    return ""


def _manual_job_id(job: dict, full_jd: str) -> str:
    parts = [
        str(job.get("platform") or "manual"),
        str(job.get("source_url") or ""),
        str(job.get("company") or ""),
        str(job.get("title") or ""),
        full_jd[:2000],
    ]
    digest = hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()[:16]
    return f"manual_{digest}"


def _first_non_empty(*values: object) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _normalize_text(text: str) -> str:
    return re.sub(r"\n{3,}", "\n\n", str(text or "").replace("\r\n", "\n")).strip()


def _append_unique_text(parts: list[str], text: str) -> None:
    for line in str(text or "").splitlines():
        value = re.sub(r"\s+", " ", line).strip()
        if value and value not in parts:
            parts.append(value)


def _text_lines(text: str) -> list[str]:
    return [
        re.sub(r"\s+", " ", line).strip().strip("-*# \t")
        for line in str(text or "").splitlines()
        if line.strip()
    ]


def _clean_company(value: str) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    text = re.sub(r"(招聘信息|招聘|直聘|官方|首页).*$", "", text).strip(" -_｜|")
    return text[:80]


def _looks_like_company(value: str) -> bool:
    text = str(value or "")
    return any(suffix in text for suffix in COMPANY_SUFFIXES)


def _looks_like_title(value: str) -> bool:
    text = str(value or "")
    return any(token in text for token in ("工程师", "开发", "算法", "产品", "运营", "实习", "专家", "经理"))
