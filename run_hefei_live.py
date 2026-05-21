"""
CareerPilot Agent — Boss直聘实时爬取（DrissionPage 浏览器方案）
流程: 弹出浏览器 → 自动检测登录(未登录则扫码) → 爬取岗位 → 导出Excel

用法:
  python run_hefei_live.py                    # 默认: 合肥 AI
  python run_hefei_live.py 武汉 "AI Agent"    # 自定义: 武汉 AI Agent
  python run_hefei_live.py 北京 大模型 8       # 北京 大模型 爬8页
"""
import sys
import os
import time
import json
import random
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
os.chdir(Path(__file__).parent)

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
console = Console()

from crawlers.browser_utils import apply_browser_hardening

CITY_CODES = {
    "武汉": "101200100", "北京": "101010100", "上海": "101020100",
    "杭州": "101210100", "深圳": "101280600", "广州": "101280100",
    "成都": "101270100", "南京": "101190100", "合肥": "101220100",
    "西安": "101110100", "重庆": "101040100", "天津": "101030100",
    "苏州": "101190400", "厦门": "101230200", "长沙": "101250100",
    "青岛": "101120200", "郑州": "101180100",
}

CITY    = sys.argv[1] if len(sys.argv) > 1 else "合肥"
KEYWORD = sys.argv[2] if len(sys.argv) > 2 else "AI"
MAX_PAGES = int(sys.argv[3]) if len(sys.argv) > 3 else 5
CITY_CODE = CITY_CODES.get(CITY, "101220100")
USER_DATA = str(Path(__file__).parent / "data" / ".boss_browser_profile")


def main():
    console.print(Panel(
        f"[bold]CareerPilot Agent — {CITY} {KEYWORD} 岗位实时采集[/]\n"
        "即将打开浏览器，请扫码登录 Boss直聘",
        border_style="cyan"
    ))

    from DrissionPage import ChromiumPage, ChromiumOptions
    co = ChromiumOptions()
    co.set_user_data_path(USER_DATA)
    if hasattr(co, "auto_port"):
        co.auto_port(True)
    apply_browser_hardening(co)

    page = ChromiumPage(co)

    # --- 打开登录页，检测是否已登录 ---
    console.print("\n[bold]Step 1: 检测登录状态...[/]")
    page.get("https://www.zhipin.com/web/geek/job")
    time.sleep(3)

    is_logged_in = _check_login(page)

    if not is_logged_in:
        console.print("[yellow]未登录，打开扫码页...[/]")
        page.get("https://www.zhipin.com/web/user/?ka=header-login")
        time.sleep(2)

        console.print("\n[bold yellow]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/]")
        console.print("[bold yellow]  ⬆  请在弹出的浏览器窗口里扫码登录  ⬆  [/]")
        console.print("[bold yellow]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/]")

        # 等待登录完成（最多120秒）
        for i in range(60):
            time.sleep(2)
            if _check_login(page):
                console.print(f"\n[bold green]✓ 登录成功！[/]")
                break
            if i % 5 == 0 and i > 0:
                console.print(f"  [dim]等待登录... ({i*2}秒)[/]")
        else:
            console.print("[red]登录超时，请重新运行[/]")
            page.quit()
            return
    else:
        console.print("[green]✓ 已登录[/]")

    # --- 爬取岗位 ---
    console.print(f"\n[bold]Step 2: 爬取 {CITY} {KEYWORD} 岗位...[/]")
    all_jobs = _crawl_jobs(page)

    page.quit()

    if not all_jobs:
        console.print("[red]没有爬到岗位，请检查网络或重新登录[/]")
        return

    # --- 去重 ---
    seen = set()
    unique = []
    for j in all_jobs:
        key = f"{j.get('company','').lower()}|{j.get('title','').lower()}"
        if key not in seen:
            seen.add(key)
            unique.append(j)
    console.print(f"[bold]去重: {len(all_jobs)} → {len(unique)} 个岗位[/]")

    # --- 存数据库 ---
    import db
    for j in unique:
        db.insert_job(**{k: j.get(k, "") for k in [
            "platform","title","company","job_id","location","salary",
            "job_type","description","requirements","url","posted_date",
            "skills","degree","experience","company_size","company_industry",
            "company_stage","welfare","hr_name","hr_title","chat_url",
            "full_jd","source_url","company_address","crawl_status",
            "crawl_keyword","detail_status","detail_source_url",
        ]})

    # --- 打印表格 ---
    table = Table(title=f"{CITY} {KEYWORD} 实时采集结果 ({len(unique)}个)", show_lines=True)
    table.add_column("#", width=4, style="dim")
    table.add_column("公司", style="bold")
    table.add_column("岗位")
    table.add_column("薪资")
    table.add_column("地点")
    table.add_column("HR")
    for i, j in enumerate(unique, 1):
        table.add_row(str(i), j["company"], j["title"],
                      j.get("salary",""), j.get("location",""),
                      f"{j.get('hr_name','')} {j.get('hr_title','')}".strip())
    console.print(table)

    # --- 导出 Excel ---
    from export.excel import export_excel
    from datetime import datetime
    ts = datetime.now().strftime("%Y%m%d_%H%M")
    out_path = Path(f"data/outputs/{CITY}_{KEYWORD}_jobs_{ts}.xlsx")
    path = export_excel(unique, out_path)
    console.print(f"\n[bold green]✓ Excel 已导出: {path}[/]")

    # 自动打开 Excel
    os.system(f"open '{path}'")
    console.print("[dim]已自动打开 Excel 文件[/]")


def _check_login(page) -> bool:
    """Check if user is logged in by looking for avatar/username elements."""
    try:
        url = page.url
        # If redirected to login page, not logged in
        if "user/?ka=header-login" in url or "login" in url:
            return False
        # Check for login indicators in page
        el = page.ele("css:.nav-figure img, css:.user-nav .figure, css:[class*='nav-info']", timeout=3)
        return el is not None
    except Exception:
        return False


def _crawl_jobs(page) -> list[dict]:
    """Crawl job listings by intercepting API responses."""
    all_jobs = []
    url = f"https://www.zhipin.com/web/geek/job?query={KEYWORD}&city={CITY_CODE}"

    for pg in range(1, MAX_PAGES + 1):
        try:
            page.listen.start("wapi/zpgeek/search/joblist")
            target = url if pg == 1 else f"{url}&page={pg}"
            page.get(target)

            console.print(f"  [dim]第 {pg}/{MAX_PAGES} 页...[/]", end="")

            try:
                packet = page.listen.wait(timeout=20)
            except Exception:
                console.print(" [yellow]超时[/]")
                break

            page.listen.stop()

            if not packet or not packet.response or not packet.response.body:
                console.print(" [yellow]无数据[/]")
                break

            body = packet.response.body
            if isinstance(body, str):
                body = json.loads(body)

            if body.get("code") != 0:
                console.print(f" [red]API错误 {body.get('code')}[/]")
                break

            job_list = body.get("zpData", {}).get("jobList", [])
            if not job_list:
                console.print(" [yellow]没有更多岗位[/]")
                break

            for j in job_list:
                encrypt_boss_id = j.get("encryptBossId", "")
                security_id = j.get("securityId", "")
                chat_url = f"https://www.zhipin.com/web/geek/chat?id={encrypt_boss_id}&securityId={security_id}" if encrypt_boss_id and security_id else ""

                all_jobs.append({
                    "platform": "boss",
                    "job_id": j.get("encryptJobId", ""),
                    "title": j.get("jobName", ""),
                    "company": j.get("brandName", ""),
                    "location": f"{j.get('cityName','')} {j.get('areaDistrict','')} {j.get('businessDistrict','')}".strip(),
                    "salary": j.get("salaryDesc", ""),
                    "job_type": "实习" if "实习" in " ".join(j.get("jobLabels", [])) else "社招",
                    "description": j.get("jobName", ""),
                    "requirements": "",
                    "url": f"https://www.zhipin.com/job_detail/{j.get('encryptJobId','')}.html",
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
                    "source_url": f"https://www.zhipin.com/job_detail/{j.get('encryptJobId','')}.html",
                })

            console.print(f" [green]{len(job_list)} 个岗位[/]")

            has_more = body.get("zpData", {}).get("hasMore", False)
            if not has_more:
                break

            time.sleep(random.uniform(2.5, 4.5))

        except Exception as e:
            console.print(f" [red]错误: {e}[/]")
            break

    return all_jobs


if __name__ == "__main__":
    main()

