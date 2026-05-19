"""Resume profile Agent with local evidence-first fallback."""

from __future__ import annotations

import re
from datetime import datetime

from agents.resume_matcher import TECH_TERMS, analyze_resume
from memory.store import save_profile

PROFILE_STOPWORDS = {
    "上海", "北京", "深圳", "广州", "杭州", "成都", "南京", "武汉", "苏州",
    "本科", "硕士", "博士", "大专", "项目", "系统", "平台", "使用", "负责",
}


def build_resume_profile(resume_text: str, *, persist: bool = True) -> dict:
    """Build a structured resume profile without inventing missing facts."""
    text = str(resume_text or "").strip()
    if not text:
        return {}

    base = analyze_resume(text)
    profile = normalize_profile(base, text)
    if persist:
        save_profile(profile)
    return profile


def normalize_profile(raw_profile: dict, resume_text: str) -> dict:
    """Normalize LLM/fallback output into the product-level UserProfile shape."""
    skills = _unique([*_as_list(raw_profile.get("skills")), *_extract_tech_terms(resume_text)])
    projects = _normalize_projects(raw_profile.get("projects"), resume_text)
    education = _as_list(raw_profile.get("education"))
    target_roles = _target_roles(raw_profile, skills, resume_text)

    profile = {
        "name": str(raw_profile.get("name") or "").strip(),
        "location": _extract_location(resume_text),
        "target_roles": target_roles,
        "target_role": str(raw_profile.get("target_role") or (target_roles[0] if target_roles else "")).strip(),
        "skills": skills,
        "projects": projects,
        "education": education,
        "experience_years": _estimate_experience_years(resume_text),
        "strengths": _unique(_as_list(raw_profile.get("strengths")) or skills[:8]),
        "gaps": _unique(_as_list(raw_profile.get("risks")) or raw_profile.get("gaps") or []),
        "evidence_note": "所有画像字段仅基于简历文本提取；不确定内容不会当成事实。",
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    return profile


def summarize_profile(profile: dict) -> str:
    if not profile:
        return "还没有简历画像。上传简历后，我会提取技能、项目、学历和求职方向。"

    roles = "、".join(profile.get("target_roles", [])[:3]) or "暂未判断"
    skills = "、".join(profile.get("skills", [])[:12]) or "暂未提取"
    projects = "、".join(p.get("name", "") for p in profile.get("projects", [])[:3] if p.get("name")) or "暂未提取"
    gaps = "、".join(profile.get("gaps", [])[:3]) or "暂无明显短板"
    return f"画像方向：{roles}\n技能关键词：{skills}\n项目证据：{projects}\n可能短板：{gaps}"


def _target_roles(raw_profile: dict, skills: list[str], resume_text: str) -> list[str]:
    roles = _as_list(raw_profile.get("target_roles"))
    single = str(raw_profile.get("target_role") or "").strip()
    if single:
        roles.insert(0, single)

    text = f"{resume_text} {' '.join(skills)}".lower()
    if any(token in text for token in ("ai agent", "agent", "智能体")):
        roles.append("AI Agent 工程师")
    if any(token in text for token in ("rag", "检索增强", "知识库", "向量检索")):
        roles.append("RAG 工程师")
    if any(token in text for token in ("大模型", "llm", "langchain", "langgraph")):
        roles.append("大模型应用开发")
    if any(token in text for token in ("react", "vue", "前端", "typescript")):
        roles.append("前端开发工程师")
    if any(token in text for token in ("fastapi", "django", "spring", "后端")):
        roles.append("后端开发工程师")
    return _unique(roles)[:5] or ["AI Agent 工程师"]


def _normalize_projects(projects: object, resume_text: str) -> list[dict]:
    if isinstance(projects, list) and projects:
        normalized = []
        for project in projects:
            if isinstance(project, dict):
                normalized.append({
                    "name": str(project.get("name") or "").strip(),
                    "summary": str(project.get("summary") or "").strip(),
                    "keywords": _extract_tech_terms(" ".join(map(str, project.values())))[:12],
                    "evidence": _as_list(project.get("evidence"))[:5],
                })
            else:
                normalized.append({"name": str(project), "summary": "", "keywords": [], "evidence": []})
        return [p for p in normalized if p.get("name") or p.get("summary")]

    guessed = []
    for line in re.split(r"[\n。；;]", resume_text):
        clean = line.strip()
        if len(clean) > 8 and any(token in clean for token in ("项目", "系统", "平台", "Agent", "RAG", "大模型")):
            guessed.append({
                "name": clean[:32],
                "summary": clean[:120],
                "keywords": _extract_tech_terms(clean)[:12],
                "evidence": [clean[:160]],
            })
        if len(guessed) >= 5:
            break
    return guessed


def _extract_tech_terms(text: str) -> list[str]:
    lower = str(text or "").lower()
    found = []
    for term in TECH_TERMS:
        if term.lower() in lower:
            found.append(term)
    return _unique(found)


def _estimate_experience_years(text: str) -> int | None:
    years = [int(v) for v in re.findall(r"(\d+)\s*年(?:工作|开发|项目|经验)", text)]
    return max(years) if years else None


def _extract_location(text: str) -> str:
    for city in ("上海", "北京", "深圳", "广州", "杭州", "成都", "南京", "武汉", "苏州", "合肥"):
        if city in text:
            return city
    return ""


def _as_list(value: object) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return [item for item in value if item not in (None, "")]
    if isinstance(value, tuple):
        return [item for item in value if item not in (None, "")]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _unique(items: list) -> list[str]:
    result = []
    for item in items:
        value = str(item or "").strip()
        if value and value not in PROFILE_STOPWORDS and value not in result:
            result.append(value)
    return result
