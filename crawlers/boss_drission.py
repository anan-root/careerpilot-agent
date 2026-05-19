"""Boss直聘 crawler using DrissionPage (真实浏览器监听API响应).

Priority fallback when boss-cli is unavailable. Requires Chrome/Chromium installed.
Supports optional automatic login detection. Login is disabled by default so
callers must explicitly opt in before a Boss login page can be opened.

Install: pip install DrissionPage
"""

from __future__ import annotations

import time
import json
import random
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

CITY_CODES = {
    "武汉": "101200100", "北京": "101010100", "上海": "101020100",
    "杭州": "101210100", "深圳": "101280600", "广州": "101280100",
    "成都": "101270100", "南京": "101190100", "西安": "101110100",
    "合肥": "101220100", "重庆": "101040100", "天津": "101030100",
    "苏州": "101190400", "厦门": "101230200", "长沙": "101250100",
    "青岛": "101120200", "郑州": "101180100", "大连": "101070200",
    "宁波": "101210400", "福州": "101230100", "昆明": "101290100",
    "哈尔滨": "101050100", "济南": "101120100", "沈阳": "101070100",
    "珠海": "101280700", "佛山": "101280800", "东莞": "101281600",
}

USER_DATA_DIR = str(Path(__file__).parent.parent / "data" / ".boss_browser_profile")


def _check_login(page) -> bool:
    """Check if user is logged in on Boss直聘."""
    try:
        url = page.url
        if "user/?ka=header-login" in url or "/web/user/" in url:
            return False
        el = page.ele("css:.nav-figure img, css:.user-nav .figure, css:[class*='nav-info']", timeout=3)
        return el is not None
    except Exception:
        return False


def _ensure_login(page, *, login_timeout: int = 120) -> bool:
    """Ensure user is logged in. If not, open login page and wait for QR scan.

    Returns True if login succeeded, False if timed out.
    """
    page.get("https://www.zhipin.com/web/geek/job")
    time.sleep(3)

    if _check_login(page):
        logger.info("Boss DrissionPage: already logged in")
        return True

    logger.info("Boss DrissionPage: not logged in, opening login page...")
    page.get("https://www.zhipin.com/web/user/?ka=header-login")
    time.sleep(2)

    print("\n" + "=" * 50)
    print("  请在弹出的浏览器窗口里扫码登录 Boss直聘")
    print("  (用 Boss直聘 App 扫码，不是微信/QQ)")
    print("=" * 50 + "\n")

    checks = login_timeout // 2
    for i in range(checks):
        time.sleep(2)
        if _check_login(page):
            logger.info("Boss DrissionPage: login detected after %ds", (i + 1) * 2)
            return True
        if i % 5 == 0 and i > 0:
            print(f"  等待登录... ({(i + 1) * 2}秒)")

    logger.error("Boss DrissionPage: login timed out after %ds", login_timeout)
    return False


def search_boss_drission(
    keyword: str = "AI Agent",
    city: str = "上海",
    *,
    max_pages: int = 3,
    delay_range: tuple[float, float] = (3.0, 6.0),
    auto_login: bool = False,
) -> list[dict]:
    """Search Boss直聘 by intercepting API responses in a real browser.

    If auto_login is True, will detect login status and prompt user to scan
    a QR code if needed. Cookie persists across runs. If auto_login is False,
    the crawler only uses an already logged-in browser profile and exits when
    login is required.

    Returns normalized job dicts ready for db.insert_job().
    """
    try:
        from DrissionPage import ChromiumPage, ChromiumOptions
    except ImportError:
        logger.error("DrissionPage not installed. Run: pip install DrissionPage")
        return []

    city_code = CITY_CODES.get(city, "101200100")
    url = f"https://www.zhipin.com/web/geek/job?query={keyword}&city={city_code}"

    co = ChromiumOptions()
    co.set_user_data_path(USER_DATA_DIR)
    browser_path = _find_browser_path()
    if browser_path:
        co.set_browser_path(browser_path)
    if hasattr(co, "auto_port"):
        co.auto_port(True)
    co.set_argument("--disable-blink-features=AutomationControlled")
    co.set_argument("--no-sandbox")

    try:
        page = ChromiumPage(co)
    except Exception as e:
        logger.error("Failed to launch Chrome: %s", e)
        return []

    all_jobs: list[dict] = []

    try:
        if auto_login:
            if not _ensure_login(page):
                logger.error("Login failed, aborting")
                page.quit()
                return []
        else:
            page.get("https://www.zhipin.com/web/geek/job")
            time.sleep(2)
            if not _check_login(page):
                logger.info("Boss DrissionPage: login required; auto_login=False, aborting without login prompt")
                page.quit()
                return []

        for pg in range(1, max_pages + 1):
            page.listen.start("wapi/zpgeek/search/joblist")
            target = url if pg == 1 else f"{url}&page={pg}"
            page.get(target)

            try:
                packet = page.listen.wait(timeout=20)
            except Exception:
                logger.warning("Page %d: no API response captured", pg)
                break

            page.listen.stop()

            if not packet or not packet.response or not packet.response.body:
                logger.warning("Page %d: empty response", pg)
                break

            body = packet.response.body
            if isinstance(body, str):
                body = json.loads(body)

            if body.get("code") != 0:
                logger.warning("Page %d: API error code %s", pg, body.get("code"))
                break

            job_list = body.get("zpData", {}).get("jobList", [])
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

            logger.info("DrissionPage Boss: page %d got %d jobs", pg, len(job_list))

            if not body.get("zpData", {}).get("hasMore", False):
                break

            delay = random.uniform(*delay_range)
            time.sleep(delay)

    except Exception as e:
        logger.error("DrissionPage Boss error: %s", e)
    finally:
        try:
            page.quit()
        except Exception:
            pass

    logger.info("DrissionPage Boss: total %d jobs for '%s' in %s", len(all_jobs), keyword, city)
    return all_jobs


def fetch_job_detail(job_url: str) -> str:
    """Fetch full JD text from a job detail page."""
    try:
        from DrissionPage import ChromiumPage, ChromiumOptions
    except ImportError:
        return ""

    co = ChromiumOptions()
    co.set_user_data_path(USER_DATA_DIR)
    browser_path = _find_browser_path()
    if browser_path:
        co.set_browser_path(browser_path)
    if hasattr(co, "auto_port"):
        co.auto_port(True)
    co.set_argument("--disable-blink-features=AutomationControlled")

    try:
        page = ChromiumPage(co)
        page.get(job_url)
        time.sleep(2)
        jd_el = page.ele("css:.job-sec-text")
        jd_text = jd_el.text if jd_el else ""
        page.quit()
        return jd_text
    except Exception as e:
        logger.error("Failed to fetch JD from %s: %s", job_url, e)
        return ""


def _find_browser_path() -> str | None:
    try:
        from crawlers.browser_utils import find_chromium_path

        return find_chromium_path()
    except Exception:
        return None
