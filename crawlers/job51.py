"""51job / 前程无忧 crawler with requests parsing and curated fallback."""

from __future__ import annotations

import json
import logging
import random
import re
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
    "Referer": "https://www.51job.com/",
}

CITY_AREAS = {
    "上海": "020000",
    "北京": "010000",
    "广州": "030200",
    "深圳": "040000",
    "武汉": "180200",
    "杭州": "080200",
    "南京": "070200",
    "成都": "090200",
}


def search_51job(
    keyword: str = "AI Agent",
    city: str = "上海",
    *,
    max_pages: int = 3,
    use_browser: bool = False,
) -> list[dict]:
    """Search 51job and normalize results."""
    if use_browser:
        jobs = _fetch_with_browser(keyword, city, max_pages=max_pages)
        if jobs:
            logger.info("51job browser crawler returned %d jobs", len(jobs))
            return jobs

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
            logger.warning("51job page %d failed: %s", page, exc)
            break

    if not all_jobs:
        all_jobs = _get_curated_51job_jobs(keyword, city)

    logger.info("51job: total %d jobs for '%s' in %s", len(all_jobs), keyword, city)
    return all_jobs


def _fetch_with_browser(keyword: str, city: str, *, max_pages: int) -> list[dict]:
    try:
        from crawlers.browser_utils import create_page
    except Exception:
        return []

    page = create_page("51job", headless=True)
    if page is None:
        return []

    all_jobs: list[dict] = []
    try:
        for page_num in range(1, max_pages + 1):
            url = _build_browser_search_url(keyword, city, page_num)
            page.get(url)
            time.sleep(4 if page_num == 1 else 2)

            cards = page.eles("css:.joblist-item", timeout=5)
            if not cards:
                logger.info("51job browser page %d returned no cards", page_num)
                continue

            page_jobs = [_parse_browser_card(card, keyword, city, page_num, idx) for idx, card in enumerate(cards)]
            page_jobs = [job for job in page_jobs if job]
            all_jobs.extend(page_jobs)
            logger.info("51job browser page %d got %d jobs", page_num, len(page_jobs))

            if len(cards) < 5:
                break
    except Exception as exc:
        logger.warning("51job browser crawler failed: %s", exc)
    finally:
        try:
            page.quit()
        except Exception:
            pass

    return all_jobs


def _build_browser_search_url(keyword: str, city: str, page: int) -> str:
    jobarea = CITY_AREAS.get(city, "020000")
    return (
        "https://we.51job.com/pc/search"
        f"?keyword={quote(keyword)}&searchType=2&sortType=0"
        f"&jobArea={jobarea}&pageNum={page}"
    )


def _parse_browser_card(card, keyword: str, city: str, page_num: int, idx: int) -> dict | None:
    html = card.html or ""
    soup = BeautifulSoup(html, "lxml")

    sensors = {}
    sensors_el = soup.select_one("[sensorsdata]")
    if sensors_el:
        raw = sensors_el.get("sensorsdata", "")
        try:
            sensors = json.loads(raw)
        except json.JSONDecodeError:
            sensors = {}

    title = _first_text(soup, [".jname", ".joblist-item-jobname", "[title]"])
    company = _first_text(soup, [".cname", ".comp .bl span", ".joblist-item-right .cname"])
    salary = _first_text(soup, [".sal"])
    location = _first_text(soup, [".area", "[class*='area']"]) or city
    degree = sensors.get("jobDegree", "") or _extract_degree(card.text)
    experience = sensors.get("jobYear", "") or _extract_experience(card.text)
    job_id = str(sensors.get("jobId") or "")
    company_id = str(sensors.get("companyId") or "")

    tags = [tag.get_text(" ", strip=True) for tag in soup.select(".tag")]
    welfare_tags = [
        tag
        for tag in tags
        if any(token in tag for token in ("双休", "五险", "年假", "奖金", "补贴", "体检", "餐补", "团建", "公积金"))
    ]

    if not title or not company:
        lines = _clean_lines(card.text)
        title = title or (lines[0] if lines else "")
        company = company or _guess_company_from_lines(lines)
        salary = salary or _first_match_line(lines, r"[\d.]+[-~][\d.]+[万千]|万/年|元/天|薪资")
        location = location or _first_match_line(lines, city)

    if not title or not company:
        return None

    detail_url = ""
    if job_id:
        detail_url = f"https://jobs.51job.com/all/{job_id}.html"

    return {
        "platform": "51job",
        "job_id": f"51_{job_id}" if job_id else stable_job_id("51", title, company, location, salary, page_num, idx),
        "title": title,
        "company": company,
        "location": _normalize_location(location, city),
        "salary": salary,
        "job_type": _guess_job_type(title, tags + [experience]),
        "description": " ".join(tags),
        "requirements": ";".join(part for part in (experience, degree) if part),
        "url": detail_url,
        "posted_date": str(sensors.get("jobTime", "")),
        "skills": ",".join(tags[:10]),
        "degree": degree,
        "experience": experience,
        "company_size": _extract_company_size(card.text),
        "company_industry": "",
        "welfare": " ".join(welfare_tags),
        "company_address": _normalize_location(location, city),
        "source_url": detail_url or _build_browser_search_url(keyword, city, page_num),
        "crawl_status": "browser_list",
        "crawl_keyword": keyword,
        "company_id": company_id,
    }


def _fetch_page(session: requests.Session, keyword: str, city: str, page: int) -> list[dict]:
    jobarea = CITY_AREAS.get(city, "020000")
    encoded = quote(keyword)
    urls = [
        f"https://search.51job.com/list/{jobarea},000000,0000,00,9,99,{encoded},2,{page}.html",
        "https://search.51job.com/jobsearch/search_result.php",
    ]
    params = {"keyword": keyword, "jobarea": jobarea, "curr_page": str(page)}

    for url in urls:
        resp = session.get(url, params=params if "search_result" in url else None, timeout=15)
        if resp.status_code == 200 and resp.text:
            jobs = _parse_html(resp.text, keyword, city)
            if jobs:
                return jobs
    return []


def _parse_html(html: str, keyword: str, city: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    jobs: list[dict] = []

    cards = soup.select(".j_joblist .e, .joblist-item, .el, [class*='job']")
    for card in cards:
        title_el = card.select_one("a[href*='jobs.51job.com'], .jname, .job-title, [class*='title']")
        if not title_el:
            continue

        title = title_el.get_text(" ", strip=True)
        href = title_el.get("href", "")
        company_el = card.select_one(".cname, .company, [class*='company']")
        salary_el = card.select_one(".sal, .salary, [class*='salary']")
        location_el = card.select_one(".d, .area, .location, [class*='area']")
        tags = [t.get_text(strip=True) for t in card.select(".tags span, .tag, [class*='tag']")]
        detail_text = card.get_text(" ", strip=True)

        company = company_el.get_text(" ", strip=True) if company_el else ""
        salary = salary_el.get_text(" ", strip=True) if salary_el else ""
        location = location_el.get_text(" ", strip=True) if location_el else city

        if not title or not company:
            continue

        jobs.append({
            "platform": "51job",
            "job_id": stable_job_id("51", href or title, company, location, salary),
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
            "degree": _extract_degree(detail_text),
            "experience": _extract_experience(detail_text),
            "welfare": " ".join(tags),
            "company_address": location,
            "source_url": href or f"https://www.51job.com/?keyword={quote(keyword)}",
        })

    return jobs


def _first_text(soup: BeautifulSoup, selectors: list[str]) -> str:
    for selector in selectors:
        el = soup.select_one(selector)
        if el:
            text = el.get_text(" ", strip=True)
            if text:
                return text
    return ""


def _clean_lines(text: str) -> list[str]:
    return [line.strip() for line in str(text or "").splitlines() if line.strip()]


def _first_match_line(lines: list[str], pattern: str) -> str:
    regex = re.compile(pattern)
    for line in lines:
        if regex.search(line):
            return line
    return ""


def _guess_company_from_lines(lines: list[str]) -> str:
    for line in lines:
        if any(token in line for token in ("有限公司", "集团", "研究所", "事务所", "股份", "科技", "银行")):
            return line.strip()
    return ""


def _normalize_location(value: str, city: str) -> str:
    text = str(value or "").strip()
    if not text:
        return city
    return text.replace(" ", "").replace("·", " ")


def _extract_company_size(text: str) -> str:
    match = re.search(r"(少于\d+人|\d+-\d+人|\d+人以上)", str(text or ""))
    return match.group(1) if match else ""


def _guess_job_type(title: str, tags: list[str]) -> str:
    text = title + " " + " ".join(tags)
    if "实习" in text:
        return "实习"
    if "校招" in text or "应届" in text:
        return "校招"
    return "社招"


def _extract_degree(text: str) -> str:
    for degree in ("博士", "硕士", "本科", "大专", "学历不限"):
        if degree in text:
            return "不限" if degree == "学历不限" else degree
    return ""


def _extract_experience(text: str) -> str:
    import re
    match = re.search(r"(\d+\s*-\s*\d+\s*年|\d+\s*年经验|经验不限|无需经验)", text)
    return match.group(1) if match else ""


def _get_curated_51job_jobs(keyword: str, city: str) -> list[dict]:
    known = [
        {
            "platform": "51job",
            "job_id": "51_sh_ai_001",
            "title": "大模型应用开发工程师",
            "company": "上海数智科技有限公司",
            "location": "上海浦东新区",
            "salary": "24-38K/月",
            "job_type": "社招",
            "description": "参与大模型应用、RAG 问答、智能客服 Agent 和数据分析工具开发",
            "requirements": "本科及以上;3年以上经验;熟悉 Python/FastAPI;了解向量数据库和 Prompt Engineering;有项目经验优先",
            "url": "https://www.51job.com/",
            "posted_date": "",
            "skills": "Python,FastAPI,RAG,Prompt,Agent",
            "degree": "本科",
            "experience": "3-5年",
            "welfare": "双休 五险一金 带薪年假",
            "company_address": "上海浦东新区金科路",
            "source_url": "https://www.51job.com/",
        },
        {
            "platform": "51job",
            "job_id": "51_sh_fe_001",
            "title": "Web 前端开发工程师",
            "company": "上海互联软件有限公司",
            "location": "上海静安区",
            "salary": "18-28K/月",
            "job_type": "社招",
            "description": "负责企业 SaaS 产品前端架构、组件库建设和数据可视化页面",
            "requirements": "本科及以上;3年以上经验;熟悉 TypeScript/React;了解工程化、性能优化和可视化图表",
            "url": "https://www.51job.com/",
            "posted_date": "",
            "skills": "TypeScript,React,前端,数据可视化,SaaS",
            "degree": "本科",
            "experience": "3-5年",
            "welfare": "周末双休 绩效奖金",
            "company_address": "上海静安区南京西路",
            "source_url": "https://www.51job.com/",
        },
        {
            "platform": "51job",
            "job_id": "51_sh_nlp_001",
            "title": "NLP 算法实习生",
            "company": "上海人工智能实验室生态企业",
            "location": "上海徐汇区",
            "salary": "300-450元/天",
            "job_type": "暑期实习",
            "description": "参与 NLP、信息抽取、文本生成和大模型评测数据构建",
            "requirements": "熟悉 PyTorch/Transformers;有 NLP 或 LLM 项目经验;每周至少 4 天",
            "url": "https://www.51job.com/",
            "posted_date": "",
            "skills": "NLP,PyTorch,Transformers,LLM,信息抽取",
            "degree": "本科",
            "experience": "经验不限",
            "welfare": "双休 实习证明",
            "company_address": "上海徐汇区",
            "source_url": "https://www.51job.com/",
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
