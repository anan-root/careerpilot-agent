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
from urllib.parse import quote

from crawlers.browser_utils import apply_browser_hardening

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
JOB_URL = "https://www.zhipin.com/web/geek/job"
LOGIN_URL = "https://www.zhipin.com/web/user/?ka=header-login"

LOGIN_URL_HINTS = ("web/user", "login", "passport", "security", "captcha", "verify")
LOGIN_TEXT_HINTS = ("登录", "验证码", "安全验证", "滑块", "短信验证")
LOGGED_IN_SELECTORS = (
    "css:.nav-figure img",
    "css:.user-nav .figure",
    "css:[class*='nav-info']",
    "css:[class*='user-info']",
)
LOGGED_OUT_SELECTORS = (
    "css:[class*='header-login']",
    "css:[href*='login']",
    "css:[class*='login-form']",
    "css:[class*='login-box']",
)


def _safe_text(value: object) -> str:
    return str(value or "").strip()


def _has_any_ele(page, selectors: tuple[str, ...], *, timeout: float = 1.0) -> bool:
    for selector in selectors:
        try:
            if page.ele(selector, timeout=timeout) is not None:
                return True
        except Exception:
            continue
    return False


def _login_state(page) -> str:
    """Return logged_in / logged_out / unknown for Boss直聘."""
    try:
        url = _safe_text(getattr(page, "url", ""))
        title = _safe_text(getattr(page, "title", ""))
        if any(hint in url for hint in LOGIN_URL_HINTS):
            return "logged_out"
        if _has_any_ele(page, LOGGED_IN_SELECTORS, timeout=1):
            return "logged_in"
        if any(hint in title for hint in LOGIN_TEXT_HINTS):
            return "logged_out"
        if _has_any_ele(page, LOGGED_OUT_SELECTORS, timeout=1):
            return "logged_out"
        return "unknown"
    except Exception:
        return "unknown"


def _check_login(page) -> bool:
    """Check if user is likely logged in on Boss直聘."""
    return _login_state(page) == "logged_in"


def _ensure_login(page, *, login_timeout: int = 120) -> bool:
    """Ensure user is logged in. If not, open login page and wait for QR scan.

    Returns True if login succeeded, False if timed out.
    """
    page.get(JOB_URL)
    time.sleep(2)

    if _check_login(page):
        logger.info("Boss DrissionPage: already logged in")
        return True

    # If the page is still settling, give it one more chance before forcing login.
    for _ in range(2):
        time.sleep(2)
        if _check_login(page):
            logger.info("Boss DrissionPage: login confirmed after refresh wait")
            return True

    logger.info("Boss DrissionPage: not logged in, opening login page...")
    page.get(LOGIN_URL)
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


def _response_suggests_login_issue(body: object) -> bool:
    if not isinstance(body, dict):
        return False

    code = str(body.get("code", ""))
    if code in {"401", "403", "419", "440", "1001", "1002"}:
        return True

    message = " ".join(
        _safe_text(body.get(key))
        for key in ("message", "msg", "desc", "description")
    )
    return any(token in message for token in (
        "登录", "login", "验证码", "安全验证", "访问受限", "cookie", "session", "授权", "验证",
    ))


def _read_joblist_packet(page, target: str, *, timeout: int = 20):
    page.listen.start("wapi/zpgeek/search/joblist")
    try:
        page.get(target)
        return page.listen.wait(timeout=timeout)
    finally:
        try:
            page.listen.stop()
        except Exception:
            pass


def _create_page():
    try:
        from DrissionPage import ChromiumPage, ChromiumOptions
    except ImportError:
        logger.error("DrissionPage not installed. Run: pip install DrissionPage")
        return None

    co = ChromiumOptions()
    co.set_user_data_path(USER_DATA_DIR)
    browser_path = _find_browser_path()
    if browser_path:
        co.set_browser_path(browser_path)
    if hasattr(co, "auto_port"):
        co.auto_port(True)
    apply_browser_hardening(co)

    try:
        return ChromiumPage(co)
    except Exception as e:
        logger.error("Failed to launch Chrome: %s", e)
        return None


def _search_keyword_with_page(
    page,
    keyword: str,
    city: str,
    *,
    max_pages: int,
    delay_range: tuple[float, float],
    auto_login: bool,
) -> tuple[list[dict], bool]:
    """Search one keyword in an existing Boss browser page.

    Returns (jobs, keep_browser_open). keep_browser_open is True when the
    browser is likely useful for manual login/session recovery.
    """
    city_code = CITY_CODES.get(city, "101020100")
    encoded_keyword = quote(str(keyword or "AI Agent").strip())
    url = f"{JOB_URL}?query={encoded_keyword}&city={city_code}"

    all_jobs: list[dict] = []
    keep_browser_open = False

    for pg in range(1, max_pages + 1):
        target = url if pg == 1 else f"{url}&page={pg}"
        body: dict | None = None

        for attempt in range(2):
            packet = _read_joblist_packet(page, target, timeout=20)

            if not packet or not getattr(packet, "response", None) or not packet.response.body:
                logger.warning("Page %d: no API response captured (attempt %d)", pg, attempt + 1)
                state = _login_state(page)
                if attempt == 0 and auto_login and state == "logged_out":
                    logger.warning("Page %d: login state is logged_out, retrying after re-auth", pg)
                    if not _ensure_login(page, login_timeout=45):
                        keep_browser_open = True
                        break
                    continue
                if auto_login and pg == 1:
                    keep_browser_open = True
                break

            body = packet.response.body
            if isinstance(body, str):
                try:
                    body = json.loads(body)
                except json.JSONDecodeError:
                    body = {"code": -1, "message": body}

            if body.get("code") == 0:
                break

            if _response_suggests_login_issue(body) and attempt == 0 and auto_login:
                logger.warning(
                    "Page %d: login/session issue detected, retrying after manual re-auth", pg
                )
                if not _ensure_login(page, login_timeout=45):
                    keep_browser_open = True
                    break
                continue
            break

        if not body:
            break

        if body.get("code") != 0:
            logger.warning("Page %d: API error code %s", pg, body.get("code"))
            if _response_suggests_login_issue(body):
                logger.warning(
                    "Page %d: Boss login/session may have expired; browser kept open for recovery.",
                    pg,
                )
                keep_browser_open = True
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

        logger.info("DrissionPage Boss: keyword '%s' page %d got %d jobs", keyword, pg, len(job_list))

        if not body.get("zpData", {}).get("hasMore", False):
            break

        delay = random.uniform(*delay_range)
        time.sleep(delay)

    return all_jobs, keep_browser_open


def search_boss_drission_batch(
    keywords: list[str],
    city: str = "上海",
    *,
    max_pages: int = 3,
    delay_range: tuple[float, float] = (3.0, 6.0),
    auto_login: bool = False,
) -> dict[str, list[dict]]:
    """Search multiple Boss keywords in one browser session."""
    normalized_keywords: list[str] = []
    for keyword in keywords or ["AI Agent"]:
        value = str(keyword or "").strip()
        if value and value not in normalized_keywords:
            normalized_keywords.append(value)
    if not normalized_keywords:
        normalized_keywords = ["AI Agent"]

    page = _create_page()
    if page is None:
        return {keyword: [] for keyword in normalized_keywords}

    should_quit = True
    results: dict[str, list[dict]] = {keyword: [] for keyword in normalized_keywords}

    try:
        if auto_login:
            if not _ensure_login(page):
                logger.warning(
                    "Boss DrissionPage: login not confirmed, browser left open for manual login."
                )
                should_quit = False
                return results
        else:
            page.get(JOB_URL)
            time.sleep(2)
            if _login_state(page) == "logged_out":
                logger.info(
                    "Boss DrissionPage: login required; auto_login=False, browser left open without prompt"
                )
                should_quit = False
                return results

        for index, keyword in enumerate(normalized_keywords):
            jobs, keep_open = _search_keyword_with_page(
                page,
                keyword,
                city,
                max_pages=max_pages,
                delay_range=delay_range,
                auto_login=auto_login,
            )
            results[keyword] = jobs
            if keep_open:
                should_quit = False
                break
            if index < len(normalized_keywords) - 1:
                time.sleep(random.uniform(2.0, 4.5))
    except Exception as e:
        logger.error("DrissionPage Boss batch error: %s", e)
    finally:
        if should_quit:
            try:
                page.quit()
            except Exception:
                pass

    total = sum(len(jobs) for jobs in results.values())
    logger.info("DrissionPage Boss: total %d jobs for %d keywords in %s", total, len(results), city)
    return results


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
    results = search_boss_drission_batch(
        [keyword],
        city,
        max_pages=max_pages,
        delay_range=delay_range,
        auto_login=auto_login,
    )
    all_jobs = results.get(str(keyword or "").strip() or "AI Agent", [])
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
    apply_browser_hardening(co)

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
