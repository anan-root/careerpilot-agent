"""Job aggregator -- collects from all platforms, deduplicates, and stores.

Boss直聘 fallback chain:
  - boss: boss-cli -> cookie -> curated
  - boss_drission: explicit interactive browser login path

DrissionPage can open a real browser and Boss login screen, so it is only used
when the explicit boss_drission platform is selected and allowed.
"""

from __future__ import annotations

import logging
import re
import random
import time
from collections import Counter
from typing import Callable, Literal

import db
from job_filters import enrich_job_fields, filter_jobs
from platform_registry import DEFAULT_PLATFORM_CODES, normalize_platforms

logger = logging.getLogger(__name__)

Platform = Literal[
    "boss",
    "boss_drission",
    "boss_cookie",
    "nowcoder",
    "liepin",
    "zhilian",
    "51job",
    "lagou",
    "yingjiesheng",
    "guopin",
    "dingxiang",
    "jobonline",
    "curated",
]

DEFAULT_PLATFORMS: list[str] = list(DEFAULT_PLATFORM_CODES)
LAST_SEARCH_SUMMARY: dict = {}


def collect_all_jobs(
    keyword: str = "AI Agent",
    location: str = "上海",
    *,
    platforms: list[Platform] | None = None,
    max_pages: int = 3,
    job_types: list[str] | None = None,
    criteria: dict | None = None,
    expand_keywords: bool = True,
    max_keywords: int = 4,
    enrich_details: bool = True,
    detail_limit: int = 20,
    use_browser_crawlers: bool = False,
    allow_browser_login: bool = False,
    search_keywords: list[str] | None = None,
    progress_callback: Callable[[str], None] | None = None,
) -> list[dict]:
    """Collect jobs from selected platforms, store in DB, return list.

    Platform priority for "boss":
      1. boss-cli (fast, no browser, requires `boss login` once)
      2. cookie-based API (manual cookie extraction)
      3. curated data (offline fallback)

    DrissionPage is skipped unless allow_browser_login=True.
    51job/Liepin browser-list crawlers are skipped unless use_browser_crawlers=True.
    """
    if platforms is None:
        platforms = list(DEFAULT_PLATFORMS)
    else:
        platforms = normalize_platforms(platforms)
    platforms = _normalize_boss_browser_platforms(platforms, allow_browser_login=allow_browser_login)

    all_jobs: list[dict] = []
    keywords = (
        _normalize_keywords(search_keywords)
        if search_keywords
        else build_search_keywords(keyword, enabled=expand_keywords, max_keywords=max_keywords)
    )
    platform_fetch_counts: Counter[str] = Counter()
    platform_merged_counts: Counter[str] = Counter()
    keyword_fetch_counts: dict[str, int] = {}

    for platform_index, platform in enumerate(platforms):
        platform_jobs: list[dict] = []
        _emit_progress(progress_callback, f"开始检索平台：{platform}（{platform_index + 1}/{len(platforms)}）")
        if platform in {"boss", "boss_drission"} and allow_browser_login:
            platform_jobs = _fetch_boss_browser_keywords(
                platform,
                keywords,
                location,
                max_pages,
                use_browser_crawlers=use_browser_crawlers,
                keyword_fetch_counts=keyword_fetch_counts,
                platform_fetch_counts=platform_fetch_counts,
                progress_callback=progress_callback,
            )
        else:
            for keyword_index, search_keyword in enumerate(keywords):
                try:
                    _emit_progress(
                        progress_callback,
                        f"{platform} 正在搜索关键词：{search_keyword}（{keyword_index + 1}/{len(keywords)}）",
                    )
                    jobs = _fetch_platform(
                        platform,
                        search_keyword,
                        location,
                        max_pages,
                        use_browser_crawlers=use_browser_crawlers,
                        allow_browser_login=allow_browser_login,
                    )
                    for job in jobs:
                        job.setdefault("crawl_keyword", search_keyword)
                        job.setdefault("crawl_status", _default_crawl_status(platform, use_browser_crawlers))
                    logger.info("[%s] keyword='%s' fetched %d jobs", platform, search_keyword, len(jobs))
                    _emit_progress(progress_callback, f"{platform} / {search_keyword} 获取 {len(jobs)} 个候选")
                    keyword_fetch_counts[f"{platform}:{search_keyword}"] = len(jobs)
                    platform_fetch_counts[str(platform)] += len(jobs)
                    platform_jobs.extend(jobs)
                except Exception as e:
                    logger.error("[%s] keyword='%s' failed: %s", platform, search_keyword, e)
                    _emit_progress(progress_callback, f"{platform} / {search_keyword} 检索失败：{e}")
                    keyword_fetch_counts[f"{platform}:{search_keyword}"] = 0

                if keyword_index < len(keywords) - 1:
                    time.sleep(random.uniform(1.8, 3.8))

        if platform_jobs:
            platform_jobs = _deduplicate(platform_jobs)
        platform_merged_counts[str(platform)] = len(platform_jobs)
        logger.info("[%s] merged %d jobs from %d keywords", platform, len(platform_jobs), len(keywords))
        _emit_progress(progress_callback, f"{platform} 合并去重后 {len(platform_jobs)} 个候选")
        all_jobs.extend(platform_jobs)

        if platform_index < len(platforms) - 1:
            time.sleep(random.uniform(2.5, 5.0))

    criteria = dict(criteria or {})
    if job_types is not None:
        criteria["job_types"] = job_types

    platform_raw_counts = Counter(job.get("platform", "unknown") for job in all_jobs)
    if enrich_details:
        from crawlers.detail_enricher import enrich_job_details

        _emit_progress(progress_callback, f"开始二次抓取详情页，上限 {detail_limit} 个")
        all_jobs = enrich_job_details(all_jobs, limit=detail_limit)
    for job in all_jobs:
        enrich_job_fields(job)
    _emit_progress(progress_callback, f"开始按岗位类型、薪资、学历、经验等条件筛选 {len(all_jobs)} 个候选")
    filtered = filter_jobs(all_jobs, criteria)
    deduped = _deduplicate(filtered)
    _emit_progress(progress_callback, f"筛选后 {len(filtered)} 个，最终去重展示 {len(deduped)} 个")
    platform_final_counts = Counter(job.get("platform", "unknown") for job in deduped)
    platform_filtered_counts = Counter(job.get("platform", "unknown") for job in filtered)
    detail_counts = Counter(job.get("detail_status", "not_requested") for job in all_jobs)
    type_counts = Counter(job.get("normalized_job_type", "unknown") for job in all_jobs)
    type_filtered_counts = Counter(job.get("normalized_job_type", "unknown") for job in filtered)
    field_counts = _field_presence_counts(all_jobs)
    summary = {
        "selected_platforms": list(platforms),
        "search_keywords": keywords,
        "search_keyword_fetch_counts": keyword_fetch_counts,
        "search_platform_fetch_counts": dict(platform_fetch_counts),
        "search_platform_merged_counts": dict(platform_merged_counts),
        "search_raw_platform_counts": dict(platform_raw_counts),
        "search_filtered_platform_counts": dict(platform_filtered_counts),
        "search_final_platform_counts": dict(platform_final_counts),
        "search_type_counts": dict(type_counts),
        "search_filtered_type_counts": dict(type_filtered_counts),
        "search_field_counts": field_counts,
        "search_detail_counts": dict(detail_counts),
        "search_raw_total": len(all_jobs),
        "search_filtered_total": len(filtered),
        "search_final_total": len(deduped),
        "criteria": criteria,
        "use_browser_crawlers": use_browser_crawlers,
        "allow_browser_login": allow_browser_login,
    }
    global LAST_SEARCH_SUMMARY
    LAST_SEARCH_SUMMARY = summary
    for job in deduped:
        job.update(summary)
    logger.info("Total after dedup: %d (from %d raw)", len(deduped), len(all_jobs))

    stored = _store_jobs(deduped)
    return stored


def get_last_search_summary() -> dict:
    """Return the most recent aggregate search summary, including empty searches."""
    return dict(LAST_SEARCH_SUMMARY)


def build_search_keywords(keyword: str, *, enabled: bool = True, max_keywords: int = 4) -> list[str]:
    """Expand narrow terms into common Chinese recruitment keywords."""
    base = str(keyword or "").strip() or "AI Agent"
    if not enabled or max_keywords <= 1:
        return [base]

    lower = base.lower()
    candidates = [base]
    if any(token in lower for token in ("ai agent", "agent", "智能体")):
        candidates.extend(["大模型", "AI应用", "智能体", "RAG", "LLM"])
    elif any(token in lower for token in ("llm", "大模型", "aigc", "人工智能")):
        candidates.extend(["AI应用", "大模型", "LLM", "AIGC", "人工智能"])
    elif "前端" in base:
        candidates.extend(["前端开发", "Web前端", "React", "Vue"])
    else:
        candidates.extend(["大模型", "AI应用", "人工智能"])

    unique: list[str] = []
    for item in candidates:
        item = item.strip()
        if item and item not in unique:
            unique.append(item)
    return unique[:max_keywords]


def _normalize_keywords(keywords: list[str]) -> list[str]:
    unique: list[str] = []
    for keyword in keywords:
        value = str(keyword or "").strip()
        if value and value not in unique:
            unique.append(value)
    return unique or ["AI Agent"]


def _normalize_boss_browser_platforms(platforms: list[str], *, allow_browser_login: bool) -> list[str]:
    """Avoid launching both Boss fallback and Boss browser in the same search."""
    if not allow_browser_login:
        return platforms

    result: list[str] = []
    boss_seen = False
    for platform in platforms:
        if platform in {"boss", "boss_drission"}:
            if not boss_seen:
                result.append("boss")
                boss_seen = True
            continue
        result.append(platform)
    return result


def _fetch_boss_browser_keywords(
    platform: str,
    keywords: list[str],
    location: str,
    max_pages: int,
    *,
    use_browser_crawlers: bool,
    keyword_fetch_counts: dict[str, int],
    platform_fetch_counts: Counter[str],
    progress_callback: Callable[[str], None] | None = None,
) -> list[dict]:
    """Fetch all Boss keywords in one browser session."""
    from crawlers.boss_drission import search_boss_drission_batch

    try:
        _emit_progress(progress_callback, "Boss 登录浏览器路径已启用，正在复用已登录窗口或等待登录态确认")
        results = search_boss_drission_batch(
            keywords,
            location,
            max_pages=max_pages,
            auto_login=True,
            progress_callback=progress_callback,
        )
    except Exception as e:
        logger.error("[%s] Boss browser batch failed: %s", platform, e)
        for search_keyword in keywords:
            keyword_fetch_counts[f"{platform}:{search_keyword}"] = 0
        results = {}

    platform_jobs: list[dict] = []
    for search_keyword in keywords:
        jobs = results.get(search_keyword, [])
        if not jobs:
            try:
                _emit_progress(progress_callback, f"Boss / {search_keyword} 浏览器结果为空，尝试非交互兜底")
                jobs = _fetch_boss_with_fallback(
                    search_keyword,
                    location,
                    max_pages,
                    allow_browser_login=False,
                )
            except Exception as e:
                logger.error("[%s] keyword='%s' non-browser fallback failed: %s", platform, search_keyword, e)
                jobs = []
        for job in jobs:
            job.setdefault("crawl_keyword", search_keyword)
            job.setdefault("crawl_status", _default_crawl_status("boss_drission", use_browser_crawlers))
        logger.info("[%s] keyword='%s' fetched %d jobs", platform, search_keyword, len(jobs))
        _emit_progress(progress_callback, f"Boss / {search_keyword} 获取 {len(jobs)} 个候选")
        keyword_fetch_counts[f"{platform}:{search_keyword}"] = len(jobs)
        platform_fetch_counts[str(platform)] += len(jobs)
        platform_jobs.extend(jobs)
    return platform_jobs


def _emit_progress(callback: Callable[[str], None] | None, message: str) -> None:
    if callback is None:
        return
    try:
        callback(message)
    except Exception:
        logger.debug("Progress callback failed", exc_info=True)


def _fetch_platform(
    platform: str,
    keyword: str,
    location: str,
    max_pages: int,
    *,
    use_browser_crawlers: bool = False,
    allow_browser_login: bool = False,
) -> list[dict]:
    """Dispatch to the appropriate crawler with full fallback chain for Boss."""
    if platform == "boss":
        return _fetch_boss_with_fallback(
            keyword,
            location,
            max_pages,
            allow_browser_login=allow_browser_login,
        )

    elif platform == "boss_drission":
        if not allow_browser_login:
            logger.warning("Boss DrissionPage skipped; set allow_browser_login=True to open login browser.")
            return []
        from crawlers.boss_drission import search_boss_drission
        return search_boss_drission(keyword, location, max_pages=max_pages, auto_login=True)

    elif platform == "boss_cookie":
        from crawlers.boss_cookie import search_boss_with_cookie
        return search_boss_with_cookie(keyword, location, max_pages=max_pages)

    elif platform == "nowcoder":
        from crawlers.nowcoder import search_nowcoder
        return search_nowcoder(keyword, location, max_pages=max_pages)

    elif platform == "liepin":
        from crawlers.liepin import search_liepin
        return search_liepin(keyword, location, max_pages=max_pages, use_browser=use_browser_crawlers)

    elif platform == "zhilian":
        from crawlers.zhilian import search_zhilian
        return search_zhilian(keyword, location, max_pages=max_pages)

    elif platform == "51job":
        from crawlers.job51 import search_51job
        return search_51job(keyword, location, max_pages=max_pages, use_browser=use_browser_crawlers)

    elif platform in {"lagou", "yingjiesheng", "guopin", "dingxiang", "jobonline"}:
        from crawlers.generic_platforms import search_generic_platform
        return search_generic_platform(platform, keyword, location, max_pages=max_pages)

    elif platform == "curated":
        from crawlers.boss import search_boss_jobs
        return search_boss_jobs(keyword, location)

    else:
        logger.warning("Unknown platform: %s", platform)
        return []


def _fetch_boss_with_fallback(
    keyword: str,
    location: str,
    max_pages: int,
    *,
    allow_browser_login: bool = False,
) -> list[dict]:
    """Try non-interactive Boss直聘 crawlers in order: boss-cli -> cookie -> curated."""

    if allow_browser_login:
        try:
            from crawlers.boss_drission import search_boss_drission
            jobs = search_boss_drission(keyword, location, max_pages=max_pages, auto_login=True)
            if jobs:
                logger.info("Boss: login browser crawler succeeded with %d jobs", len(jobs))
                return jobs
            logger.info("Boss: login browser crawler returned empty, falling back to non-interactive sources...")
        except Exception as e:
            logger.info("Boss: login browser crawler failed (%s), falling back to non-interactive sources...", e)

    # 1. boss-cli
    try:
        from crawlers.boss_real import search_boss_real
        jobs = search_boss_real(keyword, location)
        if jobs:
            logger.info("Boss: boss-cli succeeded with %d jobs", len(jobs))
            return jobs
        logger.info("Boss: boss-cli returned empty, trying cookie...")
    except Exception as e:
        logger.info("Boss: boss-cli failed (%s), trying cookie...", e)

    # 2. Cookie-based API
    try:
        from crawlers.boss_cookie import search_boss_with_cookie
        jobs = search_boss_with_cookie(keyword, location, max_pages=max_pages)
        if jobs:
            logger.info("Boss: cookie crawler succeeded with %d jobs", len(jobs))
            return jobs
        logger.info("Boss: cookie crawler returned empty, using curated data...")
    except Exception as e:
        logger.info("Boss: cookie crawler failed (%s), using curated data...", e)

    # 3. Curated fallback
    from crawlers.boss import search_boss_jobs
    jobs = search_boss_jobs(keyword, location)
    logger.info("Boss: curated fallback returned %d jobs", len(jobs))
    return jobs


def _deduplicate(jobs: list[dict]) -> list[dict]:
    """Remove exact duplicates without hiding the same role on other platforms."""
    seen_ids: set[str] = set()
    seen_fingerprints: set[str] = set()
    unique: list[dict] = []

    for job in jobs:
        platform = _normalize_key(job.get("platform", ""))
        jid = _normalize_key(job.get("job_id", ""))
        key_id = f"{platform}|{jid}" if jid else ""
        key_fp = _job_fingerprint(job)

        if key_id and key_id in seen_ids:
            continue
        if key_fp and key_fp in seen_fingerprints:
            continue

        if key_id:
            seen_ids.add(key_id)
        if key_fp:
            seen_fingerprints.add(key_fp)
        unique.append(job)

    return unique


def _job_fingerprint(job: dict) -> str:
    """Build a same-platform fingerprint when a source does not provide a solid id."""
    parts = [
        job.get("platform", ""),
        job.get("company", ""),
        job.get("title", ""),
        job.get("location", ""),
        job.get("salary", ""),
    ]
    return "|".join(_normalize_key(part) for part in parts)


def _normalize_key(value: object) -> str:
    text = str(value or "").lower().strip()
    return re.sub(r"\s+", "", text)


def _default_crawl_status(platform: str, use_browser_crawlers: bool) -> str:
    if platform == "curated":
        return "curated_fallback"
    if platform == "boss_drission":
        return "browser_login_opt_in"
    if platform in {"51job", "liepin"}:
        return "browser_list" if use_browser_crawlers else "requests_list"
    return "requests_or_api"


def _field_presence_counts(jobs: list[dict]) -> dict[str, dict[str, int]]:
    fields = ("experience", "degree", "welfare", "company_address", "salary")
    counts: dict[str, dict[str, int]] = {
        field: {"filled": 0, "missing": 0}
        for field in fields
    }
    for job in jobs:
        for field in fields:
            value = str(job.get(field) or "").strip()
            if value and not value.startswith("列表页未提供"):
                counts[field]["filled"] += 1
            else:
                counts[field]["missing"] += 1
    return counts


def _store_jobs(jobs: list[dict]) -> list[dict]:
    """Store jobs in SQLite, return list with db_id attached."""
    stored = []
    for job in jobs:
        enrich_job_fields(job)
        row_id = db.insert_job(
            platform=job.get("platform", "unknown"),
            title=job.get("title", ""),
            company=job.get("company", ""),
            job_id=job.get("job_id", ""),
            location=job.get("location", ""),
            salary=job.get("salary", ""),
            job_type=job.get("job_type", ""),
            description=job.get("description", ""),
            requirements=job.get("requirements", ""),
            url=job.get("url", ""),
            posted_date=job.get("posted_date", ""),
            skills=job.get("skills", ""),
            degree=job.get("degree", ""),
            experience=job.get("experience", ""),
            company_size=job.get("company_size", ""),
            company_industry=job.get("company_industry", ""),
            company_stage=job.get("company_stage", ""),
            welfare=job.get("welfare", ""),
            hr_name=job.get("hr_name", ""),
            hr_title=job.get("hr_title", ""),
            chat_url=job.get("chat_url", ""),
            full_jd=job.get("full_jd", ""),
            deadline=job.get("deadline", ""),
            source_url=job.get("source_url", ""),
            company_address=job.get("company_address", ""),
            crawl_status=job.get("crawl_status", ""),
            crawl_keyword=job.get("crawl_keyword", ""),
            detail_status=job.get("detail_status", ""),
            detail_source_url=job.get("detail_source_url", ""),
        )
        if row_id:
            job["db_id"] = row_id
        stored.append(job)

    return stored
