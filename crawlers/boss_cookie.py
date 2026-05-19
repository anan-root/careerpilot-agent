"""Boss直聘 crawler using direct API calls with user-provided cookies.

Use this when boss-cli login fails. Get cookies from browser DevTools:
1. Open Chrome -> zhipin.com -> login
2. Press F12 -> Network tab -> search for any job -> find request to "zpgeek"
3. Right-click the request -> Copy -> Copy as cURL
4. Extract the Cookie header value and paste into COOKIE_FILE or pass directly.
"""

from __future__ import annotations

import json
import time
import random
import logging
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

COOKIE_FILE = Path(__file__).parent.parent / "data" / ".boss_cookies.txt"

CITY_CODES = {
    "武汉": "101200100", "北京": "101010100", "上海": "101020100",
    "杭州": "101210100", "深圳": "101280600", "广州": "101280100",
    "成都": "101270100", "南京": "101190100", "合肥": "101220100",
    "西安": "101110100", "重庆": "101040100", "天津": "101030100",
    "苏州": "101190400", "厦门": "101230200", "长沙": "101250100",
    "青岛": "101120200", "郑州": "101180100", "大连": "101070200",
    "宁波": "101210400", "福州": "101230100",
}

SEARCH_URL = "https://www.zhipin.com/wapi/zpgeek/search/joblist.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Referer": "https://www.zhipin.com/web/geek/job",
    "Origin": "https://www.zhipin.com",
}


def load_cookie_string() -> str:
    """Load cookie string from file, or return empty."""
    if COOKIE_FILE.exists():
        return COOKIE_FILE.read_text(encoding="utf-8").strip()
    return ""


def save_cookie_string(cookie: str):
    """Save cookie string to file for reuse."""
    COOKIE_FILE.parent.mkdir(parents=True, exist_ok=True)
    COOKIE_FILE.write_text(cookie.strip(), encoding="utf-8")
    logger.info("Cookie saved to %s", COOKIE_FILE)


def search_boss_with_cookie(
    keyword: str = "AI",
    city: str = "合肥",
    cookie: str = "",
    *,
    max_pages: int = 5,
) -> list[dict]:
    """Search Boss直聘 using a cookie string from the browser.

    cookie: the full Cookie header value copied from browser DevTools.
    """
    if not cookie:
        cookie = load_cookie_string()
    if not cookie:
        logger.error("No cookie provided. See instructions in this file.")
        return []

    city_code = CITY_CODES.get(city, "101200100")
    session = requests.Session()
    session.headers.update(HEADERS)
    session.headers["Cookie"] = cookie

    all_jobs = []
    for page in range(1, max_pages + 1):
        params = {
            "scene": 1,
            "query": keyword,
            "city": city_code,
            "pageIndex": page,
            "pageSize": 30,
        }
        try:
            resp = session.get(SEARCH_URL, params=params, timeout=15)
            data = resp.json()
            if data.get("code") != 0:
                logger.warning("Boss API code=%s msg=%s", data.get("code"), data.get("message"))
                break

            job_list = data.get("zpData", {}).get("jobList", [])
            if not job_list:
                break

            for j in job_list:
                encrypt_boss_id = j.get("encryptBossId", "")
                security_id = j.get("securityId", "")
                chat_url = ""
                if encrypt_boss_id and security_id:
                    chat_url = f"https://www.zhipin.com/web/geek/chat?id={encrypt_boss_id}&securityId={security_id}"

                job = {
                    "platform": "boss",
                    "job_id": j.get("encryptJobId", ""),
                    "title": j.get("jobName", ""),
                    "company": j.get("brandName", ""),
                    "location": f"{j.get('cityName', '')} {j.get('areaDistrict', '')} {j.get('businessDistrict', '')}".strip(),
                    "salary": j.get("salaryDesc", ""),
                    "job_type": "实习" if "实习" in " ".join(j.get("jobLabels", [])) else "社招",
                    "description": j.get("jobName", ""),
                    "requirements": "",
                    "url": f"https://www.zhipin.com/job_detail/{j.get('encryptJobId', '')}.html",
                    "posted_date": str(j.get("lastModifyTime", "")),
                    "skills": ",".join(j.get("skills", [])),
                    "degree": j.get("jobDegree", ""),
                    "experience": j.get("jobExperience", ""),
                    "company_size": j.get("brandScaleName", ""),
                    "company_industry": j.get("brandIndustry", ""),
                    "company_stage": j.get("brandStageName", ""),
                    "welfare": ",".join(j.get("welfareList", [])),
                    "hr_name": j.get("bossName", ""),
                    "hr_title": j.get("bossTitle", ""),
                    "chat_url": chat_url,
                    "full_jd": "",
                    "source_url": f"https://www.zhipin.com/job_detail/{j.get('encryptJobId', '')}.html",
                }
                all_jobs.append(job)

            logger.info("Boss cookie crawler: page %d got %d jobs", page, len(job_list))
            has_more = data.get("zpData", {}).get("hasMore", False)
            if not has_more:
                break
            time.sleep(random.uniform(2.0, 4.0))

        except Exception as e:
            logger.error("Boss API error on page %d: %s", page, e)
            break

    logger.info("Boss cookie crawler: total %d jobs for '%s' in %s", len(all_jobs), keyword, city)
    return all_jobs
