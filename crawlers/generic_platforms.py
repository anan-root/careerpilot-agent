"""Lightweight adapters for additional recruitment platforms.

These platforms often require login, dynamic rendering, or anti-bot checks for
full job lists. The adapter keeps them selectable and traceable without opening
interactive browsers by default.
"""

from __future__ import annotations

from urllib.parse import quote

from crawlers.ids import stable_job_id


PLATFORM_CONFIGS: dict[str, dict[str, str]] = {
    "lagou": {
        "label": "拉勾",
        "home": "https://www.lagou.com/",
        "search": "https://www.lagou.com/wn/jobs?kd={keyword}&city={city}",
        "industry": "互联网/软件",
    },
    "yingjiesheng": {
        "label": "应届生",
        "home": "https://www.yingjiesheng.com/",
        "search": "https://www.yingjiesheng.com/sojob.php?word={keyword}&area={city}",
        "industry": "校招/应届",
    },
    "guopin": {
        "label": "国聘网",
        "home": "https://www.iguopin.com/",
        "search": "https://www.iguopin.com/search/jobs?keyword={keyword}&city={city}",
        "industry": "国企/央企",
    },
    "dingxiang": {
        "label": "丁香人才网",
        "home": "https://www.jobmd.cn/",
        "search": "https://www.jobmd.cn/work/search.htm?wd={keyword}",
        "industry": "医疗健康",
    },
    "jobonline": {
        "label": "就业在线",
        "home": "https://www.jobonline.cn/",
        "search": "https://www.jobonline.cn/",
        "industry": "公共就业服务",
    },
}


def search_generic_platform(
    platform: str,
    keyword: str = "AI Agent",
    city: str = "上海",
    *,
    max_pages: int = 1,
) -> list[dict]:
    config = PLATFORM_CONFIGS.get(platform)
    if not config:
        return []

    search_url = config["search"].format(keyword=quote(keyword), city=quote(city))
    label = config["label"]
    title = f"{keyword} 相关岗位检索入口"
    company = f"{label}公开岗位"
    job_type = "校招" if platform == "yingjiesheng" else "社招"
    return [
        {
            "platform": platform,
            "job_id": stable_job_id(platform, keyword, city, "search-entry"),
            "title": title,
            "company": company,
            "location": city,
            "salary": "",
            "job_type": job_type,
            "description": f"{label}暂使用公开搜索入口。该平台可能需要登录、动态渲染或人工验证才能获取完整列表。",
            "requirements": "",
            "url": search_url or config["home"],
            "posted_date": "",
            "skills": keyword,
            "degree": "",
            "experience": "",
            "company_size": "",
            "company_industry": config.get("industry", ""),
            "company_address": city,
            "welfare": "",
            "source_url": search_url or config["home"],
            "crawl_status": "search_entry",
            "crawl_keyword": keyword,
            "detail_status": "not_requested",
        }
    ]
