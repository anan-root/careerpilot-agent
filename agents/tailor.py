"""TailorAgent -- Resume customization using YAML profile + JD matching."""

from __future__ import annotations

import json
import yaml
import subprocess
import shutil
from pathlib import Path

from llm_client import chat

PROFILE_PATH = Path(__file__).resolve().parent.parent / "data" / "profile.yaml"
TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates" / "latex"
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "data" / "outputs"


def _load_profile() -> dict:
    with open(PROFILE_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def generate_tailored_resume(jd_info: dict, *, include_fabricated: bool = True) -> dict:
    """Generate a tailored resume dict from profile + JD analysis.

    Returns a dict with sections ready for LaTeX rendering.
    """
    profile = _load_profile()

    profile_dump = yaml.dump(profile, allow_unicode=True, default_flow_style=False)
    jd_dump = json.dumps(jd_info, ensure_ascii=False, indent=2)

    prompt = f"""你是一个专业的AI简历顾问。请根据个人资料和目标岗位JD，生成一份高度定制化的简历内容。

## 个人资料 (YAML)
{profile_dump}

## 目标岗位 JD
{jd_dump}

## 要求
1. 使用STAR法则润色项目经历，突出与JD匹配的技能
2. 按JD关键词重新排列技能顺序，最相关的排前面
3. {"基于现有项目方向，合理扩展1-2个与岗位高度匹配的实战项目（标注为规划中）" if include_fabricated else "仅使用真实项目经历"}
4. 生成一段精炼的个人总结（2-3句话），突出与岗位的匹配度
5. 所有内容使用中文

返回JSON格式：
{{
  "name": "姓名",
  "contact": {{
    "email": "...",
    "phone": "...",
    "github": "..."
  }},
  "summary": "个人总结（2-3句话）",
  "education": [
    {{
      "school": "学校",
      "degree": "学位",
      "major": "专业",
      "period": "时间段",
      "gpa": ""
    }}
  ],
  "skills": {{
    "languages": ["按JD相关性排序的编程语言"],
    "frameworks": ["按JD相关性排序的框架"],
    "ai_knowledge": ["按JD相关性排序的AI知识"],
    "tools": ["工具"]
  }},
  "projects": [
    {{
      "name": "项目名",
      "period": "时间段",
      "description": "一句话描述",
      "highlights": ["STAR法则润色的要点1", "要点2", "要点3"],
      "technologies": ["技术栈"],
      "is_fabricated": false
    }}
  ],
  "keywords_injected": ["从JD提取并注入简历的ATS关键词"]
}}"""

    from llm_client import _extract_json
    raw = chat(prompt, system="你是专业简历顾问。必须返回合法JSON，不要包含其他内容。")
    return json.loads(_extract_json(raw))


def render_latex(resume_data: dict, output_name: str) -> Path:
    """Render resume data into a LaTeX PDF."""
    template_path = TEMPLATE_DIR / "resume_template.tex"
    if not template_path.exists():
        raise FileNotFoundError(f"LaTeX template not found: {template_path}")

    from jinja2 import Environment, FileSystemLoader
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        block_start_string="<%",
        block_end_string="%>",
        variable_start_string="<<",
        variable_end_string=">>",
        comment_start_string="<#",
        comment_end_string="#>",
    )
    template = env.get_template("resume_template.tex")
    rendered = template.render(**resume_data)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    tex_path = OUTPUT_DIR / f"{output_name}.tex"
    pdf_path = OUTPUT_DIR / f"{output_name}.pdf"

    tex_path.write_text(rendered, encoding="utf-8")

    result = subprocess.run(
        ["xelatex", "-interaction=nonstopmode", "-output-directory", str(OUTPUT_DIR), str(tex_path)],
        capture_output=True, text=True, timeout=60,
    )

    if pdf_path.exists():
        for ext in (".aux", ".log", ".out"):
            cleanup = OUTPUT_DIR / f"{output_name}{ext}"
            cleanup.unlink(missing_ok=True)
        return pdf_path

    raise RuntimeError(f"LaTeX compilation failed:\n{result.stderr[-2000:]}")


def generate_greeting(jd_info: dict, resume_data: dict) -> str:
    """Generate a personalized greeting message for Boss直聘."""
    prompt = f"""根据以下岗位信息和简历，生成一段Boss直聘打招呼语（80字以内，真诚自然，不要套话）。

岗位: {jd_info.get('title', '')} @ {jd_info.get('company', '')}
核心要求: {', '.join(jd_info.get('required_skills', []))}
我的亮点: {resume_data.get('summary', '')}

要求：
- 直接说明匹配度
- 提到1-2个具体的相关项目/技能
- 表达热情但不过分
- 80字以内"""

    return chat(prompt, system="你是求职者，正在Boss直聘上给HR发打招呼消息。简洁真诚。")
