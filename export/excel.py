"""Excel export with conditional formatting, auto-filter, frozen header, multi-sheet."""

from __future__ import annotations

import re
from pathlib import Path
from datetime import datetime

import pandas as pd

COLUMN_MAP = {
    "company": "公司",
    "title": "岗位名称",
    "location": "工作地点",
    "salary": "薪资",
    "job_type": "类型",
    "platform": "来源",
    "skills": "技能标签",
    "degree": "学历要求",
    "experience": "经验要求",
    "company_size": "公司规模",
    "company_industry": "行业",
    "company_stage": "融资阶段",
    "welfare": "福利待遇",
    "hr_name": "招聘人",
    "hr_title": "招聘人职位",
    "score": "评分",
    "status": "状态",
    "url": "投递链接",
    "chat_url": "聊天链接",
    "source_url": "岗位链接",
    "posted_date": "发布日期",
    "deadline": "截止日期",
    "scraped_at": "采集时间",
}

CORE_COLUMNS = [
    "company", "title", "location", "salary", "job_type", "platform",
    "skills", "degree", "experience", "company_size", "company_industry",
    "welfare", "hr_name", "score", "status", "url", "chat_url",
    "posted_date",
]


def export_excel(
    jobs: list[dict],
    output_path: str | Path | None = None,
    *,
    include_all_columns: bool = False,
) -> Path:
    """Export jobs to a formatted Excel file.

    Features:
    - Frozen header row with blue background
    - Conditional formatting on salary and score columns
    - Auto-filter enabled
    - Auto column width
    - Multi-sheet: 职位列表, 公司汇总, 投递追踪
    """
    if output_path is None:
        ts = datetime.now().strftime("%Y%m%d_%H%M")
        output_path = Path(f"data/outputs/jobs_{ts}.xlsx")

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    columns = list(COLUMN_MAP.keys()) if include_all_columns else CORE_COLUMNS
    columns = [c for c in columns if c in COLUMN_MAP]

    df = pd.DataFrame(jobs)
    for col in columns:
        if col not in df.columns:
            df[col] = ""

    df = df[columns].copy()
    df.rename(columns=COLUMN_MAP, inplace=True)

    with pd.ExcelWriter(str(output_path), engine="xlsxwriter") as writer:
        _write_jobs_sheet(writer, df)
        _write_company_sheet(writer, jobs)
        _write_tracker_sheet(writer, jobs)

    return output_path


def _write_jobs_sheet(writer: pd.ExcelWriter, df: pd.DataFrame):
    """Write the main jobs sheet with formatting."""
    df.to_excel(writer, sheet_name="职位列表", index=False)

    wb = writer.book
    ws = writer.sheets["职位列表"]

    header_fmt = wb.add_format({
        "bold": True,
        "bg_color": "#366092",
        "font_color": "white",
        "border": 1,
        "text_wrap": True,
        "valign": "vcenter",
        "font_size": 11,
    })

    for col_num, value in enumerate(df.columns):
        ws.write(0, col_num, value, header_fmt)

    for i, col in enumerate(df.columns):
        max_len = df[col].astype(str).map(len).max()
        header_len = len(str(col))
        width = min(max(max_len, header_len) + 4, 45)
        ws.set_column(i, i, width)

    ws.freeze_panes(1, 0)
    ws.autofilter(0, 0, len(df), len(df.columns) - 1)

    green_fmt = wb.add_format({"bg_color": "#C6EFCE", "font_color": "#006100"})
    yellow_fmt = wb.add_format({"bg_color": "#FFEB9C", "font_color": "#9C6500"})
    red_fmt = wb.add_format({"bg_color": "#FFC7CE", "font_color": "#9C0006"})

    if "评分" in df.columns:
        score_col = list(df.columns).index("评分")
        last_row = len(df)
        ws.conditional_format(1, score_col, last_row, score_col, {
            "type": "cell", "criteria": ">=", "value": 0.65, "format": green_fmt
        })
        ws.conditional_format(1, score_col, last_row, score_col, {
            "type": "cell", "criteria": "between", "minimum": 0.45, "maximum": 0.649, "format": yellow_fmt
        })
        ws.conditional_format(1, score_col, last_row, score_col, {
            "type": "cell", "criteria": "<", "value": 0.45, "format": red_fmt
        })

    if "薪资" in df.columns:
        salary_col = list(df.columns).index("薪资")
        last_row = len(df)
        for row_idx in range(len(df)):
            val = str(df.iloc[row_idx][df.columns[salary_col]])
            daily = _parse_salary_daily(val)
            if daily >= 300:
                ws.write(row_idx + 1, salary_col, val, green_fmt)
            elif daily >= 150:
                ws.write(row_idx + 1, salary_col, val, yellow_fmt)
            elif daily > 0:
                ws.write(row_idx + 1, salary_col, val, red_fmt)

    if "来源" in df.columns:
        src_col = list(df.columns).index("来源")
        boss_fmt = wb.add_format({"bg_color": "#D6E4F0"})
        nc_fmt = wb.add_format({"bg_color": "#E2EFDA"})
        lp_fmt = wb.add_format({"bg_color": "#FCE4D6"})
        for row_idx in range(len(df)):
            val = str(df.iloc[row_idx][df.columns[src_col]])
            if "boss" in val.lower():
                ws.write(row_idx + 1, src_col, val, boss_fmt)
            elif "nowcoder" in val.lower():
                ws.write(row_idx + 1, src_col, val, nc_fmt)
            elif "liepin" in val.lower():
                ws.write(row_idx + 1, src_col, val, lp_fmt)


def _write_company_sheet(writer: pd.ExcelWriter, jobs: list[dict]):
    """Write company summary sheet."""
    company_data: dict[str, dict] = {}
    for j in jobs:
        c = j.get("company", "")
        if not c:
            continue
        if c not in company_data:
            company_data[c] = {
                "公司": c,
                "岗位数": 0,
                "行业": j.get("company_industry", ""),
                "规模": j.get("company_size", ""),
                "融资": j.get("company_stage", ""),
                "地点": j.get("location", ""),
                "薪资范围": [],
            }
        company_data[c]["岗位数"] += 1
        s = j.get("salary", "")
        if s:
            company_data[c]["薪资范围"].append(s)

    rows = []
    for info in company_data.values():
        info["薪资范围"] = " / ".join(set(info["薪资范围"]))
        rows.append(info)

    if not rows:
        return

    df = pd.DataFrame(rows)
    df.sort_values("岗位数", ascending=False, inplace=True)
    df.to_excel(writer, sheet_name="公司汇总", index=False)

    wb = writer.book
    ws = writer.sheets["公司汇总"]
    header_fmt = wb.add_format({
        "bold": True, "bg_color": "#548235", "font_color": "white", "border": 1
    })
    for col_num, value in enumerate(df.columns):
        ws.write(0, col_num, value, header_fmt)
        ws.set_column(col_num, col_num, 18)
    ws.freeze_panes(1, 0)


def _write_tracker_sheet(writer: pd.ExcelWriter, jobs: list[dict]):
    """Write application tracker template sheet."""
    tracker_cols = ["公司", "岗位", "投递日期", "状态", "面试日期", "下次跟进", "备注"]
    rows = []
    for j in jobs:
        rows.append({
            "公司": j.get("company", ""),
            "岗位": j.get("title", ""),
            "投递日期": "",
            "状态": "未投递",
            "面试日期": "",
            "下次跟进": "",
            "备注": "",
        })

    df = pd.DataFrame(rows, columns=tracker_cols)
    df.to_excel(writer, sheet_name="投递追踪", index=False)

    wb = writer.book
    ws = writer.sheets["投递追踪"]
    header_fmt = wb.add_format({
        "bold": True, "bg_color": "#BF8F00", "font_color": "white", "border": 1
    })
    for col_num, value in enumerate(df.columns):
        ws.write(0, col_num, value, header_fmt)
        ws.set_column(col_num, col_num, 16)
    ws.freeze_panes(1, 0)
    ws.autofilter(0, 0, len(df), len(df.columns) - 1)

    ws.data_validation(1, 3, len(df), 3, {
        "validate": "list",
        "source": ["未投递", "已投递", "笔试", "一面", "二面", "HR面", "Offer", "拒绝", "放弃"],
    })


def _parse_salary_daily(salary_str: str) -> float:
    """Try to extract a daily salary number from strings like '300-350元/天' or '15-25K/月'."""
    s = salary_str.replace(" ", "")

    m = re.search(r"(\d+)-?(\d+)?元/天", s)
    if m:
        lo = int(m.group(1))
        hi = int(m.group(2)) if m.group(2) else lo
        return (lo + hi) / 2

    m = re.search(r"(\d+)-?(\d+)?[kK]/月", s)
    if m:
        lo = int(m.group(1)) * 1000
        hi = int(m.group(2)) * 1000 if m.group(2) else lo
        return (lo + hi) / 2 / 22

    m = re.search(r"(\d+)-?(\d+)?元/月", s)
    if m:
        lo = int(m.group(1))
        hi = int(m.group(2)) if m.group(2) else lo
        return (lo + hi) / 2 / 22

    return 0.0
