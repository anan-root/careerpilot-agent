"""Resume parsing, job matching, and targeted advice generation."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Iterable

from llm_client import chat, chat_json

TEXT_EXTENSIONS = {".txt", ".md", ".tex"}
SUPPORTED_EXTENSIONS = TEXT_EXTENSIONS | {".pdf", ".docx"}

STOPWORDS = {
    "and", "or", "the", "with", "for", "from", "this", "that", "you", "your",
    "岗位", "要求", "职责", "负责", "熟悉", "掌握", "优先", "相关", "能力",
    "工作", "项目", "经验", "公司", "职位", "实习", "开发", "工程师",
}

TECH_TERMS = [
    "Python", "Java", "JavaScript", "TypeScript", "C++", "Go", "SQL",
    "PyTorch", "TensorFlow", "Transformers", "HuggingFace", "LangChain",
    "LangGraph", "FastAPI", "Flask", "Django", "React", "Vue", "Docker",
    "Kubernetes", "Linux", "Git", "MySQL", "PostgreSQL", "Redis",
    "Elasticsearch", "MinIO", "Pandas", "NumPy", "Scikit-learn",
    "大模型", "LLM", "Agent", "AI Agent", "智能体", "RAG", "检索增强",
    "向量检索", "Embedding", "ReRanker", "BM25", "Prompt", "Function Calling",
    "MCP", "微调", "SFT", "DPO", "RLHF", "LoRA", "MoE", "Transformer",
    "Tokenizer", "多模态", "NLP", "CV", "推荐系统", "机器学习", "深度学习",
    "算法", "后端", "前端", "全栈", "爬虫", "数据分析", "数据挖掘",
    "实习", "校招", "工程化", "分布式", "高并发", "数据库", "API",
]


def extract_resume_text(file_path: str | Path) -> str:
    """Extract text from a resume file."""
    path = Path(file_path)
    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"暂不支持 {suffix}，请上传 PDF、DOCX、TXT、MD 或 TEX。")

    if suffix in TEXT_EXTENSIONS:
        return _normalize_text(path.read_text(encoding="utf-8", errors="ignore"))
    if suffix == ".pdf":
        return _extract_pdf_text(path)
    if suffix == ".docx":
        return _extract_docx_text(path)
    raise ValueError(f"暂不支持 {suffix}。")


def analyze_resume(resume_text: str) -> dict:
    """Use the LLM to turn raw resume text into structured evidence."""
    prompt = f"""请解析以下简历，提取结构化信息。只基于原文，不要编造。

简历原文：
{_clip(resume_text, 12000)}

返回 JSON：
{{
  "name": "姓名或空字符串",
  "target_role": "候选目标岗位，如无法判断则为空",
  "education": ["教育经历要点"],
  "skills": ["技能关键词"],
  "projects": [
    {{
      "name": "项目名",
      "summary": "项目一句话摘要",
      "evidence": ["能证明能力的原文要点"]
    }}
  ],
  "strengths": ["优势"],
  "risks": ["简历中的明显短板或不清楚处"]
}}"""
    try:
        return chat_json(prompt, system="你是严谨的招聘简历解析助手，输出必须是合法 JSON。")
    except Exception:
        return _fallback_resume_profile(resume_text)


def rank_jobs_for_resume(
    resume_text: str,
    jobs: Iterable[dict],
    *,
    top_n: int | None = 20,
    ai_top_n: int = 0,
) -> list[dict]:
    """Rank jobs by resume fit. Heuristic first, optional LLM refinement."""
    resume_keywords = set(_extract_keywords(resume_text))
    ranked: list[dict] = []

    for job in jobs:
        match = _score_job_against_resume(resume_text, resume_keywords, job)
        ranked.append({**job, "resume_match": match})

    ranked.sort(key=lambda j: j["resume_match"]["score"], reverse=True)

    if ai_top_n > 0:
        for job in ranked[:ai_top_n]:
            ai_match = deep_match_resume_to_job(resume_text, job)
            job["resume_match"]["ai"] = ai_match
            ai_score = ai_match.get("score")
            if isinstance(ai_score, (int, float)):
                job["resume_match"]["score"] = round((job["resume_match"]["score"] * 0.4) + (ai_score * 0.6), 1)
        ranked.sort(key=lambda j: j["resume_match"]["score"], reverse=True)

    if top_n is not None:
        return ranked[:top_n]
    return ranked


def deep_match_resume_to_job(resume_text: str, job: dict) -> dict:
    """Ask the LLM for a strict resume-to-job fit score."""
    prompt = f"""你是严格的招聘筛选官。请判断这份简历和岗位的匹配度。

规则：
- 只基于简历原文和岗位信息，不要替候选人编造经历。
- 分数为 0-100，越高代表越值得优先投递。
- 明确指出证据、缺口和风险。

简历原文：
{_clip(resume_text, 12000)}

岗位信息：
{json.dumps(_job_for_prompt(job), ensure_ascii=False, indent=2)}

返回 JSON：
{{
  "score": 82,
  "level": "强匹配/可尝试/需补强/不建议",
  "matched_evidence": ["简历中已经覆盖岗位需求的证据"],
  "missing_keywords": ["岗位需要但简历缺少的关键词"],
  "risks": ["HR或面试官可能质疑的点"],
  "reasoning": "100字以内解释"
}}"""
    try:
        data = chat_json(prompt, system="你是严谨的招聘匹配评估助手，输出必须是合法 JSON。")
        data["score"] = _safe_score(data.get("score", 0))
        return data
    except Exception as exc:
        return {
            "score": None,
            "level": "AI分析失败",
            "matched_evidence": [],
            "missing_keywords": [],
            "risks": [str(exc)],
            "reasoning": "",
        }


def generate_resume_job_advice(resume_text: str, job: dict) -> str:
    """Generate resume optimization and interview advice for one target job."""
    prompt = f"""请基于候选人的真实简历和目标岗位，生成简历优化意见和面试建议。

要求：
1. 不要编造经历；如果缺少信息，标注“需要补充证据”。
2. 优先给出能直接改简历的建议。
3. 面试建议要围绕岗位 JD 和简历中的项目。
4. 中文输出，结构清晰。

简历原文：
{_clip(resume_text, 14000)}

目标岗位：
{json.dumps(_job_for_prompt(job), ensure_ascii=False, indent=2)}

请按以下结构输出 Markdown：
## 匹配结论
## 简历优化建议
## 可直接改写的简历要点
## 面试准备重点
## 面试官可能追问
## 投递前检查清单"""
    return chat(prompt, system="你是专业但诚实的求职顾问，严格反对简历编造。", max_tokens=6000)


def build_match_report(ranked_jobs: list[dict]) -> str:
    """Create a local Markdown report for matched jobs."""
    lines = ["# 简历岗位匹配报告", ""]
    for i, job in enumerate(ranked_jobs, 1):
        match = job.get("resume_match", {})
        lines.extend([
            f"## {i}. {job.get('company', '')} - {job.get('title', '')}",
            f"- 匹配分：{match.get('score', 0)}",
            f"- 地点：{job.get('location', '')}",
            f"- 薪资：{job.get('salary', '')}",
            f"- 来源：{job.get('platform', '')}",
            f"- 命中关键词：{', '.join(match.get('matched_keywords', [])[:20]) or '暂无'}",
            f"- 缺口关键词：{', '.join(match.get('missing_keywords', [])[:20]) or '暂无'}",
            f"- 建议：{match.get('summary', '')}",
            "",
        ])
    return "\n".join(lines)


def _extract_pdf_text(path: Path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError("解析 PDF 需要安装 pypdf：pip install pypdf") from exc

    reader = PdfReader(str(path))
    parts = [page.extract_text() or "" for page in reader.pages]
    return _normalize_text("\n".join(parts))


def _extract_docx_text(path: Path) -> str:
    try:
        from docx import Document
    except ImportError as exc:
        raise RuntimeError("解析 DOCX 需要安装 python-docx：pip install python-docx") from exc

    doc = Document(str(path))
    parts = [p.text for p in doc.paragraphs if p.text.strip()]
    for table in doc.tables:
        for row in table.rows:
            parts.extend(cell.text for cell in row.cells if cell.text.strip())
    return _normalize_text("\n".join(parts))


def _fallback_resume_profile(text: str) -> dict:
    keywords = _extract_keywords(text)
    email = re.search(r"[\w.+-]+@[\w.-]+\.\w+", text)
    phone = re.search(r"(?:\+?86[- ]?)?1[3-9]\d{9}", text)
    return {
        "name": "",
        "target_role": "",
        "education": [],
        "skills": keywords[:40],
        "projects": [],
        "strengths": keywords[:15],
        "risks": ["未调用 AI 解析，仅使用本地关键词提取。"],
        "contact": {
            "email": email.group(0) if email else "",
            "phone": phone.group(0) if phone else "",
        },
    }


def _score_job_against_resume(resume_text: str, resume_keywords: set[str], job: dict) -> dict:
    job_text = _job_text(job)
    job_keywords = set(_extract_keywords(job_text))
    skill_keywords = set(_extract_keywords(" ".join(str(job.get(k, "")) for k in ("skills", "requirements", "description", "full_jd"))))

    matched = sorted(resume_keywords & job_keywords, key=lambda x: (-len(x), x))
    skill_matched = sorted(resume_keywords & skill_keywords, key=lambda x: (-len(x), x))
    missing = sorted(skill_keywords - resume_keywords, key=lambda x: (-len(x), x))

    keyword_score = _ratio_score(len(matched), max(len(job_keywords), 1), cap=0.45)
    skill_score = _ratio_score(len(skill_matched), max(len(skill_keywords), 1), cap=0.40)
    title_score = _title_score(resume_keywords, str(job.get("title", "")))
    description_bonus = 8 if any(k in resume_text for k in ("实习", "项目", "工程", "算法", "大模型", "Agent", "RAG")) else 0

    score = min(100.0, keyword_score + skill_score + title_score + description_bonus)
    if score >= 75:
        summary = "简历关键词和岗位要求重合较高，建议优先投递并做定制化优化。"
    elif score >= 55:
        summary = "有一定匹配基础，适合补强关键词和项目证据后投递。"
    elif score >= 35:
        summary = "匹配度一般，建议先判断是否真的符合目标方向。"
    else:
        summary = "当前简历证据较弱，不建议作为优先岗位。"

    return {
        "score": round(score, 1),
        "matched_keywords": matched[:30],
        "skill_matches": skill_matched[:20],
        "missing_keywords": missing[:30],
        "summary": summary,
    }


def _ratio_score(matches: int, total: int, *, cap: float) -> float:
    if total <= 0:
        return 0.0
    return min(matches / total, cap) / cap * (cap * 100)


def _title_score(resume_keywords: set[str], title: str) -> float:
    title_keywords = set(_extract_keywords(title))
    if not title_keywords:
        return 0.0
    overlap = len(resume_keywords & title_keywords) / len(title_keywords)
    return min(overlap * 18, 18)


def _extract_keywords(text: str) -> list[str]:
    text = _normalize_text(text)
    raw = re.findall(r"[A-Za-z][A-Za-z0-9+#./-]{1,}", text)
    lower_text = text.lower()
    for term in TECH_TERMS:
        if term.lower() in lower_text:
            raw.append(term)
    for chunk in re.findall(r"[\u4e00-\u9fff]{2,12}", text):
        if len(chunk) <= 6:
            raw.append(chunk)
    items: list[str] = []
    seen: set[str] = set()
    for token in raw:
        item = token.strip().strip(".,;:()[]{}<>，。；：（）【】")
        key = item.lower()
        if len(item) < 2 or key in STOPWORDS:
            continue
        if key not in seen:
            seen.add(key)
            items.append(item)
    return items


def _job_text(job: dict) -> str:
    fields = [
        "company", "title", "location", "salary", "job_type", "skills",
        "degree", "experience", "description", "requirements", "full_jd",
        "company_industry", "company_stage", "welfare",
    ]
    return "\n".join(str(job.get(k, "")) for k in fields if job.get(k))


def _job_for_prompt(job: dict) -> dict:
    keys = [
        "company", "title", "location", "salary", "job_type", "skills",
        "degree", "experience", "description", "requirements", "full_jd",
        "platform", "url", "source_url",
    ]
    return {k: job.get(k, "") for k in keys if job.get(k)}


def _safe_score(value) -> float:
    try:
        return max(0.0, min(100.0, float(value)))
    except (TypeError, ValueError):
        return 0.0


def _normalize_text(text: str) -> str:
    return re.sub(r"\n{3,}", "\n\n", text.replace("\r\n", "\n")).strip()


def _clip(text: str, limit: int) -> str:
    text = _normalize_text(text)
    if len(text) <= limit:
        return text
    return text[:limit] + "\n\n[内容过长，已截断]"
