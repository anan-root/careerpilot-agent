"""CareerPilot CLI -- command-line interface for all features."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import click
from rich.console import Console
from rich.table import Table

console = Console()
OUTPUT_DIR = Path(__file__).parent / "data" / "outputs"


@click.group()
def cli():
    """CareerPilot Agent - 个人求职智能体"""
    pass


@cli.command("llm-status")
@click.option("--test", "run_test", is_flag=True, help="实际请求一次 DeepSeek，验证 API Key 是否可用")
def llm_status(run_test):
    """查看当前大模型配置"""
    import json
    from llm_client import get_llm_config, test_llm_connection

    console.print(json.dumps(get_llm_config(), ensure_ascii=False, indent=2))
    if run_test:
        console.print(json.dumps(test_llm_connection(), ensure_ascii=False, indent=2))


@cli.command()
@click.option("--keyword", "-k", default="AI Agent", help="搜索关键词")
@click.option("--location", "-l", default="上海", help="目标城市")
@click.option("--job-type", "-t", multiple=True,
              type=click.Choice(["社招", "校招", "实习"]),
              default=("社招",), help="岗位类型，可多选；默认只看社招/全职")
def search(keyword, location, job_type):
    """搜索岗位（使用默认平台）"""
    from crawlers.aggregator import collect_all_jobs
    jobs = collect_all_jobs(keyword, location, job_types=list(job_type))
    console.print(f"[green]采集到 {len(jobs)} 个岗位[/]")
    for j in jobs:
        console.print(f"  [{j['platform']}] {j['company']} | {j['title']} | {j.get('location','')} | {j.get('salary','')}")


@cli.command("agent-search")
@click.argument("goal_text")
@click.option("--resume", "-r", type=click.Path(exists=True, dir_okay=False), default=None, help="可选：简历文件路径")
@click.option("--report", type=click.Path(dir_okay=False), default=None, help="保存 Agent 搜索报告 Markdown")
def agent_search(goal_text, resume, report):
    """用一句话目标启动 CareerPilot Agent 搜索"""
    from agents.career_orchestrator import run_agent_search
    from agents.resume_matcher import extract_resume_text

    resume_text = extract_resume_text(resume) if resume else None
    result = run_agent_search(goal_text, resume_text)
    console.print("\n[bold cyan]Agent 总结[/]")
    console.print(result.get("agent_message", ""))
    memory_summary = result.get("memory_context", {}).get("summary")
    if memory_summary:
        console.print("\n[bold cyan]求职记忆[/]")
        console.print(memory_summary)

    table = Table(title=f"Agent 推荐岗位 ({len(result.get('jobs', []))})", show_lines=True)
    table.add_column("#", style="dim", width=4)
    table.add_column("等级", width=8)
    table.add_column("分数", justify="right", width=6)
    table.add_column("公司", style="bold")
    table.add_column("岗位")
    table.add_column("薪资")
    table.add_column("风险")

    for i, job in enumerate(result.get("jobs", [])[:30], 1):
        decision = job.get("job_decision", {})
        table.add_row(
            str(i),
            str(decision.get("level", "")),
            str(decision.get("score", "")),
            job.get("company", ""),
            job.get("title", ""),
            job.get("salary", ""),
            "；".join(decision.get("risks", [])[:2]),
        )
    console.print(table)

    report_text = result.get("report")
    if report_text:
        if report is None:
            OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
            report = OUTPUT_DIR / "agent_search_report.md"
        report_path = Path(report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(report_text, encoding="utf-8")
        console.print(f"[green]✓[/] Agent 搜索报告已保存: {report_path}")
    if result.get("run_id"):
        console.print(f"[dim]Agent 任务ID: {result['run_id']}[/]")


@cli.command("agent-runs")
@click.option("--limit", "-n", default=10, help="展示最近多少次 Agent 任务")
def agent_runs(limit):
    """查看最近的 CareerPilot Agent 任务记录"""
    from memory.store import load_agent_runs

    runs = load_agent_runs(limit=limit)
    if not runs:
        console.print("[yellow]暂无 Agent 任务记录[/]")
        return

    table = Table(title=f"最近 Agent 任务 ({len(runs)})", show_lines=True)
    table.add_column("任务ID", style="dim")
    table.add_column("状态", width=10)
    table.add_column("岗位数", justify="right", width=8)
    table.add_column("目标")
    table.add_column("推荐分布")
    table.add_column("更新时间")

    for item in runs:
        table.add_row(
            item.get("run_id", ""),
            item.get("status", ""),
            str(item.get("job_count", "")),
            item.get("goal_text", "")[:42],
            str(item.get("decision_counts", {})),
            item.get("updated_at", ""),
        )
    console.print(table)


@cli.command("agent-ask")
@click.argument("question")
@click.option("--run-id", default=None, help="指定 Agent 任务ID；不填则使用最近一次任务")
def agent_ask(question, run_id):
    """基于最近一次 Agent 搜索结果提问"""
    from agents.conversation_agent import answer_agent_question
    from memory.store import load_agent_run

    context = load_agent_run(run_id) if run_id else None
    if run_id and not context:
        console.print(f"[yellow]没有找到 Agent 任务：{run_id}[/]")
        return
    console.print(answer_agent_question(question, context))


@cli.command()
@click.option("--keyword", "-k", default="AI Agent", help="搜索关键词")
@click.option("--location", "-l", default="上海", help="目标城市")
@click.option("--platform", "-p", multiple=True,
              type=click.Choice(["boss", "boss_drission", "nowcoder", "liepin", "zhilian", "51job", "curated"]),
              help="指定平台(可多选)")
@click.option("--pages", default=3, help="每个平台爬取页数")
@click.option("--job-type", "-t", multiple=True,
              type=click.Choice(["社招", "校招", "实习"]),
              default=("社招",), help="岗位类型，可多选；默认只看社招/全职")
@click.option("--no-expand", is_flag=True, help="关闭扩展关键词检索")
@click.option("--max-keywords", default=4, help="最多使用多少个扩展关键词")
@click.option("--no-detail", is_flag=True, help="关闭二次详情页抓取")
@click.option("--detail-limit", default=20, help="详情页抓取上限")
@click.option("--use-browser-crawlers", is_flag=True, help="允许 51job/猎聘使用无登录浏览器列表采集")
@click.option("--allow-browser-login", is_flag=True, help="允许 Boss DrissionPage 打开浏览器并提示扫码登录")
def crawl(
    keyword,
    location,
    platform,
    pages,
    job_type,
    no_expand,
    max_keywords,
    no_detail,
    detail_limit,
    use_browser_crawlers,
    allow_browser_login,
):
    """多平台真实爬虫采集岗位"""
    from crawlers.aggregator import collect_all_jobs
    platforms = list(platform) if platform else None
    jobs = collect_all_jobs(
        keyword,
        location,
        platforms=platforms,
        max_pages=pages,
        job_types=list(job_type),
        expand_keywords=not no_expand,
        max_keywords=max_keywords,
        enrich_details=not no_detail,
        detail_limit=detail_limit,
        use_browser_crawlers=use_browser_crawlers,
        allow_browser_login=allow_browser_login,
    )

    console.print(f"\n[bold green]采集完成: {len(jobs)} 个岗位[/]")

    table = Table(title="采集结果", show_lines=True)
    table.add_column("#", style="dim", width=4)
    table.add_column("公司", style="bold")
    table.add_column("岗位")
    table.add_column("地点")
    table.add_column("薪资")
    table.add_column("经验")
    table.add_column("学历")
    table.add_column("类型")
    table.add_column("来源")

    for i, j in enumerate(jobs[:50], 1):
        table.add_row(
            str(i), j["company"], j["title"],
            j.get("location", ""), j.get("salary", ""),
            j.get("experience_display") or j.get("experience", ""),
            j.get("degree_display") or j.get("degree", ""),
            j.get("job_type", ""), j["platform"],
        )
    console.print(table)

    if len(jobs) > 50:
        console.print(f"[dim]... 还有 {len(jobs) - 50} 个岗位，使用 export 命令导出查看全部[/]")


@cli.command()
@click.option("--format", "-f", "fmt",
              type=click.Choice(["excel", "csv", "json", "all"]),
              default="excel", help="导出格式")
@click.option("--output", "-o", default=None, help="输出文件路径")
@click.option("--all-columns", is_flag=True, help="导出所有字段（默认只导出核心字段）")
def export(fmt, output, all_columns):
    """导出岗位数据为 Excel/CSV/JSON"""
    import db

    jobs = db.get_all_jobs_df()
    if not jobs:
        console.print("[yellow]数据库中没有岗位数据，请先运行 crawl 或 search 命令[/]")
        return

    console.print(f"[dim]共 {len(jobs)} 个岗位[/]")

    if fmt in ("excel", "all"):
        from export.excel import export_excel
        path = export_excel(jobs, output if fmt == "excel" else None,
                            include_all_columns=all_columns)
        console.print(f"[green]✓[/] Excel 导出: {path}")

    if fmt in ("csv", "all"):
        from export.csv_export import export_csv
        path = export_csv(jobs, output if fmt == "csv" else None,
                          include_all_columns=all_columns)
        console.print(f"[green]✓[/] CSV 导出: {path}")

    if fmt in ("json", "all"):
        from export.json_export import export_json
        path = export_json(jobs, output if fmt == "json" else None)
        console.print(f"[green]✓[/] JSON 导出: {path}")


@cli.command("match-resume")
@click.argument("resume_path", type=click.Path(exists=True, dir_okay=False))
@click.option("--top", "-n", default=10, help="展示匹配度最高的岗位数量")
@click.option("--ai-top", default=0, help="对前N个岗位使用 DeepSeek 精评（会消耗 API）")
@click.option("--job-type", "-t", multiple=True,
              type=click.Choice(["社招", "校招", "实习"]),
              default=("社招",), help="匹配的岗位类型；默认只看社招/全职")
@click.option("--output", "-o", default=None, help="保存 Markdown 匹配报告")
def match_resume(resume_path, top, ai_top, job_type, output):
    """根据上传简历匹配数据库中的岗位"""
    import db
    from agents.resume_matcher import extract_resume_text, rank_jobs_for_resume, build_match_report
    from job_filters import filter_jobs_by_type

    jobs = filter_jobs_by_type(db.get_all_jobs_df(), list(job_type))
    if not jobs:
        console.print("[yellow]数据库中没有符合类型的岗位数据，请先运行 crawl/search，或调整 --job-type。[/]")
        return

    resume_text = extract_resume_text(resume_path)
    ranked = rank_jobs_for_resume(resume_text, jobs, top_n=top, ai_top_n=ai_top)

    table = Table(title=f"简历匹配 Top {len(ranked)}", show_lines=True)
    table.add_column("#", style="dim", width=4)
    table.add_column("匹配分", justify="right", width=8)
    table.add_column("公司", style="bold")
    table.add_column("岗位")
    table.add_column("地点")
    table.add_column("命中关键词")

    for i, job in enumerate(ranked, 1):
        match = job["resume_match"]
        table.add_row(
            str(i),
            f"{match['score']:.1f}",
            job.get("company", ""),
            job.get("title", ""),
            job.get("location", ""),
            ", ".join(match.get("matched_keywords", [])[:8]),
        )
    console.print(table)

    if output is None:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        output = OUTPUT_DIR / "resume_job_match_report.md"
    report = build_match_report(ranked)
    Path(output).write_text(report, encoding="utf-8")
    console.print(f"[green]✓[/] 匹配报告已保存: {output}")


@cli.command("advise-resume")
@click.argument("resume_path", type=click.Path(exists=True, dir_okay=False))
@click.option("--job-id", type=int, default=None, help="数据库中的岗位 ID")
@click.option("--company", default=None, help="按公司名模糊匹配岗位")
@click.option("--title", default=None, help="按岗位名模糊匹配岗位")
@click.option("--output", "-o", default=None, help="保存 Markdown 建议")
def advise_resume(resume_path, job_id, company, title, output):
    """针对一个岗位生成简历优化意见和面试建议"""
    import db
    from agents.resume_matcher import extract_resume_text, generate_resume_job_advice

    if job_id is not None:
        job = db.get_job_by_id(job_id)
    else:
        jobs = db.get_all_jobs_df()
        job = next((
            j for j in jobs
            if (not company or company in j.get("company", ""))
            and (not title or title in j.get("title", ""))
        ), None)

    if not job:
        console.print("[yellow]没有找到目标岗位。请提供 --job-id，或使用 --company / --title。[/]")
        return

    resume_text = extract_resume_text(resume_path)
    advice = generate_resume_job_advice(resume_text, job)
    console.print(advice)

    if output is None:
        safe_name = f"{job.get('company','job')}_{job.get('title','')}".replace("/", "_").replace(" ", "_")[:50]
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        output = OUTPUT_DIR / f"resume_advice_{safe_name}.md"
    Path(output).write_text(advice, encoding="utf-8")
    console.print(f"[green]✓[/] 建议已保存: {output}")


@cli.command()
@click.argument("jd_text")
def analyze(jd_text):
    """分析JD并评分"""
    import json
    from agents.analyst import analyze_jd, score_job
    jd_info = analyze_jd(jd_text)
    total, details = score_job(jd_info)
    console.print(f"[green]评分: {total}[/]")
    console.print(json.dumps(details, ensure_ascii=False, indent=2))


@cli.command()
@click.option("--keyword", "-k", default="AI Agent", help="搜索关键词")
@click.option("--location", "-l", default="上海", help="目标城市")
@click.option("--top", "-n", default=3, help="处理前N个岗位")
@click.option("--job-type", "-t", multiple=True,
              type=click.Choice(["社招", "校招", "实习"]),
              default=("社招",), help="岗位类型，可多选；默认只看社招/全职")
def run(keyword, location, top, job_type):
    """运行完整管线"""
    from pipeline import run_pipeline
    run_pipeline(keyword, location, top, job_types=list(job_type))


@cli.command()
@click.option("--keyword", "-k", default="AI Agent", help="搜索关键词")
@click.option("--location", "-l", default="上海", help="目标城市")
@click.option("--top", "-n", default=5, help="处理前N个岗位")
@click.option("--interval", "-i", default=30, help="检查间隔（分钟）")
@click.option("--job-type", "-t", multiple=True,
              type=click.Choice(["社招", "校招", "实习"]),
              default=("社招",), help="岗位类型，可多选；默认只看社招/全职")
def batch(keyword, location, top, interval, job_type):
    """批量模式 -- 适合夜间自动运行"""
    from pipeline import run_pipeline
    from apscheduler.schedulers.blocking import BlockingScheduler

    console.print(f"[bold cyan]批量模式启动[/]")
    console.print(f"关键词: {keyword} | 地点: {location} | Top-{top}")
    console.print(f"每 {interval} 分钟检查一次新岗位")

    run_pipeline(keyword, location, top, job_types=list(job_type))

    try:
        scheduler = BlockingScheduler()
        scheduler.add_job(
            run_pipeline, "interval", minutes=interval,
            args=[keyword, location, top, None, list(job_type)],
        )
        scheduler.start()
    except ImportError:
        console.print("[yellow]APScheduler未安装，使用简单循环模式[/]")
        import time
        while True:
            time.sleep(interval * 60)
            run_pipeline(keyword, location, top, job_types=list(job_type))


@cli.command()
@click.option("--platform", "-p", default=None, help="按平台过滤")
@click.option("--min-score", "-s", default=None, type=float, help="最低评分过滤")
@click.option("--job-type", "-t", multiple=True,
              type=click.Choice(["社招", "校招", "实习"]),
              default=None, help="岗位类型过滤，可多选")
def list_jobs(platform, min_score, job_type):
    """列出数据库中的所有岗位"""
    import db
    from job_filters import filter_jobs_by_type
    jobs = db.get_jobs(limit=50, platform=platform, min_score=min_score)
    jobs = filter_jobs_by_type(jobs, list(job_type) if job_type else None)
    if not jobs:
        console.print("[yellow]数据库中没有岗位[/]")
        return

    table = Table(title=f"岗位列表 ({len(jobs)})", show_lines=True)
    table.add_column("#", style="dim", width=4)
    table.add_column("评分", justify="right", width=6)
    table.add_column("公司", style="bold")
    table.add_column("岗位")
    table.add_column("地点")
    table.add_column("薪资")
    table.add_column("来源")

    for i, j in enumerate(jobs, 1):
        score = j.get("score") or 0
        color = "green" if score >= 0.65 else "yellow" if score >= 0.45 else "red"
        table.add_row(
            str(i), f"[{color}]{score:.2f}[/]",
            j["company"], j["title"],
            j.get("location", ""), j.get("salary", ""),
            j.get("platform", ""),
        )
    console.print(table)


if __name__ == "__main__":
    cli()

