"""CoachAgent -- Interview preparation: skill gap analysis, study path, mock questions."""

from __future__ import annotations

import json
from llm_client import chat, chat_json


def extract_skill_tree(jd_info: dict) -> dict:
    """Extract a skill tree from JD: required / preferred / basic."""
    prompt = f"""分析以下岗位要求，提取技能树，分为三级。

岗位信息:
{json.dumps(jd_info, ensure_ascii=False, indent=2)}

返回JSON:
{{
  "required": [
    {{"skill": "技能名", "category": "分类(如LLM/Agent/工程/算法)", "importance": "高/中"}}
  ],
  "preferred": [
    {{"skill": "加分技能", "category": "分类", "importance": "中/低"}}
  ],
  "basic": [
    {{"skill": "基础要求(学历/语言等)", "category": "基础", "importance": "门槛"}}
  ]
}}"""
    return chat_json(prompt)


def generate_study_path(skill_tree: dict, *, target_weeks: int = 4) -> str:
    """Generate a week-by-week study plan from zero to interview-ready."""
    prompt = f"""你是AI面试培训专家。根据以下技能要求，生成从零到面试通关的{target_weeks}周学习计划。

技能要求:
{json.dumps(skill_tree, ensure_ascii=False, indent=2)}

要求：
1. 每周有明确的学习主题和目标
2. 推荐具体的学习资源（GitHub仓库、课程、文档）
3. 每周末有检验标准（能回答的面试题/能完成的小项目）
4. 从最基础开始，逐步深入
5. 最后一周专门用于模拟面试和查漏补缺

格式用Markdown，标题层次清晰。"""

    return chat(prompt, system="你是资深AI面试培训专家，擅长制定系统化学习计划。", max_tokens=8000)


def generate_eight_part_essay(skill_tree: dict) -> str:
    """Generate targeted 八股文 (interview FAQ) for the specific skills."""
    skills_list = [s["skill"] for s in skill_tree.get("required", [])]
    skills_list += [s["skill"] for s in skill_tree.get("preferred", [])]

    prompt = f"""你是AI大模型面试专家。针对以下技能点，生成面试八股文速查手册。

技能点: {', '.join(skills_list)}

要求：
1. 每个技能点3-5个高频面试题
2. 每题包含：题目、核心答案（200字以内）、追问方向
3. 区分"必背"和"了解即可"
4. 包含字节/阿里/腾讯等大厂的真实面试题
5. 在每个知识点后标注[必背]或[了解]

格式用Markdown，结构清晰。"""

    return chat(prompt, system="你是资深AI面试官，熟悉字节、阿里、腾讯的面试风格。", max_tokens=8000)


def generate_mock_questions(jd_info: dict, resume_data: dict | None = None) -> str:
    """Generate mock interview questions that drill deep (Interview-Mentor style)."""
    resume_context = ""
    if resume_data:
        resume_context = f"""
求职者简历摘要: {resume_data.get('summary', '')}
项目经历: {json.dumps(resume_data.get('projects', []), ensure_ascii=False)}
"""

    prompt = f"""你是一个严格的AI Agent岗位面试官（类似字节二面风格）。

岗位信息:
{json.dumps(jd_info, ensure_ascii=False, indent=2)}

{resume_context}

请生成一套完整的模拟面试题（共15题），包括：

## 一、项目拷打（5题）
- 针对简历项目深入追问
- 不接受模糊回答，每题附带2个追问方向
- 关注：架构设计、技术细节、遇到的困难、量化结果

## 二、AI技术深度（5题）
- 覆盖：LLM原理、Agent架构、RAG、Prompt Engineering、MCP
- 每题有标准答案要点和评分标准(1-5分)
- 包含手撕代码题（如：手写Self-Attention）

## 三、基础技术 + 算法（3题）
- Python基础、数据结构、常见算法
- 难度适中，适合实习生

## 四、行为面试 + 反问（2题）
- 用STAR法则准备的行为面试题
- 推荐的反问问题

格式用Markdown，每题标注难度(简单/中等/困难)和考查重点。"""

    return chat(prompt, system="你是严格的技术面试官，不接受模糊回答，会深入追问细节。", max_tokens=8000)


def generate_interview_pack(jd_info: dict, resume_data: dict | None = None) -> dict:
    """Generate a complete interview preparation package."""
    skill_tree = extract_skill_tree(jd_info)
    study_path = generate_study_path(skill_tree)
    eight_part = generate_eight_part_essay(skill_tree)
    mock_qs = generate_mock_questions(jd_info, resume_data)

    return {
        "skill_tree": skill_tree,
        "study_path": study_path,
        "eight_part_essay": eight_part,
        "mock_questions": mock_qs,
    }
