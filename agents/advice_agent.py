"""Action advice Agent for a selected job."""

from __future__ import annotations


def build_local_job_advice(job: dict, profile: dict | None = None) -> str:
    """Generate concise local advice without an LLM call."""
    profile = profile or {}
    decision = job.get("job_decision") or {}

    lines = [
        f"## {job.get('company', '')} - {job.get('title', '')}",
        "",
        f"推荐等级：{decision.get('level', '未评估')} / 推荐分：{decision.get('score', '')}",
        "",
        "### 为什么可以考虑",
    ]
    reasons = decision.get("matched_reasons") or ["岗位进入候选列表，但还需要结合简历进一步判断。"]
    lines.extend(f"- {item}" for item in reasons)

    risks = decision.get("risks") or []
    lines.extend(["", "### 风险和不确定项"])
    lines.extend(f"- {item}" for item in (risks or ["暂无明显风险；仍建议人工确认公司、岗位真实性和工作制。"]))

    lines.extend(["", "### 简历优化动作"])
    resume_actions = decision.get("resume_actions") or _fallback_resume_actions(job, profile)
    lines.extend(f"- {item}" for item in resume_actions)

    lines.extend(["", "### 面试准备重点"])
    interview_focus = decision.get("interview_focus") or _fallback_interview_focus(job)
    lines.extend(f"- {item}" for item in interview_focus)

    lines.extend(["", "### 打招呼语草稿"])
    lines.append(_greeting(job, profile))
    return "\n".join(lines)


def _fallback_resume_actions(job: dict, profile: dict) -> list[str]:
    skills = str(job.get("skills") or "").replace(",", "、")
    actions = []
    if skills:
        actions.append(f"检查简历中是否有这些关键词的真实证据：{skills[:100]}")
    if profile.get("projects"):
        actions.append("选择最相关的 1 个项目，补充技术难点、你的动作和结果指标")
    actions.append("把岗位职责里的名词映射到简历项目描述中，但不要编造经历")
    return actions


def _fallback_interview_focus(job: dict) -> list[str]:
    text = " ".join(str(job.get(key) or "") for key in ("title", "description", "requirements", "skills"))
    focus = []
    for token in ("RAG", "Agent", "大模型", "LLM", "Prompt", "向量检索", "FastAPI", "React", "Python"):
        if token.lower() in text.lower():
            focus.append(f"准备 {token} 的原理、项目实践和常见追问")
    return focus or ["准备项目介绍、技术选型原因、遇到的问题和量化结果"]


def _greeting(job: dict, profile: dict) -> str:
    skills = "、".join(profile.get("skills", [])[:5])
    role = job.get("title", "该岗位")
    company = job.get("company", "贵公司")
    if skills:
        return f"您好，我关注到{company}的{role}，我的经历和 {skills} 等方向比较相关。想进一步了解岗位要求，也希望有机会投递沟通，谢谢。"
    return f"您好，我关注到{company}的{role}，对岗位方向比较感兴趣。想进一步了解岗位要求，也希望有机会投递沟通，谢谢。"
