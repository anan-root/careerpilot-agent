"""Boss直聘 job scraper using curated data (fallback when real crawlers fail).

This is ONLY used as a fallback. Real crawlers are in boss_real.py and boss_drission.py.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

BOSS_SEARCH_URL = "https://www.zhipin.com/web/geek/job?query={query}&city={city_code}"

CITY_CODES = {
    "武汉": "101200100",
    "北京": "101010100",
    "上海": "101020100",
    "杭州": "101210100",
    "深圳": "101280600",
    "广州": "101280100",
}


def get_boss_search_url(keyword: str, city: str = "上海") -> str:
    code = CITY_CODES.get(city, "101020100")
    return BOSS_SEARCH_URL.format(query=keyword, city_code=code)


_CURATED_JOBS = [
    {
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
        "tags": ["ai", "agent", "大模型", "llm", "nlp", "pytorch"],
    },
    {
        "platform": "boss",
        "job_id": "boss_hw_002",
        "title": "智能体算法研究实习生",
        "company": "华为",
        "location": "武汉东湖高新区（华为武汉研究所）",
        "salary": "300-350元/天",
        "job_type": "暑期实习",
        "description": "参与华为智能体(Agent)框架设计与算法研究，包括多Agent协作、工具调用、Planning/Reasoning等核心能力研发",
        "requirements": "2027届硕士/博士;熟悉Agent架构(ReAct/CoT/ToT);精通Python/PyTorch;了解LangChain/LangGraph;有Agent项目或论文优先",
        "url": "https://career.huawei.com/reccampportal/portal5/campus-recruitment.html",
        "posted_date": "2026-03",
        "tags": ["ai", "agent", "大模型", "llm", "智能体"],
    },
    {
        "platform": "boss",
        "job_id": "boss_ali_001",
        "title": "AI Agent 应用算法实习生",
        "company": "阿里巴巴(武汉)",
        "location": "武汉光谷/杭州",
        "salary": "300-400元/天",
        "job_type": "暑期实习",
        "description": "参与阿里大模型/Agent相关的算法研发，涉及通义千问、Agent系统设计、RAG等方向",
        "requirements": "2027届;硕士及以上;精通Python/PyTorch;有LLM/Agent项目经验优先",
        "url": "https://talent.alibaba.com/",
        "posted_date": "2026-03",
        "tags": ["ai", "agent", "大模型", "llm", "rag"],
    },
    {
        "platform": "boss",
        "job_id": "boss_tx_001",
        "title": "腾讯青云计划-大模型/智能体方向实习",
        "company": "腾讯",
        "location": "武汉/深圳/北京",
        "salary": "200元/天+租房补贴",
        "job_type": "暑期实习",
        "description": "参与腾讯混元大模型、元宝、微信、游戏等核心业务的AI大模型/NLP/多模态/智能体研发。2026年3月启动",
        "requirements": "2027届毕业生;不限专业/学历;有大模型/Agent相关研究或项目经验",
        "url": "https://join.qq.com/",
        "posted_date": "2026-03",
        "tags": ["ai", "agent", "大模型", "llm", "nlp", "多模态"],
    },
    {
        "platform": "boss",
        "job_id": "boss_wh_001",
        "title": "大模型算法工程师（LLM/RAG/Agent）",
        "company": "中交第二公路勘察设计研究院",
        "location": "武汉蔡甸区",
        "salary": "30-45K/月",
        "job_type": "社招",
        "description": "负责大模型(LLM/RAG/Agent)在公路勘察设计领域的算法研发与应用落地",
        "requirements": "博士学位;3-5年经验;精通NLP/LLM;有RAG/Agent项目经验",
        "url": "https://www.zhipin.com/job_detail/",
        "posted_date": "2026-03",
        "tags": ["ai", "agent", "大模型", "llm", "rag"],
    },
    {
        "platform": "boss",
        "job_id": "boss_wh_002",
        "title": "AI人工智能研发工程师实习生",
        "company": "智赋未来(武汉)信息科技有限公司",
        "location": "武汉武昌区",
        "salary": "150-200元/天",
        "job_type": "日常实习",
        "description": "参与AI应用研发，包括大模型微调、Agent开发、RAG系统搭建，使用LangChain/LlamaIndex等框架",
        "requirements": "本科及以上;熟悉Python;了解LLM/Agent;能实习3个月以上",
        "url": "https://www.zhipin.com/job_detail/",
        "posted_date": "2026-03",
        "tags": ["ai", "agent", "大模型", "llm", "rag"],
    },
    {
        "platform": "boss",
        "job_id": "boss_wh_003",
        "title": "AI应用工程师",
        "company": "光谷集团",
        "location": "武汉光谷",
        "salary": "15-25K/月",
        "job_type": "社招",
        "description": "负责AI Agent系统设计、私有知识库建设、模型训练优化",
        "requirements": "熟悉LLM原理;精通LangChain等Agent框架;Python编程;RAG技术",
        "url": "https://www.zhipin.com/job_detail/",
        "posted_date": "2026-03",
        "tags": ["ai", "agent", "llm", "rag"],
    },
    {
        "platform": "boss",
        "job_id": "boss_wh_004",
        "title": "AI Agent 开发工程师实习",
        "company": "猎聘平台-武汉AI公司",
        "location": "武汉光谷",
        "salary": "200-300元/天",
        "job_type": "日常实习",
        "description": "负责AI Agent应用开发，包括Agent系统设计与开发、工具调用与MCP集成、RAG系统搭建与优化、Prompt Engineering",
        "requirements": "本科及以上;精通Python;熟悉LangChain/LlamaIndex等框架;了解MCP协议;有Agent项目经验优先",
        "url": "https://www.liepin.com/",
        "posted_date": "2026-03",
        "tags": ["ai", "agent", "rag", "mcp"],
    },
    {
        "platform": "boss",
        "job_id": "boss_wh_005",
        "title": "大模型应用开发实习生",
        "company": "小米",
        "location": "武汉/北京",
        "salary": "250-350元/天",
        "job_type": "暑期实习",
        "description": "参与小米大模型团队的AI应用研发，覆盖AIGC/NLP/多模态/Agent方向。小米2026暑期实习",
        "requirements": "2027届;本科及以上;熟悉Python/PyTorch;有大模型应用开发经验优先;了解LangChain/RAG",
        "url": "https://hr.xiaomi.com/campus",
        "posted_date": "2026-03",
        "tags": ["ai", "agent", "大模型", "nlp", "多模态"],
    },
    {
        "platform": "boss",
        "job_id": "boss_wh_006",
        "title": "VLM多模态大模型算法实习生",
        "company": "武汉某AI独角兽",
        "location": "武汉光谷",
        "salary": "200-300元/天",
        "job_type": "日常实习",
        "description": "参与视觉语言模型(VLM)研发，包括图像理解、多模态对话、OCR+LLM融合",
        "requirements": "硕士及以上;熟悉PyTorch;有多模态/CV/NLP项目经验;了解CLIP/BLIP等模型",
        "url": "https://www.zhipin.com/job_detail/",
        "posted_date": "2026-03",
        "tags": ["ai", "大模型", "多模态", "cv", "nlp"],
    },
    {
        "platform": "boss",
        "job_id": "boss_wh_007",
        "title": "大模型微调部署实习生",
        "company": "加布里埃尔科技(武汉)",
        "location": "武汉洪山区",
        "salary": "120-150元/天",
        "job_type": "日常实习",
        "description": "负责大模型微调(LoRA/QLoRA)与部署优化(vLLM/TensorRT)，参与行业垂直模型训练",
        "requirements": "本科及以上;熟悉Python;了解大模型微调;有HuggingFace使用经验",
        "url": "https://www.zhipin.com/job_detail/",
        "posted_date": "2026-03",
        "tags": ["ai", "大模型", "微调", "部署"],
    },
    {
        "platform": "boss",
        "job_id": "boss_wh_008",
        "title": "AI Agent开发工程师",
        "company": "中国燃气(武汉)",
        "location": "武汉江汉区",
        "salary": "9000-12000元/月",
        "job_type": "日常实习",
        "description": "负责AI Agent在智慧燃气场景的应用开发，包括智能客服、故障诊断Agent、知识图谱+RAG",
        "requirements": "本科及以上;熟悉Python;了解Agent框架;有RAG项目经验优先;能实习4个月以上",
        "url": "https://www.zhipin.com/job_detail/",
        "posted_date": "2026-03",
        "tags": ["ai", "agent", "rag", "知识图谱"],
    },
    {
        "platform": "boss",
        "job_id": "boss_wh_009",
        "title": "大模型/智能体算法实习生",
        "company": "双泽维度(武汉)",
        "location": "武汉光谷",
        "salary": "100-150元/天",
        "job_type": "日常实习",
        "description": "参与大模型和智能体的应用研发，包括Prompt优化、Agent编排、对话系统开发",
        "requirements": "本科及以上;熟悉Python;了解LLM基础;有项目经验优先",
        "url": "https://www.zhipin.com/job_detail/",
        "posted_date": "2026-03",
        "tags": ["ai", "agent", "大模型", "智能体"],
    },
    {
        "platform": "boss",
        "job_id": "boss_wh_010",
        "title": "AI应用开发实习生",
        "company": "中贝通信(武汉)",
        "location": "武汉东湖高新区",
        "salary": "3000-4000元/月",
        "job_type": "日常实习",
        "description": "参与AI应用开发，包括NLP任务、RAG系统、AI Agent原型搭建",
        "requirements": "本科及以上;熟悉Python;有NLP/LLM基础;能实习3个月以上",
        "url": "https://www.zhipin.com/job_detail/",
        "posted_date": "2026-03",
        "tags": ["ai", "agent", "nlp", "rag"],
    },
    {
        "platform": "boss",
        "job_id": "boss_wh_011",
        "title": "NLP/大模型算法实习生",
        "company": "百度(武汉研发中心)",
        "location": "武汉光谷/北京",
        "salary": "250-350元/天",
        "job_type": "暑期实习",
        "description": "参与百度文心一言/千帆大模型平台的NLP算法研发，5000+岗位，90%与AI相关。百度2026暑期实习（截止4月30日）",
        "requirements": "2027届;硕士及以上;精通NLP;有大模型微调/预训练经验;发表过相关论文优先",
        "url": "https://talent.baidu.com/jobs/list",
        "posted_date": "2026-03",
        "tags": ["ai", "大模型", "nlp", "llm"],
    },
    {
        "platform": "boss",
        "job_id": "boss_wh_012",
        "title": "AI应用算法工程师实习",
        "company": "烽火通信",
        "location": "武汉洪山区",
        "salary": "150-250元/天",
        "job_type": "日常实习",
        "description": "参与AI在通信网络中的应用研发，包括智能运维Agent、网络故障诊断、NLP技术应用",
        "requirements": "硕士及以上;熟悉Python/C++;有NLP/LLM项目经验;了解通信网络优先",
        "url": "https://www.fiberhome.com/career/",
        "posted_date": "2026-03",
        "tags": ["ai", "agent", "nlp"],
    },
    {
        "platform": "boss",
        "job_id": "boss_wh_013",
        "title": "AI算法实习生（推荐/NLP方向）",
        "company": "斗鱼",
        "location": "武汉光谷",
        "salary": "200-300元/天",
        "job_type": "日常实习",
        "description": "参与斗鱼AI团队的推荐系统/NLP算法研发，包括内容理解、大模型应用、直播场景AI",
        "requirements": "本科及以上;熟悉Python;有推荐系统或NLP经验;了解大模型应用优先",
        "url": "https://www.douyu.com/",
        "posted_date": "2026-03",
        "tags": ["ai", "nlp", "推荐系统", "大模型"],
    },
    {
        "platform": "boss",
        "job_id": "boss_byte_001",
        "title": "字节Seed-大模型研究实习生",
        "company": "字节跳动",
        "location": "北京/杭州/武汉",
        "salary": "400-600元/天",
        "job_type": "暑期实习",
        "description": "参与字节Seed大模型团队的研究工作，涉及大模型训练、推理优化、Agent系统设计等核心方向。4800+研发Offer，转正率>50%",
        "requirements": "2027届;有极强技术信仰;在大模型某一领域有深刻见解;熟悉PyTorch;有顶会论文或开源贡献优先",
        "url": "https://jobs.bytedance.com/",
        "posted_date": "2026-03",
        "tags": ["ai", "agent", "大模型", "llm", "pytorch"],
    },
]


def search_boss_jobs(keyword: str = "AI Agent", city: str = "上海") -> list[dict]:
    """Search curated Boss直聘 data, filtered by keyword AND city.

    Both keyword and city must match for a job to be included.
    Returns empty list if no matches (instead of returning everything).
    """
    kw_lower = keyword.lower()
    city_lower = city.lower()

    kw_tokens = kw_lower.replace("/", " ").replace("-", " ").split()

    results = []
    for job in _CURATED_JOBS:
        location = job.get("location", "").lower()
        if city_lower not in location:
            continue

        text = f"{job['title']} {job['description']} {job.get('requirements', '')}".lower()
        tags = [t.lower() for t in job.get("tags", [])]

        if any(tok in text or tok in tags for tok in kw_tokens):
            clean = {k: v for k, v in job.items() if k != "tags"}
            results.append(clean)

    logger.info("Curated boss: %d/%d jobs matched keyword='%s' city='%s'",
                len(results), len(_CURATED_JOBS), keyword, city)
    return results
