"""Demo: run full CareerPilot pipeline for 华为武汉AI实习."""

import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
os.chdir(Path(__file__).parent)

from rich.console import Console
console = Console()


def main():
    from pipeline import (
        step_analyze_and_score, step_company_profile,
        step_generate_resume, step_interview_prep, step_export,
    )

    huawei_job = {
        "platform": "boss",
        "job_id": "boss_hw_001",
        "title": "AI工程师实习生（大模型/NLP方向）",
        "company": "华为",
        "location": "武汉东湖高新区（华为武汉研究所）",
        "salary": "300-350元/天",
        "job_type": "暑期实习",
        "description": "参与华为云/盘古大模型相关的AI应用研发，包括大模型推理优化、NLP算法、Agent系统设计等方向。华为2026暑期实习Star计划",
        "requirements": "2027届硕士/博士;熟悉Python/C++;精通PyTorch;有LLM/NLP项目经验;熟悉Transformer架构;有顶会论文或竞赛获奖优先",
        "url": "https://career.huawei.com/reccampportal/portal5/campus-recruitment.html",
        "posted_date": "2026-03",
        "skills": "Python,C++,PyTorch,LLM,NLP,Transformer,Agent",
        "degree": "硕士/博士",
        "experience": "有LLM/NLP项目经验",
        "company_size": "100000+",
        "company_industry": "人工智能/通信/ICT",
        "company_stage": "上市公司",
        "welfare": "五险一金,免费班车,免费三餐,健身房",
        "source_url": "https://career.huawei.com/reccampportal/portal5/campus-recruitment.html",
    }

    console.print("[bold cyan]═══ CareerPilot Demo: 华为武汉AI实习 完整流程 ═══[/]\n")

    # Step 1: Analyze & Score
    console.print("[bold]Step 1: 岗位分析 & 10维评分[/]")
    scored = step_analyze_and_score([huawei_job])

    # Step 2: Company Profile
    console.print("\n[bold]Step 2: 公司画像[/]")
    step_company_profile(huawei_job)

    # Step 3: Resume
    console.print("\n[bold]Step 3: 简历定制[/]")
    resume_data, pdf_path = step_generate_resume(huawei_job)

    # Step 4: Interview Prep
    console.print("\n[bold]Step 4: 面试资料生成[/]")
    step_interview_prep(huawei_job, resume_data)

    console.print("\n[bold green]═══ 华为武汉AI实习 Demo 完成！═══[/]")
    console.print("输出目录: data/outputs/")


if __name__ == "__main__":
    main()

