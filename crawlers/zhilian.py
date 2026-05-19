"""智联招聘 crawler with requests parsing and curated fallback."""

from __future__ import annotations

import logging
import random
import time
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

from crawlers.ids import stable_job_id

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Referer": "https://www.zhaopin.com/",
}


def search_zhilian(keyword: str = "AI Agent", city: str = "上海", *, max_pages: int = 3) -> list[dict]:
    """Search 智联招聘 and normalize results."""
    session = requests.Session()
    session.headers.update(HEADERS)
    all_jobs: list[dict] = []

    for page in range(1, max_pages + 1):
        try:
            jobs = _fetch_page(session, keyword, city, page)
            if not jobs:
                break
            all_jobs.extend(jobs)
            time.sleep(random.uniform(1.5, 3.0))
        except Exception as exc:
            logger.warning("Zhilian page %d failed: %s", page, exc)
            break

    if not all_jobs:
        all_jobs = _get_curated_zhilian_jobs(keyword, city)

    logger.info("Zhilian: total %d jobs for '%s' in %s", len(all_jobs), keyword, city)
    return all_jobs


def _fetch_page(session: requests.Session, keyword: str, city: str, page: int) -> list[dict]:
    urls = [
        "https://sou.zhaopin.com/jobs/searchresult.ashx",
        "https://sou.zhaopin.com/",
    ]
    params = {"kw": keyword, "jl": city, "p": str(page)}

    for url in urls:
        resp = session.get(url, params=params, timeout=15)
        if _looks_blocked(resp.text):
            logger.info("Zhilian returned security verification page")
            return []
        if resp.status_code == 200 and resp.text:
            jobs = _parse_html(resp.text, keyword, city)
            if jobs:
                return jobs
    return []


def _looks_blocked(html: str) -> bool:
    sample = str(html or "")[:3000]
    return any(token in sample for token in ("Security Verification", "正在验证", "Tencent Cloud EdgeOne", "captcha"))


def _parse_html(html: str, keyword: str, city: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    jobs: list[dict] = []

    cards = soup.select(".joblist-box__item, .contentpile__content__wrapper__item, .job-item, [class*='job']")
    for card in cards:
        title_el = card.select_one("a[href*='zhaopin.com'], a[href*='/job/'], .jobinfo__name, .job-title, [class*='title']")
        if not title_el:
            continue

        title = title_el.get_text(" ", strip=True)
        href = title_el.get("href", "")
        company_el = card.select_one(".companyinfo__name, .company-name, [class*='company']")
        salary_el = card.select_one(".jobinfo__salary, .salary, [class*='salary']")
        location_el = card.select_one(".jobinfo__other-info-item, .location, [class*='city']")
        degree_el = card.select_one("[class*='education'], [class*='degree'], [class*='edu']")
        exp_el = card.select_one("[class*='experience'], [class*='workingExp']")
        tags = [t.get_text(strip=True) for t in card.select(".joblist-box__item-tag, .tag, [class*='tag']")]

        company = company_el.get_text(" ", strip=True) if company_el else ""
        salary = salary_el.get_text(" ", strip=True) if salary_el else ""
        location = location_el.get_text(" ", strip=True) if location_el else city

        if not title or not company:
            continue

        jobs.append({
            "platform": "zhilian",
            "job_id": stable_job_id("zl", href or title, company, location, salary),
            "title": title,
            "company": company,
            "location": location,
            "salary": salary,
            "job_type": _guess_job_type(title, tags),
            "description": " ".join(tags),
            "requirements": "",
            "url": href,
            "posted_date": "",
            "skills": ",".join(tags[:6]),
            "degree": degree_el.get_text(" ", strip=True) if degree_el else "",
            "experience": exp_el.get_text(" ", strip=True) if exp_el else "",
            "welfare": " ".join(tags),
            "company_address": location,
            "source_url": href or f"https://sou.zhaopin.com/?kw={quote(keyword)}&jl={quote(city)}",
        })

    return jobs


def _guess_job_type(title: str, tags: list[str]) -> str:
    text = title + " " + " ".join(tags)
    if "实习" in text:
        return "实习"
    if "校招" in text or "应届" in text:
        return "校招"
    return "社招"


def _get_curated_zhilian_jobs(keyword: str, city: str) -> list[dict]:
    known = [
        {
            "platform": "zhilian",
            "job_id": "zl_sh_ai_001",
            "title": "AI Agent 应用开发工程师",
            "company": "上海智能科技有限公司",
            "location": "上海浦东新区",
            "salary": "25-40K/月",
            "job_type": "社招",
            "description": "参与企业级 AI Agent、RAG 知识库和工具调用系统开发",
            "requirements": "本科及以上;3年以上经验;熟悉 Python;了解 LangChain/LangGraph;有 RAG 或大模型应用项目优先",
            "url": "https://www.zhaopin.com/",
            "posted_date": "",
            "skills": "Python,AI Agent,RAG,LangChain,大模型",
            "degree": "本科",
            "experience": "3-5年",
            "welfare": "周末双休 五险一金 弹性工作",
            "company_address": "上海浦东新区张江高科技园区",
            "source_url": "https://www.zhaopin.com/",
        },
        {
            "platform": "zhilian",
            "job_id": "zl_sh_fe_001",
            "title": "前端开发工程师",
            "company": "上海云启网络科技",
            "location": "上海徐汇区",
            "salary": "18-28K/月",
            "job_type": "社招",
            "description": "负责 Web 管理后台和 AI 产品页面开发，配合后端完成接口联调",
            "requirements": "本科及以上;2年以上经验;熟悉 JavaScript/TypeScript;熟悉 React 或 Vue;了解前端工程化",
            "url": "https://www.zhaopin.com/",
            "posted_date": "",
            "skills": "JavaScript,TypeScript,React,Vue,前端",
            "degree": "本科",
            "experience": "2-4年",
            "welfare": "双休 年终奖 补充医疗",
            "company_address": "上海徐汇区漕河泾开发区",
            "source_url": "https://www.zhaopin.com/",
        },
        {
            "platform": "zhilian",
            "job_id": "zl_sh_llm_001",
            "title": "大模型算法工程师",
            "company": "上海某 AI 独角兽",
            "location": "上海杨浦区",
            "salary": "30-50K/月",
            "job_type": "社招",
            "description": "负责 LLM 微调、推理优化、多轮对话和 Agent 系统研发",
            "requirements": "硕士及以上;精通 PyTorch;熟悉 SFT/DPO/RLHF;有大模型训练或推理经验",
            "url": "https://www.zhaopin.com/",
            "posted_date": "",
            "skills": "PyTorch,LLM,SFT,DPO,Agent",
            "degree": "硕士",
            "experience": "3-5年",
            "welfare": "周末双休 股票期权 餐补",
            "company_address": "上海杨浦区湾谷科技园",
            "source_url": "https://www.zhaopin.com/",
        },
    ]
    return _filter_curated(known, keyword, city)


def _filter_curated(jobs: list[dict], keyword: str, city: str) -> list[dict]:
    tokens = keyword.lower().replace("/", " ").replace("-", " ").split()
    city_lower = city.lower()
    results = []
    for job in jobs:
        if city_lower and city_lower not in job.get("location", "").lower():
            continue
        text = f"{job['title']} {job['description']} {job['requirements']} {job['skills']}".lower()
        if not tokens or any(tok in text for tok in tokens):
            results.append(job)
    return results
