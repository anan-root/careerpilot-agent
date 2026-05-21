"""CareerPilot end-to-end pipeline -- from job collection to interview prep."""

from __future__ import annotations

import sys
import json
import time
from pathlib import Path
from datetime import datetime

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich import print as rprint

sys.path.insert(0, str(Path(__file__).parent))

import db
from crawlers.aggregator import collect_all_jobs
from agents.analyst import analyze_jd, score_job, profile_company
from agents.tailor import generate_tailored_resume, render_latex, generate_greeting
from agents.coach import generate_interview_pack
from platform_registry import DEFAULT_PLATFORM_CODES, PLATFORM_LABELS, platform_label_text

console = Console()
OUTPUT_DIR = Path(__file__).parent / "data" / "outputs"


def step_collect(keyword: str = "AI Agent", location: str = "上海",
                 platforms: list[str] | None = None,
                 job_types: list[str] | None = None) -> list[dict]:
    """Step 1: Collect jobs from all platforms."""
    console.print("\n[bold cyan]═══ Step 1: 岗位采集（多平台真实爬虫） ═══[/]")

    platform_names = platform_label_text(platforms or DEFAULT_PLATFORM_CODES)
    console.print(f"  平台: {platform_names}")
    if job_types:
        console.print(f"  类型: {', '.join(job_types)}")

    jobs = collect_all_jobs(
        keyword,
        location,
        platforms=platforms,
        job_types=job_types,
        expand_keywords=True,
        enrich_details=True,
        detail_limit=20,
        use_browser_crawlers=False,
        allow_browser_login=False,
    )
    console.print(f"[green]✓[/] 采集到 {len(jobs)} 个岗位")

    table = Table(title="采集结果", show_lines=True)
    table.add_column("#", style="dim", width=4)
    table.add_column("公司", style="bold")
    table.add_column("岗位")
    table.add_column("地点")
    table.add_column("薪资")
    table.add_column("类型")
    table.add_column("平台")

    for i, j in enumerate(jobs, 1):
        table.add_row(
            str(i), j["company"], j["title"], j.get("location", ""),
            j.get("salary", ""), j.get("job_type", ""), j["platform"],
        )

    console.print(table)
    return jobs


def step_analyze_and_score(jobs: list[dict]) -> list[dict]:
    """Step 2: Analyze JDs and score each job."""
    console.print("\n[bold cyan]═══ Step 2: 岗位分析 & 10维评分 ═══[/]")

    scored = []
    for i, job in enumerate(jobs):
        console.print(f"  [{i+1}/{len(jobs)}] 分析: {job['company']} - {job['title']}")

        jd_text = f"岗位: {job['title']}\n公司: {job['company']}\n地点: {job.get('location','')}\n薪资: {job.get('salary','')}\n描述: {job.get('description','')}\n要求: {job.get('requirements','')}\n技能: {job.get('skills','')}"
        try:
            jd_info = analyze_jd(jd_text)
            total, details = score_job(jd_info)
            job["jd_info"] = jd_info
            job["score"] = total
            job["score_details"] = details

            color = "green" if total >= 0.6 else "yellow" if total >= 0.4 else "red"
            console.print(f"    [{color}]评分: {total:.2f}[/] | {details.get('reasoning','')[:60]}")

            job_db_id = job.get("db_id")
            if job_db_id:
                db.update_job_score(job_db_id, total, details)
        except Exception as e:
            console.print(f"    [red]分析失败: {e}[/]")
            job["score"] = 0
            job["jd_info"] = {}

        scored.append(job)
        time.sleep(1)

    scored.sort(key=lambda x: x.get("score", 0), reverse=True)

    table = Table(title="评分排名", show_lines=True)
    table.add_column("#", style="dim")
    table.add_column("公司", style="bold")
    table.add_column("岗位")
    table.add_column("评分", justify="right")
    table.add_column("推荐", justify="center")

    for i, j in enumerate(scored):
        s = j.get("score", 0)
        rec = "✅ 强推" if s >= 0.65 else "⚡ 可投" if s >= 0.45 else "❌ 跳过"
        color = "green" if s >= 0.65 else "yellow" if s >= 0.45 else "red"
        table.add_row(str(i+1), j["company"], j["title"], f"[{color}]{s:.2f}[/]", rec)

    console.print(table)
    return scored


def step_export(jobs: list[dict]) -> Path | None:
    """Step 2.5: Export jobs to Excel."""
    console.print("\n[bold cyan]═══ Step 2.5: 导出 Excel ═══[/]")
    try:
        from export.excel import export_excel
        ts = datetime.now().strftime("%Y%m%d_%H%M")
        path = export_excel(jobs, OUTPUT_DIR / f"jobs_{ts}.xlsx")
        console.print(f"[green]✓[/] Excel 导出: {path}")
        return path
    except Exception as e:
        console.print(f"[yellow]⚠ Excel 导出失败: {e}[/]")
        return None


def step_company_profile(job: dict) -> dict:
    """Step 3: Generate company profile."""
    console.print(f"\n[bold cyan]═══ Step 3: 公司画像 - {job['company']} ═══[/]")
    try:
        profile = profile_company(job["company"])
        console.print(Panel(
            f"[bold]{profile.get('name', job['company'])}[/]\n"
            f"行业: {profile.get('industry', '未知')}\n"
            f"规模: {profile.get('size', '未知')}\n"
            f"评分: {profile.get('rating', 'N/A')}/10\n"
            f"优点: {', '.join(profile.get('pros', []))}\n"
            f"缺点: {', '.join(profile.get('cons', []))}\n"
            f"薪资: {profile.get('avg_salary', '未知')}\n"
            f"加班: {profile.get('work_life_balance', '未知')}",
            title="公司画像",
        ))
        return profile
    except Exception as e:
        console.print(f"[red]公司画像生成失败: {e}[/]")
        return {}


def step_generate_resume(job: dict) -> tuple[dict, Path | None]:
    """Step 4: Generate tailored resume."""
    console.print(f"\n[bold cyan]═══ Step 4: 简历定制 - {job['company']} {job['title']} ═══[/]")

    jd_info = job.get("jd_info", {})
    if not jd_info:
        jd_info = {"title": job["title"], "company": job["company"],
                    "required_skills": job.get("requirements", "").split(";")}

    try:
        resume_data = generate_tailored_resume(jd_info)
        resume_data.setdefault("basics_location", "上海")

        console.print("[green]✓[/] 简历内容生成完成")
        console.print(f"  个人总结: {resume_data.get('summary', '')[:100]}...")
        console.print(f"  项目数量: {len(resume_data.get('projects', []))}")
        console.print(f"  ATS关键词: {', '.join(resume_data.get('keywords_injected', []))}")

        safe_name = f"{job['company']}_{job['title']}".replace("/", "_").replace(" ", "_")[:50]
        output_name = f"resume_{safe_name}_{datetime.now().strftime('%Y%m%d')}"

        try:
            pdf_path = render_latex(resume_data, output_name)
            console.print(f"[green]✓[/] PDF生成: {pdf_path}")
        except Exception as e:
            console.print(f"[yellow]⚠ LaTeX编译失败 (可能未安装): {e}[/]")
            md_path = OUTPUT_DIR / f"{output_name}.json"
            md_path.write_text(json.dumps(resume_data, ensure_ascii=False, indent=2), encoding="utf-8")
            console.print(f"[green]✓[/] 简历数据已保存: {md_path}")
            pdf_path = None

        greeting = generate_greeting(jd_info, resume_data)
        console.print(Panel(greeting, title="Boss直聘打招呼语"))

        return resume_data, pdf_path
    except Exception as e:
        console.print(f"[red]简历生成失败: {e}[/]")
        return {}, None


def step_interview_prep(job: dict, resume_data: dict | None = None) -> dict:
    """Step 5: Generate interview preparation package."""
    console.print(f"\n[bold cyan]═══ Step 5: 面试资料生成 - {job['company']} {job['title']} ═══[/]")

    jd_info = job.get("jd_info", {})
    if not jd_info:
        jd_info = {"title": job["title"], "company": job["company"],
                    "required_skills": job.get("requirements", "").split(";")}

    try:
        console.print("  [dim]生成技能树...[/]")
        pack = generate_interview_pack(jd_info, resume_data)

        safe_name = f"{job['company']}_{job['title']}".replace("/", "_").replace(" ", "_")[:50]
        base_name = f"interview_{safe_name}_{datetime.now().strftime('%Y%m%d')}"

        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

        skill_path = OUTPUT_DIR / f"{base_name}_skill_tree.json"
        skill_path.write_text(json.dumps(pack["skill_tree"], ensure_ascii=False, indent=2), encoding="utf-8")

        study_path = OUTPUT_DIR / f"{base_name}_study_path.md"
        study_path.write_text(pack["study_path"], encoding="utf-8")

        eight_path = OUTPUT_DIR / f"{base_name}_eight_part.md"
        eight_path.write_text(pack["eight_part_essay"], encoding="utf-8")

        mock_path = OUTPUT_DIR / f"{base_name}_mock_interview.md"
        mock_path.write_text(pack["mock_questions"], encoding="utf-8")

        console.print(f"[green]✓[/] 技能树: {skill_path}")
        console.print(f"[green]✓[/] 学习路径: {study_path}")
        console.print(f"[green]✓[/] 八股文: {eight_path}")
        console.print(f"[green]✓[/] 模拟面试: {mock_path}")

        return pack
    except Exception as e:
        console.print(f"[red]面试资料生成失败: {e}[/]")
        return {}


def run_pipeline(keyword: str = "AI Agent", location: str = "上海", top_n: int = 3,
                 platforms: list[str] | None = None,
                 job_types: list[str] | None = None):
    """Run the full end-to-end pipeline."""
    console.print(Panel(
        f"[bold]CareerPilot Agent 求职助手[/]\n"
        f"关键词: {keyword} | 地点: {location} | Top-N: {top_n}\n"
        f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        title="🔥 Pipeline Start",
        border_style="cyan",
    ))

    jobs = step_collect(keyword, location, platforms, job_types)
    if not jobs:
        console.print("[red]没有采集到岗位，结束。[/]")
        return

    scored_jobs = step_analyze_and_score(jobs)

    step_export(scored_jobs)

    top_jobs = [j for j in scored_jobs if j.get("score", 0) > 0][:top_n]
    if not top_jobs:
        console.print("[yellow]没有高分岗位，取前3个继续处理。[/]")
        top_jobs = scored_jobs[:top_n]

    console.print(f"\n[bold magenta]═══ 对 Top-{len(top_jobs)} 岗位执行完整流程 ═══[/]")

    for i, job in enumerate(top_jobs):
        console.print(f"\n{'='*60}")
        console.print(f"[bold]目标 {i+1}: {job['company']} - {job['title']}[/]")
        console.print(f"{'='*60}")

        step_company_profile(job)
        resume_data, pdf_path = step_generate_resume(job)
        step_interview_prep(job, resume_data)

        time.sleep(2)

    console.print(Panel(
        f"[bold green]Pipeline 完成！[/]\n"
        f"处理了 {len(top_jobs)} 个岗位\n"
        f"输出目录: {OUTPUT_DIR}",
        title="✅ Pipeline Complete",
        border_style="green",
    ))


def run_single(job_data: dict):
    """Run pipeline for a single specified job."""
    console.print(Panel(
        f"[bold]单岗位模式: {job_data['company']} - {job_data['title']}[/]",
        title="🎯 Single Job",
        border_style="cyan",
    ))

    jd_text = f"岗位: {job_data['title']}\n公司: {job_data['company']}\n描述: {job_data.get('description','')}\n要求: {job_data.get('requirements','')}"
    jd_info = analyze_jd(jd_text)
    job_data["jd_info"] = jd_info

    total, details = score_job(jd_info)
    job_data["score"] = total
    job_data["score_details"] = details
    console.print(f"[green]评分: {total:.2f}[/]")

    step_company_profile(job_data)
    resume_data, _ = step_generate_resume(job_data)
    step_interview_prep(job_data, resume_data)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="CareerPilot Pipeline")
    parser.add_argument("--keyword", default="AI Agent", help="搜索关键词")
    parser.add_argument("--location", default="上海", help="目标城市")
    parser.add_argument("--top", type=int, default=3, help="处理前N个岗位")
    parser.add_argument("--platform", nargs="*", default=None,
                        choices=list(PLATFORM_LABELS.keys()),
                        help="指定平台，默认 BOSS直聘 / 智联招聘 / 前程无忧")
    parser.add_argument("--job-type", nargs="*", default=["社招"],
                        help="岗位类型 (社招 校招 实习)，默认只看社招/全职")
    args = parser.parse_args()

    run_pipeline(args.keyword, args.location, args.top, args.platform, args.job_type)

