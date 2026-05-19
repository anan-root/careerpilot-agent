"""AnalystAgent -- JD parsing, 10-dimension scoring, company profiling."""

from __future__ import annotations

import json
import yaml
from pathlib import Path

from llm_client import chat_json, chat
import db

PROFILE_PATH = Path(__file__).resolve().parent.parent / "data" / "profile.yaml"
CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.yaml"


def _load_profile() -> dict:
    with open(PROFILE_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _load_scoring_config() -> dict:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)["scoring"]


def analyze_jd(jd_text: str) -> dict:
    """Extract structured info from a job description."""
    prompt = f"""分析以下招聘JD，提取结构化信息。

JD内容：
{jd_text}

请返回JSON格式：
{{
  "title": "岗位名称",
  "company": "公司名",
  "location": "工作地点",
  "salary": "薪资范围",
  "job_type": "实习类型(日常实习/暑期实习/校招/社招)",
  "required_skills": ["必需技能1", "必需技能2"],
  "preferred_skills": ["加分技能1", "加分技能2"],
  "basic_requirements": ["学历要求", "其他基础要求"],
  "responsibilities": ["职责1", "职责2"],
  "keywords": ["关键词1", "关键词2"]
}}"""
    return chat_json(prompt)


def score_job(job_data: dict) -> tuple[float, dict]:
    """Score a job on 10 dimensions. Returns (total_score, detail_dict)."""
    profile = _load_profile()
    cfg = _load_scoring_config()
    weights = cfg["weights"]
    gate = cfg["gate_threshold"]

    skills_text = json.dumps(profile["skills"], ensure_ascii=False)
    projects_text = "\n".join(
        f"- {p['name']}: {p['description']}" for p in profile["projects"]
    )

    prompt = f"""你是一个资深求职顾问。请对以下岗位进行10维度评分（0-10分）。

## 求职者背景
技能: {skills_text}
项目: {projects_text}
目标: {profile['basics']['target_role']}
地点偏好: {profile['basics']['location']}

## 岗位信息
{json.dumps(job_data, ensure_ascii=False, indent=2)}

## 评分维度（每个0-10分）
1. role_match: 岗位方向是否匹配AI/Agent（门槛维度）
2. skill_alignment: 必需技能的覆盖率（门槛维度）
3. salary: 薪资竞争力
4. location: 地理便利性（武汉优先）
5. company_stage: 公司发展阶段（大厂/独角兽/创业）
6. tech_stack: 技术栈先进度
7. growth_potential: 成长潜力（转正/晋升）
8. interview_difficulty: 面试通过可能性（10=很可能通过）
9. timeline_match: 时间匹配度
10. work_life_balance: 工作生活平衡

返回JSON:
{{
  "role_match": 8,
  "skill_alignment": 7,
  "salary": 6,
  "location": 9,
  "company_stage": 7,
  "tech_stack": 8,
  "growth_potential": 7,
  "interview_difficulty": 6,
  "timeline_match": 8,
  "work_life_balance": 7,
  "reasoning": "简要评分理由"
}}"""

    scores = chat_json(prompt)
    reasoning = scores.pop("reasoning", "")

    role_gate = scores.get("role_match", 0) / 10.0
    skill_gate = scores.get("skill_alignment", 0) / 10.0
    if role_gate < gate or skill_gate < gate:
        total = 0.0
    else:
        total = sum(
            (scores.get(dim, 0) / 10.0) * w
            for dim, w in weights.items()
        )

    details = {**scores, "total": round(total, 3), "reasoning": reasoning}
    return round(total, 3), details


def profile_company(company_name: str) -> dict:
    """Generate a company profile with pros/cons/rating."""
    prompt = f"""分析公司"{company_name}"，生成公司画像。

请返回JSON:
{{
  "name": "{company_name}",
  "industry": "所属行业",
  "size": "公司规模(人数)",
  "description": "一句话描述",
  "rating": 7.5,
  "pros": ["优点1", "优点2"],
  "cons": ["缺点1", "缺点2"],
  "avg_salary": "实习生平均日薪",
  "work_life_balance": "加班情况描述",
  "tech_reputation": "技术口碑"
}}"""
    return chat_json(prompt)
