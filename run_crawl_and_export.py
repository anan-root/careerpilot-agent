"""One-shot script: crawl all platforms for Wuhan AI jobs + export Excel."""

import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
os.chdir(Path(__file__).parent)

import logging
logging.basicConfig(level=logging.INFO, format="%(name)s | %(message)s")

from rich.console import Console
from rich.table import Table

console = Console()

def main():
    import db
    console.print("[bold cyan]═══ CareerPilot 岗位采集 + Excel 导出 ═══[/]\n")

    # --- 1. Crawl from all platforms ---
    all_jobs = []

    # Boss直聘 (real crawler first, fallback to curated)
    console.print("[bold]1. Boss直聘 (boss-cli → 策展数据 fallback)...[/]")
    try:
        from crawlers.boss_real import search_boss_real
        boss_jobs = search_boss_real("AI Agent", "武汉")
        if boss_jobs:
            console.print(f"  [green]boss-cli: {len(boss_jobs)} 个岗位[/]")
        else:
            raise RuntimeError("boss-cli returned empty")
    except Exception as e:
        console.print(f"  [yellow]boss-cli unavailable ({e}), using curated data[/]")
        from crawlers.boss import search_boss_jobs
        boss_jobs = search_boss_jobs("AI Agent", "武汉")
        console.print(f"  [green]策展数据: {len(boss_jobs)} 个岗位[/]")
    all_jobs.extend(boss_jobs)

    # 牛客网
    console.print("\n[bold]2. 牛客网 (requests)...[/]")
    try:
        from crawlers.nowcoder import search_nowcoder
        nc_jobs = search_nowcoder("AI Agent", "武汉", max_pages=2)
        console.print(f"  [green]{len(nc_jobs)} 个岗位[/]")
        all_jobs.extend(nc_jobs)
    except Exception as e:
        console.print(f"  [red]牛客网失败: {e}[/]")

    # 猎聘
    console.print("\n[bold]3. 猎聘 (requests)...[/]")
    try:
        from crawlers.liepin import search_liepin
        lp_jobs = search_liepin("AI Agent", "武汉", max_pages=2)
        console.print(f"  [green]{len(lp_jobs)} 个岗位[/]")
        all_jobs.extend(lp_jobs)
    except Exception as e:
        console.print(f"  [red]猎聘失败: {e}[/]")

    # --- 2. Dedup ---
    seen = set()
    unique = []
    for j in all_jobs:
        key = f"{j.get('company','').lower()}|{j.get('title','').lower()}"
        if key not in seen:
            seen.add(key)
            unique.append(j)
    console.print(f"\n[bold]去重: {len(all_jobs)} → {len(unique)} 个岗位[/]")

    # --- 3. Store in DB ---
    for j in unique:
        row_id = db.insert_job(
            platform=j.get("platform", "unknown"),
            title=j.get("title", ""),
            company=j.get("company", ""),
            job_id=j.get("job_id", ""),
            location=j.get("location", ""),
            salary=j.get("salary", ""),
            job_type=j.get("job_type", ""),
            description=j.get("description", ""),
            requirements=j.get("requirements", ""),
            url=j.get("url", ""),
            posted_date=j.get("posted_date", ""),
            skills=j.get("skills", ""),
            degree=j.get("degree", ""),
            experience=j.get("experience", ""),
            company_size=j.get("company_size", ""),
            company_industry=j.get("company_industry", ""),
            company_stage=j.get("company_stage", ""),
            welfare=j.get("welfare", ""),
            hr_name=j.get("hr_name", ""),
            hr_title=j.get("hr_title", ""),
            chat_url=j.get("chat_url", ""),
            full_jd=j.get("full_jd", ""),
            deadline=j.get("deadline", ""),
            source_url=j.get("source_url", ""),
            company_address=j.get("company_address", ""),
            crawl_status=j.get("crawl_status", ""),
            crawl_keyword=j.get("crawl_keyword", ""),
            detail_status=j.get("detail_status", ""),
            detail_source_url=j.get("detail_source_url", ""),
        )
        if row_id:
            j["db_id"] = row_id

    # --- 4. Print table ---
    table = Table(title=f"武汉 AI 岗位采集结果 ({len(unique)} 个)", show_lines=True)
    table.add_column("#", style="dim", width=4)
    table.add_column("来源", width=8)
    table.add_column("公司", style="bold")
    table.add_column("岗位")
    table.add_column("地点")
    table.add_column("薪资")
    table.add_column("类型")

    for i, j in enumerate(unique, 1):
        table.add_row(
            str(i), j["platform"], j["company"], j["title"],
            j.get("location", ""), j.get("salary", ""),
            j.get("job_type", ""),
        )
    console.print(table)

    # --- 5. Export Excel ---
    console.print("\n[bold]导出 Excel...[/]")
    from export.excel import export_excel
    xlsx_path = export_excel(unique, "data/outputs/wuhan_ai_jobs.xlsx")
    console.print(f"[bold green]✓ Excel 导出: {xlsx_path}[/]")

    # --- 6. Export CSV + JSON ---
    from export.csv_export import export_csv
    from export.json_export import export_json
    csv_path = export_csv(unique, "data/outputs/wuhan_ai_jobs.csv")
    json_path = export_json(unique, "data/outputs/wuhan_ai_jobs.json")
    console.print(f"[green]✓ CSV: {csv_path}[/]")
    console.print(f"[green]✓ JSON: {json_path}[/]")

    console.print(f"\n[bold green]完成！共 {len(unique)} 个岗位，来自 Boss直聘 + 牛客网 + 猎聘[/]")
    return unique

if __name__ == "__main__":
    main()

