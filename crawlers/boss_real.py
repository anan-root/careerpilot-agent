"""Boss直聘 real crawler using kabi-boss-cli (逆向API, 纯HTTP无需浏览器).

Install: pip install kabi-boss-cli
First run: `boss login` in terminal to authenticate via QR code.
"""

from __future__ import annotations

import json
import subprocess
import time
import random
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

CITY_MAP = {
    "武汉": "武汉", "北京": "北京", "上海": "上海", "杭州": "杭州",
    "深圳": "深圳", "广州": "广州", "成都": "成都", "南京": "南京",
}


def _run_boss_cli(args: list[str], timeout: int = 30) -> dict | None:
    """Run boss-cli command and parse JSON output."""
    cmd = ["boss"] + args + ["--json"]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout
        )
        if result.returncode != 0:
            logger.warning("boss-cli error: %s", result.stderr.strip())
            return None
        raw = result.stdout.strip()
        if not raw:
            return None
        data = json.loads(raw)
        if data.get("ok"):
            return data.get("data", {})
        logger.warning("boss-cli not ok: %s", data)
        return None
    except FileNotFoundError:
        logger.error("boss-cli not installed. Run: pip install kabi-boss-cli && boss login")
        return None
    except subprocess.TimeoutExpired:
        logger.warning("boss-cli timed out")
        return None
    except json.JSONDecodeError as e:
        logger.warning("boss-cli JSON parse error: %s", e)
        return None


def check_login() -> bool:
    """Check if boss-cli is logged in."""
    data = _run_boss_cli(["status"])
    return data is not None


def search_boss_real(
    keyword: str = "AI Agent",
    city: str = "上海",
    *,
    degree: str = "",
    experience: str = "",
    salary: str = "",
    max_results: int = 60,
) -> list[dict]:
    """Search Boss直聘 via boss-cli and return normalized job dicts.

    Each returned dict has the unified CareerPilot field names ready for db.insert_job().
    """
    args = ["search", keyword, "--city", city]
    if degree:
        args += ["--degree", degree]
    if experience:
        args += ["--experience", experience]
    if salary:
        args += ["--salary", salary]

    data = _run_boss_cli(args, timeout=45)
    if not data:
        logger.info("boss-cli search returned no data, falling back to curated data")
        return []

    raw_jobs = data if isinstance(data, list) else data.get("jobList", data.get("list", []))
    if not isinstance(raw_jobs, list):
        logger.warning("Unexpected boss-cli data format: %s", type(data))
        return []

    jobs = []
    for j in raw_jobs[:max_results]:
        encrypt_boss_id = j.get("encryptBossId", "")
        security_id = j.get("securityId", "")
        chat_url = ""
        if encrypt_boss_id and security_id:
            chat_url = f"https://www.zhipin.com/web/geek/chat?id={encrypt_boss_id}&securityId={security_id}"

        job = {
            "platform": "boss",
            "job_id": j.get("encryptJobId", j.get("jobId", "")),
            "title": j.get("jobName", ""),
            "company": j.get("brandName", ""),
            "location": f"{j.get('cityName', '')} {j.get('areaDistrict', '')} {j.get('businessDistrict', '')}".strip(),
            "salary": j.get("salaryDesc", ""),
            "job_type": _guess_job_type(j),
            "description": j.get("jobName", ""),
            "requirements": "",
            "url": f"https://www.zhipin.com/job_detail/{j.get('encryptJobId', '')}.html",
            "posted_date": j.get("lastModifyTime", ""),
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
        jobs.append(job)

    logger.info("boss-cli: fetched %d jobs for '%s' in %s", len(jobs), keyword, city)
    return jobs


def export_boss_csv(keyword: str, city: str = "上海", output: str = "boss_jobs.csv", n: int = 50) -> Path | None:
    """Use boss-cli export command to directly export CSV."""
    cmd = ["boss", "export", keyword, "--city", city, "-n", str(n), "-o", output]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode == 0 and Path(output).exists():
            return Path(output)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return None


def _guess_job_type(job_data: dict) -> str:
    labels = job_data.get("jobLabels", [])
    exp = job_data.get("jobExperience", "")
    text = " ".join(labels) + " " + exp
    if "实习" in text:
        return "实习"
    if "应届" in text or "校招" in text:
        return "校招"
    return "社招"
