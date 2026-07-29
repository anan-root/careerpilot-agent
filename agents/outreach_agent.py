"""Controlled BOSS greeting and reply draft generation."""

from __future__ import annotations

import json
import re
from typing import Any

from llm_client import chat_json

DEFAULT_GREETING_CONSTRAINT = "语气礼貌、具体，突出真实技能或项目证据，不提薪资，不夸大经历。"
DEFAULT_REPLY_CONSTRAINT = "语气礼貌、简洁，基于对方消息回应，不承诺简历里没有的经历。"
SYSTEM_BOUNDARY = (
    "你是求职沟通助手。只能根据给定简历画像、岗位信息和匹配结论生成文本。"
    "不得添加未提供的公司经历、工作年限、证书或项目成果。"
)


def normalize_max_chars(value: object, default: int = 100) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = int(default)
    return max(20, min(300, number))


def generate_boss_greeting(
    job: dict,
    profile: dict | None = None,
    match: dict | None = None,
    *,
    max_chars: int = 100,
    custom_prompt: str = "",
) -> dict:
    """Generate an editable BOSS greeting draft."""
    max_chars = normalize_max_chars(max_chars)
    prompt = _greeting_prompt(job, profile or {}, match or {}, max_chars, custom_prompt)
    try:
        data = chat_json(prompt, system=SYSTEM_BOUNDARY + " 输出必须是合法 JSON。")
        message = _clean_message(data.get("message"), max_chars)
        if not message:
            raise ValueError("empty greeting")
        return _result(message, "llm", max_chars, custom_prompt, data.get("notes"))
    except Exception as exc:
        message = _fallback_greeting(job, profile or {}, max_chars)
        return _result(message, "fallback", max_chars, custom_prompt, [f"LLM 未返回可用草稿：{exc}"])


def generate_boss_reply(
    job: dict,
    profile: dict | None = None,
    hr_message: str = "",
    *,
    max_chars: int = 120,
    custom_prompt: str = "",
) -> dict:
    """Generate an editable reply draft from an HR message or pasted chat text."""
    max_chars = normalize_max_chars(max_chars, default=120)
    prompt = _reply_prompt(job, profile or {}, hr_message, max_chars, custom_prompt)
    try:
        data = chat_json(prompt, system=SYSTEM_BOUNDARY + " 输出必须是合法 JSON。")
        message = _clean_message(data.get("message"), max_chars)
        if not message:
            raise ValueError("empty reply")
        return _result(message, "llm", max_chars, custom_prompt, data.get("notes"))
    except Exception as exc:
        message = _fallback_reply(hr_message, max_chars)
        return _result(message, "fallback", max_chars, custom_prompt, [f"LLM 未返回可用回复：{exc}"])


def _greeting_prompt(job: dict, profile: dict, match: dict, max_chars: int, custom_prompt: str) -> str:
    payload = {
        "job": _job_summary(job),
        "profile": _profile_summary(profile),
        "match": _match_summary(match or job),
        "max_chars": max_chars,
        "user_constraints": custom_prompt.strip() or DEFAULT_GREETING_CONSTRAINT,
        "fixed_rules": [
            "只生成一条打招呼文本",
            "不添加未给出的经历",
            "不要写薪资诉求，除非用户约束明确要求",
            "输出 JSON：message 为最终文本，notes 为简短说明数组",
        ],
    }
    return "请根据下面 JSON 生成 BOSS 打招呼草稿：\n" + json.dumps(payload, ensure_ascii=False, indent=2)


def _reply_prompt(job: dict, profile: dict, hr_message: str, max_chars: int, custom_prompt: str) -> str:
    payload = {
        "job": _job_summary(job),
        "profile": _profile_summary(profile),
        "hr_message_or_chat_text": str(hr_message or "").strip()[:2000],
        "max_chars": max_chars,
        "user_constraints": custom_prompt.strip() or DEFAULT_REPLY_CONSTRAINT,
        "fixed_rules": [
            "只生成一条回复建议",
            "不添加未给出的经历",
            "遇到不确定信息，用可沟通的表达，不替用户做承诺",
            "输出 JSON：message 为最终文本，notes 为简短说明数组",
        ],
    }
    return "请根据下面 JSON 生成 BOSS 回复建议：\n" + json.dumps(payload, ensure_ascii=False, indent=2)


def _job_summary(job: dict) -> dict:
    keys = (
        "title",
        "company",
        "location",
        "salary",
        "degree",
        "experience",
        "skills",
        "requirements",
        "description",
        "full_jd",
        "hr_name",
        "hr_title",
    )
    return {key: _clip(job.get(key), 500) for key in keys if str(job.get(key) or "").strip()}


def _profile_summary(profile: dict) -> dict:
    projects = []
    for project in (profile.get("projects") or [])[:3]:
        if isinstance(project, dict):
            projects.append({
                "name": _clip(project.get("name"), 80),
                "summary": _clip(project.get("summary"), 160),
                "keywords": [str(item) for item in (project.get("keywords") or [])[:8]],
            })
        else:
            projects.append({"name": _clip(project, 80)})
    return {
        "target_roles": [str(item) for item in (profile.get("target_roles") or [])[:5]],
        "skills": [str(item) for item in (profile.get("skills") or [])[:16]],
        "projects": projects,
        "strengths": [str(item) for item in (profile.get("strengths") or [])[:8]],
        "experience_years": profile.get("experience_years"),
        "evidence_note": profile.get("evidence_note", ""),
    }


def _match_summary(match: dict) -> dict:
    decision = match.get("job_decision") if isinstance(match.get("job_decision"), dict) else {}
    ai_match = match.get("ai_match") if isinstance(match.get("ai_match"), dict) else {}
    resume_match = match.get("resume_match") if isinstance(match.get("resume_match"), dict) else {}
    return {
        "score": decision.get("score") or resume_match.get("score") or ai_match.get("score"),
        "level": decision.get("level") or ai_match.get("level"),
        "matched_reasons": (decision.get("matched_reasons") or ai_match.get("matched_evidence") or resume_match.get("matched_keywords") or [])[:5],
        "risks": (decision.get("risks") or ai_match.get("risk_points") or [])[:5],
    }


def _fallback_greeting(job: dict, profile: dict, max_chars: int) -> str:
    title = str(job.get("title") or "这个岗位").strip()
    company = str(job.get("company") or "").strip()
    skills = [str(item).strip() for item in (profile.get("skills") or []) if str(item).strip()]
    projects = [
        str(project.get("name") or project.get("summary") or "").strip()
        for project in (profile.get("projects") or [])
        if isinstance(project, dict)
    ]
    target = f"{company}{title}" if company else title
    parts = [f"您好，我对{target}很感兴趣"]
    if skills:
        parts.append(f"我有{ '、'.join(skills[:3]) }相关实践")
    if projects:
        parts.append(f"做过{projects[0][:18]}相关项目")
    parts.append("希望有机会进一步沟通。")
    return _clean_message("，".join(parts), max_chars)


def _fallback_reply(hr_message: str, max_chars: int) -> str:
    text = str(hr_message or "")
    if any(token in text for token in ("面试", "沟通", "电话", "时间")):
        message = "您好，可以的。我方便进一步沟通，您看这边需要我补充哪些项目或技能信息？"
    elif any(token in text for token in ("简历", "作品", "项目")):
        message = "您好，可以。我可以重点补充项目背景、技术栈和个人负责部分，方便您判断匹配度。"
    else:
        message = "您好，感谢回复。我对这个岗位比较感兴趣，可以继续了解岗位职责和技术要求。"
    return _clean_message(message, max_chars)


def _result(message: str, source: str, max_chars: int, custom_prompt: str, notes: Any = None) -> dict:
    warnings = []
    if len(message) > max_chars:
        warnings.append(f"草稿超过 {max_chars} 字，已截断。")
    return {
        "message": _clean_message(message, max_chars),
        "source": source,
        "max_chars": max_chars,
        "custom_prompt": custom_prompt,
        "notes": _as_list(notes),
        "warnings": warnings,
    }


def _clean_message(value: object, max_chars: int) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    text = text.strip("` \n\r\t")
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip("，。,.；;、 ")


def _clip(value: object, limit: int) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text[:limit]


def _as_list(value: Any) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []
