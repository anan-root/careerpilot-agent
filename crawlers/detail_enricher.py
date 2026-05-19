"""Best-effort job detail page enrichment."""

from __future__ import annotations

import logging
import random
import re
import time

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}


def enrich_job_details(
    jobs: list[dict],
    *,
    limit: int = 30,
    delay_range: tuple[float, float] = (0.4, 1.0),
) -> list[dict]:
    """Fetch detail pages for the first N jobs and merge useful fields."""
    if not jobs or limit <= 0:
        for job in jobs:
            job.setdefault("detail_status", "skipped_disabled")
        return jobs

    session = requests.Session()
    session.headers.update(HEADERS)

    attempted = 0
    for job in jobs:
        if attempted >= limit:
            job.setdefault("detail_status", "skipped_limit")
            continue

        url = job.get("source_url") or job.get("url")
        if not url:
            job["detail_status"] = "skipped_no_url"
            continue

        platform = str(job.get("platform", "")).lower()
        if platform == "51job":
            # 51job detail pages usually trigger a slider challenge, while the
            # browser list page already exposes experience, degree, tags, salary.
            job["detail_status"] = "skipped_detail_block_prone"
            continue

        attempted += 1
        try:
            detail = fetch_detail(session, url, platform)
            if not detail:
                job["detail_status"] = "blocked_or_empty"
                continue
            _merge_detail(job, detail)
            job["detail_status"] = "fetched"
            job["detail_source_url"] = url
            time.sleep(random.uniform(*delay_range))
        except Exception as exc:
            logger.info("Detail fetch failed for %s: %s", url, exc)
            job["detail_status"] = "failed"

    return jobs


def fetch_detail(session: requests.Session, url: str, platform: str) -> dict:
    resp = session.get(url, timeout=15)
    if resp.status_code != 200 or not resp.text:
        return {}

    if _looks_blocked(resp.text):
        return {}

    soup = BeautifulSoup(resp.text, "lxml")
    text = soup.get_text("\n", strip=True)
    if len(text) < 80:
        return {}

    return {
        "full_jd": _extract_full_jd(soup, text, platform),
        "requirements": _extract_requirements(text),
        "degree": _extract_degree(text),
        "experience": _extract_experience(text),
        "welfare": _extract_welfare(soup, text),
        "company_address": _extract_address(text),
    }


def _merge_detail(job: dict, detail: dict) -> None:
    for key, value in detail.items():
        value = str(value or "").strip()
        if not value:
            continue

        if key == "welfare" and job.get("welfare"):
            merged = _merge_tokens(str(job.get("welfare", "")), value)
            job["welfare"] = merged
        elif key == "full_jd":
            if len(value) > len(str(job.get("full_jd") or "")):
                job["full_jd"] = value
            if len(value) > len(str(job.get("description") or "")):
                job["description"] = value[:1200]
        elif not job.get(key) or str(job.get(key)).startswith("列表页"):
            job[key] = value


def _merge_tokens(*values: str) -> str:
    tokens: list[str] = []
    for value in values:
        for token in re.split(r"[\s,，;/；|]+", value):
            token = token.strip()
            if token and token not in tokens:
                tokens.append(token)
    return " ".join(tokens)


def _looks_blocked(html: str) -> bool:
    sample = html[:3000]
    return any(
        token in sample
        for token in ("Security Verification", "正在验证", "滑动验证", "访问验证", "captcha", "acw_sc__v2")
    )


def _extract_full_jd(soup: BeautifulSoup, text: str, platform: str) -> str:
    selectors = [
        ".job-sec-text",
        ".job-description",
        ".job-intro-container",
        ".job-detail",
        ".job-msg",
        ".job_msg",
        ".bmsg",
        "[class*='job-description']",
        "[class*='job-intro']",
        "[class*='job-detail']",
    ]
    for selector in selectors:
        el = soup.select_one(selector)
        if el:
            jd = el.get_text("\n", strip=True)
            if len(jd) > 80:
                return jd[:5000]
    return text[:5000]


def _extract_requirements(text: str) -> str:
    patterns = [
        r"(任职要求[:：]?\s*[\s\S]{80,1200})",
        r"(岗位要求[:：]?\s*[\s\S]{80,1200})",
        r"(职位要求[:：]?\s*[\s\S]{80,1200})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return _trim_section(match.group(1))
    return ""


def _extract_degree(text: str) -> str:
    for degree in ("博士", "硕士", "统招本科", "本科", "大专", "学历不限", "不限学历"):
        if degree in text:
            if degree == "统招本科":
                return "本科"
            if degree in {"学历不限", "不限学历"}:
                return "不限"
            return degree
    return ""


def _extract_experience(text: str) -> str:
    match = re.search(r"(经验不限|不限经验|无需经验|应届生|在校生|\d+\s*-\s*\d+\s*年|\d+\s*年(?:及)?以上|\d+\s*年以内)", text)
    return match.group(1) if match else ""


def _extract_welfare(soup: BeautifulSoup, text: str) -> str:
    values = [
        tag.get_text(" ", strip=True)
        for tag in soup.select(".tag, .label, [class*='tag'], [class*='welfare']")
    ]
    values.append(text)

    found = []
    for token in (
        "周末双休",
        "双休",
        "五险一金",
        "带薪年假",
        "年终奖",
        "绩效奖金",
        "定期体检",
        "餐补",
        "交通补贴",
        "弹性工作",
        "大小周",
        "单休",
    ):
        if any(token in value for value in values) and token not in found:
            found.append(token)
    return " ".join(found)


def _extract_address(text: str) -> str:
    for pattern in (
        r"(?:工作地址|公司地址|上班地址|地址)[:：]?\s*([^\n]{6,80})",
        r"(上海[^\n]{4,60}(?:路|街|园|区|号|中心|广场|大厦))",
    ):
        match = re.search(pattern, text)
        if match:
            return match.group(1).strip()
    return ""


def _trim_section(text: str) -> str:
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    stop = re.search(r"\n(?:福利|工作地址|公司介绍|职位亮点|薪资)", text)
    if stop:
        text = text[: stop.start()]
    return text[:1200]
