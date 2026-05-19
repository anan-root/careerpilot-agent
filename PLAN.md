# CareerPilot Agent — 完整调研计划

> 生成时间：2026-04-04
> 状态：Phase 1-6 全部完成 ✅

---

## 项目概述

构建一个以 Agent 为核心交互形态的个人求职智能体，覆盖「岗位采集 → 简历画像 → 推荐决策 → 行动建议 → 求职记忆」链路，优先跑通「上海 AI/Agent 社招」这一完整示例，再逐步封装为可发布的新项目。

## 执行进度

| Phase | 内容 | 状态 |
|-------|------|------|
| Phase 1 | 初始化项目框架 + MiniMax API接入 + 个人YAML数据文件 | ✅ 完成 |
| Phase 2 | 岗位采集引擎 — JobSpy集成 + Boss直聘爬虫 + 牛客抓取 + 公司分析 | ✅ 完成 |
| Phase 3 | 简历生成引擎 — YAML->LaTeX->PDF管线 + LLM定制简历 + ATS优化 | ✅ 完成 |
| Phase 4 | 面试资料生成 — 技能提取 + 学习路径 + 八股文 + 面经聚合 | ✅ 完成 |
| Phase 5 | 端到端Demo — 以武汉大厂AI实习为例跑通全流程 + 批量模式 | ✅ 完成 |
| Phase 6 | 封装发布 — OpenClaw Skill + MCP + CLI + 文档 + Web前端预备 | ✅ 完成 |
| Phase 7 | Web平台 — Next.js + 用户系统 + 多地区支持 | 🔜 待执行 |

---

## 一、全网调研成果总览（50+ 优秀案例深度学习）

### 1.1 岗位采集 & 自动投递类（13个项目）

**中国求职平台专用：**

- [JobClaw](https://github.com/slothsheepking/jobclaw) (Python, 49 stars) — Boss直聘/LinkedIn 自动抓取+LLM匹配+批量投递，防封机制(随机延迟3-8s/日限100次/僵尸岗过滤)，支持Claude OAuth免费方案
- [GeekGeekRun 牛人快跑](https://github.com/nicedayzhu/geekgeekrun) — Boss直聘专用，可视化界面+LLM集成+已读不回提醒
- [Get Jobs](https://github.com/loks666/get_jobs) (Java) — 多平台(Boss/猎聘/拉勾/51job/智联)，定时投递+企业微信推送
- [AI工作猎手 ai-job](https://github.com/yangfeng20/ai-job) (Java+Vue) — AI坐席自动回复HR+智能挽留+邮件通知+Spring Boot 3
- [boss_batch_push](https://github.com/yangfeng20/boss_batch_push) (JS, 790 stars) — Boss批量投递+词云分析，油猴脚本
- [海投助手 Jobs_helper](https://github.com/YangShengzhou03/Jobs_helper) (JS, 220 stars) — AI智能回复+可视化面板+防重复

**国际求职平台专用：**

- [AIHawk Jobs_Applier_AI_Agent](https://github.com/feder-cr/Jobs_Applier_AI_Agent) (Python, **29.5k stars** — 全网最火) — LinkedIn自动投递，50+岗位/小时，TechCrunch/Wired报道
- [ApplyPilot](https://github.com/Pickle-Pixel/ApplyPilot) — **6阶段全自动管线**: Discover(5平台+48个Workday) -> Enrich -> Score -> Tailor -> CoverLetter -> Apply，2天投递1000个岗位
- [JobSentinel](https://github.com/cboyd0319/JobSentinel) (Rust+TS) — 监控13平台+智能评分(技能40%+薪资25%+地点20%+公司10%+新鲜度5%)+鬼工作检测

**混合/聚合平台：**

- [JobSpy/python-jobspy](https://github.com/speedyapply/JobSpy) (Python, **3.1k stars**) — LinkedIn/Indeed/Glassdoor/Google Jobs/ZipRecruiter 聚合爬虫库，23万+月下载（不支持Boss直聘）
- [apply-potato](https://github.com/coolbrother/apply-potato) — GitHub招聘仓库监控+GPT提取+Gmail状态追踪+Google Sheets+Discord通知，完全本地运行
- [Job Scout](https://github.com/8do-abehn/job-scout) — GitHub Actions定时爬取+GitHub Issues追踪应用状态（to-review/applied/interviewing/offer）+MCP Server
- [JoBoom](https://github.com/careerboomAI/JoBoom) (Next.js 16) — 跨LinkedIn/Indeed/Upwork聚合搜索+CV解析

**关键学习点：**

- ApplyPilot的6阶段管线是最完整的自动化流程设计
- AIHawk证明了自动投递的巨大需求(29.5k stars)
- JobSpy是最成熟的多平台爬虫库，但不支持中国平台，需要Playwright方案补充
- Job Scout的GitHub Actions + Issues方案是低成本的自动化追踪

### 1.2 MCP/Skill 求职服务类（7个项目）

- [ClawJob](https://clawjob.upcv.tech/) — OpenClaw 原生求职Skill，**6个Skill+20个MCP工具**：resume-create/edit、campus-search、job-search、job-monitor、auto-apply，兼容Cursor/Claude Code/Windsurf，简历实时同步到网页端
- [job-search-mcp](https://github.com/openclaw/skills/blob/main/skills/amoghpurohit/job-search-mcp/SKILL.md) — OpenClaw Skill，集成JobSpy的`scrape_jobs_tool`搜索8平台（LinkedIn/Indeed/Glassdoor/Google/ZipRecruiter/Bayt/Naukri/BDJobs）
- [JobGPT MCP](https://github.com/6figr-com/jobgpt-mcp-server) — **34个工具**覆盖求职全流程：搜索+自动投递+简历定制+应用追踪+招聘外联，支持Claude/Cursor/Windsurf/Continue
- [Placed MCP](https://github.com/exidian-tech/placed-mcp) — **47个工具**：37简历模板(测试50+ATS系统)+模拟面试(技术/系统设计/行为)+LinkedIn优化+薪资谈判
- [interview-mcp-server](https://github.com/HelloGGX/interview-mcp-server) — 简历PDF解析+AI生成面试题+实时对话录音+自动评估报告(多维度)
- [resume-tailoring-skill](https://github.com/varunr89/resume-tailoring-skill) (192 stars) — Claude Code Skill，公司文化调研+对话式经历发现+信心评分匹配+批量处理3-5个相似岗位
- [interview-coach-skill](https://github.com/noamseg/interview-coach-skill) (**833 stars**) — **23个命令**覆盖求职全生命周期：5维度评分(Substance/Structure/Relevance/Credibility/Differentiation)+故事银行(STAR)+8阶段训练+多格式面试转录分析(Otter/Zoom/Grain/Teams)+评分漂移校准

**关键学习点：**

- ClawJob的6 Skill + 20 MCP工具的设计模式是OpenClaw Skill开发的标杆
- interview-coach-skill的5维度评分+故事银行+评分漂移校准非常专业
- resume-tailoring-skill的"对话式经历发现"很创新 — 通过提问发掘用户未写入简历的经历

### 1.3 简历生成类（12个项目）

**LaTeX管线类：**

- [cv-pipeline](https://github.com/jsoyer/cv-pipeline) (Python, 99通过测试) — **最成熟的YAML->AI->LaTeX->PDF管线**：67个脚本+14个CI/CD工作流+5种AI(Gemini/Claude/OpenAI/Mistral/Ollama)+ATS评分，曾用于投递Anthropic
- [LLM-Resume-Template](https://github.com/adongwanai/LLM-Resume-Template) (166 stars) — **专为LLM/Agent岗设计**的LaTeX模板，含头像/科研/实习/项目板块，支持Overleaf
- [billryan/resume](https://github.com/billryan/resume) (**10.9k stars**) — 经典中英文LaTeX简历模板，CJK支持+FontAwesome
- [Roger](https://github.com/marswangyang/Roger) — Python+LaTeX+Gemini，按JD自动定制简历和求职信
- [GitHired](https://github.com/Herc-Ch/GitHired) — 从GitHub仓库自动拉取信息+LangChain生成简历

**Resume as Code 理念：**

- [resume-as-code](https://github.com/xiaohanyu/resume-as-code) / [YAMLResume](https://yamlresume.dev/) — **"简历即代码"**: 维护单一YAML职业Timeline，3个AI Agent(Timeline Polishing/Resume Generation/Interview Preparation)按STAR法则润色，支持9种语言，GitHub Actions自动化构建
- [ResumeAgent](https://github.com/ApplyU-ai/ResumeAgent) (TypeScript) — 4大功能：Resume Transformer(4模板) + Resume Tailor(零编造) + **Resume Heatmap**(简历-JD对齐热力图) + Resume Parser

**Claude Code简历插件：**

- [ats-resume-agent](https://github.com/NullSpace-BitCradle/ats-resume-agent) — **零编造政策**：每项成就必须有来源证明，LaTeX PDF输出+ATS优化
- [claude-resume-kit](https://github.com/ARPeeketi/claude-resume-kit) — **8维度多视角评审**(5种读者人格：ATS Bot/HR/技术评审/...)+反编造控制(出处标记/动词纪律/更正日志)+分离Claude Code会话减少偏差
- [resume-tailor-plugin](https://github.com/olegvg/resume-tailor-plugin) — Gap Analysis表(匹配/缺口/差异化)+ATS评分+地区惯例适配(EN-US/RU-CIS)+反模式保护
- [JobPilot](https://github.com/waltershalon/jobpilot) — Claude API定制+爬取+ATS分析+LaTeX/DOCX输出+React前端实时预览+FastAPI后端

**AI防编造最佳实践（来自 claude-resume-kit）：**

- Provenance flags: published / under review / internal
- Verb discipline: 防止过度吹嘘
- Corrections log: 修正过的错误不会重新出现
- 每步使用独立Claude Code会话，防止上下文污染

**关键学习点：**

- cv-pipeline是工程化程度最高的(67脚本+14 CI/CD)，直接复用其管线设计
- resume-as-code的"简历即代码"理念最优雅 — 维护一份YAML，生成N份定制简历
- ResumeAgent的热力图功能非常直观 — 可视化简历与JD的匹配度
- claude-resume-kit的8维度评审+5种读者人格评分系统最专业
- 零编造政策对于实习简历可选，但对于有经验的求职者很重要

### 1.4 面试资料 & 模拟面试类（10个项目）

**面试题库/学习指南：**

- [LLM-Agent-Interview-Guide](https://github.com/Lau-Jonathan/LLM-Agent-Interview-Guide) — **300+题，9大模块，字节Top20高频题**，3-5天/模块学习路径
- [ai-interview-guide](https://github.com/guocong-bincai/ai-interview-guide) — 245+题，18模块，**4级难度**(基础->应用->优化->架构)+90+代码示例
- [AgentGuide](https://github.com/adongwanai/AgentGuide) (**2928 stars**) — 对标JavaGuide，**1000+题库**，8-10周学习路径，双线(算法岗+开发岗)+简历级项目+6步求职方法论
- [ai-agents-from-zero](https://github.com/didilili/ai-agents-from-zero) — 从零到企业级(LangChain/LangGraph/RAG/MCP/多模态/微调)+可运行源码+提示词模板
- [Agent-100-Days](https://github.com/flingjie/Agent-100-Days) — 15周系统学习：Week1-2 LLM原理 -> Week3-7 Prompt/RAG/记忆 -> Week8-11 Agent模式 -> Week12-15 综合项目
- 你自己的 [ai-agent-interview-guide](https://github.com/bcefghj/ai-agent-interview-guide) (104 stars) — 200+面试题+企业级项目+简历模板+STAR面试稿+哆啦A梦漫画

**AI模拟面试系统：**

- [The-Interview-Mentor](https://github.com/ps06756/The-Interview-Mentor) — **40个面试官Agent**覆盖系统设计(URL缩短器/搜索引擎/Uber)/编程(数组/链表/DP)/ML/DevOps/行为面试，不接受模糊回答会追问细节，自适应难度
- [Friday](https://github.com/mostofashakib/Friday) — **LangGraph多Agent语音面试**：Interviewer(Opus生成题目) + Grader(Sonnet评分1-5) + Follow-up(RAG检测知识弱点) + Coach(Haiku实时指导)，Next.js 15前端+ElevenLabs TTS
- [interview-coach-skill](https://github.com/noamseg/interview-coach-skill) (833 stars) — 23命令全生命周期：5维度评分+故事银行+**8阶段训练进阶**+4-6题模拟面试(行为/系统设计/Case/Panel)+多格式转录分析
- [AI-Interviewer](https://github.com/sujalthapa369/AI-Interviewer) — React+Flask，NLP驱动题目生成+答案评估+性能分析仪表盘

**牛客/小红书真实面经（字节/阿里/腾讯 2026）：**

- 项目拷打：Agent编排/混合记忆架构/RAG存储/Token优化
- 技术深度：LangGraph/多模态/LoRA微调/MCP vs Function Calling
- 基础技术：HashMap/MySQL事务/Redis/Kafka/算法题
- 高频考点：GRPO原理/Self-Attention/KV Cache/手写Attention/RAG全流程/Agent记忆系统

**关键学习点：**

- AgentGuide(2928 stars)的6步求职方法论 + 双线(算法岗/开发岗)路径设计最系统
- The-Interview-Mentor的"不接受模糊回答"设计理念值得借鉴 — 真正的面试官会追问
- Friday的4-Agent语音面试架构是技术标杆(Interviewer/Grader/Follow-up/Coach)
- interview-coach-skill的评分漂移校准很巧妙 — 3次真实面试后自动校准AI评分

### 1.5 多Agent求职编排系统（5个项目）

- [Career-Ops](https://dev.to/santifer/i-built-a-multi-agent-job-search-system-with-claude-code-631-evaluations-12-modes-2cd0) — **12个Claude Code Skill模式**(auto-pipeline/oferta/batch/pdf/scan/apply等)，**10维评分**(角色匹配+技能对齐为门槛)，631次评估中74%低于4.0被过滤，批量122+ URL并行+容错
- [Job-Hunter](https://github.com/ryan-griego/job-hunter) (Nuxt4+Python) — 10个专用Agent+MongoDB+SSE实时监控
- [Job Agent Toolkit](https://github.com/Acidlambunk/Job-Agent) — MCP工具+LangGraph编排+FastAPI
- [Matt Sayar的4-Agent架构](https://mattsayar.com/orchestrating-ai-agents-for-job-searching/) — find-leads + customize-resume + find-decision-makers + generate-loom-script，**Google Sheet为中央协调枢纽**
- [Claude-Job-Search-Strategist](https://github.com/danielrosehill/Claude-Job-Search-Strategist) — 结构化工作区模板：user-context/ + inputs/ + outputs/ + agents/ + processes.json，斜杠命令约定(/agent, /queue, /resume-tailor, /cover-letter)

**关键学习点：**

- Career-Ops的"10维评分+门槛机制"最科学 — 角色匹配和技能对齐不达标直接过滤
- Matt Sayar的Google Sheet中央协调很实用 — 多Agent通过共享表格协作
- Claude-Job-Search-Strategist的目录结构设计很清晰 — 输入/输出/Agent分离

### 1.6 求职追踪 & 仪表盘类（4个项目）

- [JobSync](https://github.com/Gsync/jobsync) (Next.js, **468 stars**) — 自托管求职追踪+AI简历评审+匹配+分析，Docker部署
- [JobTrackerPro](https://github.com/thughari/JobTrackerPro) (Java/Angular) — 企业级，Gemini 2.0 Flash自动解析邮件+零操作追踪
- [ai-job-tracker](https://github.com/lbwalton/ai-job-tracker) — OpenAI分析+Gmail集成+Google Sheets+CSV导出
- [Resume-Matcher](https://github.com/srbhr/Resume-Matcher) (**26.5k stars**) — 简历关键词匹配+改进建议，多语言

### 1.7 小红书/牛客爬虫工具（4个项目）

- [xiaohongshu-skill](https://github.com/DeliciousBuding/xiaohongshu-skill) — Playwright+兼容Claude Code/OpenClaw，搜索/帖子/评论+反爬保护
- [redbook-cli](https://github.com/Youhai020616/xiaohongshu) — AI驱动小红书自动化，搜索/发布/互动/分析，MCP+CDP双引擎
- [LittleCrawler](https://github.com/pbeenigg/LittleCrawler) (684 stars) — 小红书/知乎/闲鱼异步爬虫，多存储(JSON/SQLite/MySQL/MongoDB)
- 牛客网官方API: https://docs.nowcoder.com/ — OAuth2.0认证，可获取招聘日程

### 1.8 行业痛点分析（来自2026年市场调研）

**求职者核心痛点：**

- 简历适配效率低：手动改写2小时+/岗位，关键词对齐困难
- 信息碎片化：岗位散落在Boss/猎聘/牛客/小红书，无法统一管理
- 面试准备无方向：不知道该学什么，八股文海量但缺乏针对性
- 公司信息不透明：薪资/加班/文化等信息需多平台对比

**现有工具不足：**

- 投递类工具多但简历定制弱（大多只有投递，没有简历生成）
- 面试准备类工具和投递类工具完全割裂
- 中国求职平台(Boss/牛客)的MCP/Skill支持几乎为零
- 没有"岗位采集->简历定制->面试准备->投递"的完整闭环工具

---

## 二、你的竞争优势分析

根据GitHub（62 followers, 250+ stars 的 claude-code 指南, 104 stars 的 ai-agent-interview-guide），你在AI Agent领域的积累：

- **claude-code-complete-guide** (250 stars) — 深度理解AI Agent架构
- **ai-agent-interview-guide** (104 stars) — 已有200+面试题+企业级项目+简历模板
- **learn-minimind** (66 stars) — LLM训练全流程理解
- **miniClaudeCode** (40 stars) — Agent架构最小复现
- **ClaudeCode-Source-Analysis** (33 stars) — 源码分析能力

**独特价值**：你是少数同时具备"AI Agent深度理解"和"求职内容创作能力"的开发者。武汉光谷2026新政按GitHub星标认定人才，你的GitHub profile本身就是竞争力。

---

## 三、系统架构设计

### 3.1 总体架构（5层）

```
输入层: 个人YAML数据 + 岗位URL/关键词 + 偏好配置
  ↓
数据采集层: Boss直聘(Playwright) + 牛客网API + JobSpy(国际) + 小红书面经 + Firecrawl
  ↓
核心引擎层(MiniMax M2.7):
  ├── JD分析器 (技能提取+关键词)
  ├── 10维评分器 (门槛+加权)
  ├── 公司画像 (薪资/评价/加班)
  ├── 简历引擎 (YAML->AI定制->LaTeX->PDF)
  ├── 面试引擎 (八股+面经+学习路径)
  └── 故事银行 (STAR法则经历库)
  ↓
输出层: LaTeX PDF简历 + 面试准备包 + 公司报告 + 投递指南 + 学习计划
  ↓
部署层: CLI工具 + OpenClaw Skill(SKILL.md) + MCP Server(6个工具) + 定时任务 + Web应用
```

### 3.2 5个专用Agent职责

- **ScoutAgent**: 多平台岗位采集 + 去重 + 新岗位监控
- **AnalystAgent**: JD解析 + 10维评分(借鉴Career-Ops) + 公司画像
- **TailorAgent**: YAML经历匹配 + STAR润色 + LaTeX生成 + ATS优化
- **CoachAgent**: 技能差距分析 + 学习路径 + 八股文 + 模拟面试题
- **TrackerAgent**: 投递状态追踪 + 进度汇报 + 新岗位提醒

### 3.3 10维岗位评分系统（借鉴Career-Ops）

| 维度 | 说明 | 类型 |
|------|------|------|
| 角色匹配度 | 岗位方向是否匹配AI/Agent | 门槛 |
| 技能对齐度 | 必需技能的覆盖率 | 门槛 |
| 薪资竞争力 | 日薪/月薪对比市场水平 | 加权 |
| 地理便利性 | 是否在武汉/可远程 | 加权 |
| 公司发展阶段 | 大厂/独角兽/创业公司 | 加权 |
| 团队技术实力 | 技术栈先进度 | 加权 |
| 成长潜力 | 转正可能/晋升空间 | 加权 |
| 面试难度 | 预估通过率 | 加权 |
| 时间匹配 | 实习时间/开始日期 | 加权 |
| 综合加班评价 | 工作生活平衡 | 加权 |

---

## 四、技术选型

| 模块 | 技术 | 说明 |
|------|------|------|
| LLM | MiniMax M2.7 | `base_url="https://api.minimaxi.com/v1"` + OpenAI SDK兼容 |
| 语言 | Python 3.11+ | 主语言 |
| 简历管线 | YAML + Jinja2 + XeLaTeX | `brew install basictex && tlmgr install ctex fontspec xecjk` |
| LaTeX模板 | LLM-Resume-Template + billryan/resume | AI岗专用 + 通用中文 |
| 岗位采集 | Playwright + JobSpy + Firecrawl | Boss直聘/牛客/国际平台 |
| 面经采集 | xiaohongshu-skill + 牛客API | 小红书面经 + 牛客招聘 |
| 数据存储 | SQLite + JSON | 本地存储 |
| MCP框架 | Python MCP SDK | `pip install mcp` |
| Skill框架 | OpenClaw SKILL.md | trigger + tools + markdown body |
| 自动化 | APScheduler + GitHub Actions | 定时任务 + CI/CD |
| Web前端 | Next.js 15 + Tailwind + Shadcn UI | 后期网站 |
| 通知 | Discord Webhook / 企业微信 | 实时提醒 |

---

## 五、实施路线（7个阶段）

### Phase 1: 基础框架 + MiniMax接入 + 个人数据 ✅

**目标**: 搭建项目骨架，让LLM能用起来

- 初始化 `jobforge/` 项目结构
- MiniMax M2.7 API 接入（OpenAI SDK兼容）
- 创建 `data/profile.yaml`（Resume as Code 个人数据）
- 安装LaTeX环境

### Phase 2: 岗位采集引擎 ✅

**目标**: 采集武汉AI/Agent实习的所有岗位

- Boss直聘 Playwright 爬虫（防封机制）
- 牛客网校招/实习岗位 API 对接
- 猎聘/智联关键词搜索
- 公司信息聚合 → 公司画像
- 10维评分系统
- SQLite 结构化存储

### Phase 3: 简历生成引擎（LaTeX PDF） ✅

**目标**: 输入JD，输出定制简历PDF

- YAML -> Jinja2 -> LaTeX -> PDF 管线
- LLM-Resume-Template 集成
- MiniMax M2.7 驱动简历定制（JD关键词提取 + STAR润色 + ATS优化）
- 首跑：金山软件武汉AI实习 → 简历PDF ✅

### Phase 4: 面试资料生成引擎 ✅

**目标**: 输入JD，输出从零到面试的完整资料包

- JD → 技能树提取（必需/加分/基础）
- 学习路径（N周计划）
- 八股文速查手册
- 模拟面试题（不接受模糊回答风格）
- 首跑：金山软件岗位面试资料包 ✅

### Phase 5: 端到端Demo跑通 ✅

**目标**: 以武汉大厂AI实习为例，完整跑通全流程

- 目标：金山软件武汉AI Agent实习
- 管线：岗位采集 → 公司画像 → 10维评分 → 简历PDF → 面试资料包 → 打招呼语
- 批量模式：夜间APScheduler自动调度

### Phase 6: 封装为OpenClaw Skill + MCP ✅

**目标**: 让别人也能用

SKILL.md 封装（5个Skill命令）：
- `/jobforge-search` — 搜索岗位
- `/jobforge-analyze` — 分析岗位+评分
- `/jobforge-resume` — 生成定制简历
- `/jobforge-interview` — 生成面试资料
- `/jobforge-pipeline` — 端到端全流程

MCP Server（6个工具）：
- `jobforge_search` / `jobforge_analyze` / `jobforge_company`
- `jobforge_resume` / `jobforge_interview` / `jobforge_greeting`

CLI工具：`python cli.py run/search/batch/list-jobs`

### Phase 7: Web平台 🔜

**目标**: 部署网站，支持不同地区/岗位的用户

- Next.js 15 + Tailwind + Shadcn UI
- 用户系统：注册/登录/个人数据
- 多地区支持：不限于武汉
- 应用追踪仪表盘
- 部署：Vercel / 阿里云

---

## 六、核心借鉴清单（精选每个方向最优案例）

### 架构设计

| 项目 | 借鉴内容 |
|------|---------|
| Career-Ops | 12模式Skill架构 + 10维评分门槛机制 + 批量并行处理 |
| Matt Sayar | 4-Agent + Google Sheet中央协调 |
| Claude-Job-Search-Strategist | 输入/输出/Agent分离的目录结构 |
| ApplyPilot | 6阶段自动化管线(Discover->Enrich->Score->Tailor->CoverLetter->Apply) |

### 简历生成

| 项目 | 借鉴内容 |
|------|---------|
| cv-pipeline | YAML->AI->LaTeX->PDF管线(67脚本+ATS评分) |
| resume-as-code | "简历即代码"理念 + STAR法则Timeline Polishing |
| ResumeAgent | 简历-JD热力图可视化 |
| claude-resume-kit | 8维度5视角评审 + 反编造控制 |

### 面试准备

| 项目 | 借鉴内容 |
|------|---------|
| AgentGuide | 6步求职方法论 + 1000+题库 + 双线路径 |
| The-Interview-Mentor | 40个面试官Agent + 不接受模糊回答 |
| interview-coach-skill | 5维度评分 + 故事银行 + 8阶段训练 |
| Friday | LangGraph 4-Agent语音面试(Interviewer/Grader/Follow-up/Coach) |

### 岗位采集

| 项目 | 借鉴内容 |
|------|---------|
| JobClaw | Boss直聘Playwright + 防封机制(随机延迟+日限+僵尸过滤) |
| JobSpy | 多平台聚合爬虫(3.1k stars) |
| Job Scout | GitHub Actions定时 + Issues追踪 |

### OpenClaw/MCP

| 项目 | 借鉴内容 |
|------|---------|
| ClawJob | 6 Skill + 20 MCP工具的设计模式 |
| resume-tailoring-skill | 对话式经历发现 + 批量处理 |

---

## 七、MiniMax M2.7 额度与成本规划

- 每月 4500 次调用 / 5小时（每周10倍 = 45000次/50小时）
- `base_url="https://api.minimaxi.com/v1"` + OpenAI SDK
- 单个岗位全流程约 8-15 次调用（JD分析2次 + 简历生成3次 + 面试资料5次 + 评分2次）
- 每周可处理 **3000-5600 个岗位**，完全够用
- 低峰时段(夜间) 100TPS，适合批量处理
- 建议：每晚22:00-06:00运行批量任务，利用低峰高速

---

## 八、项目独特卖点（对比现有工具的差异化）

现有工具的共同问题是**功能割裂** — 投递工具不会做简历，简历工具不会做面试准备。CareerPilot 的核心差异化：

1. **完整闭环**：岗位采集 → 公司画像 → 简历定制 → 面试资料 → 投递指南，一条龙
2. **中国市场深度支持**：Boss直聘/牛客/猎聘/智联 + 小红书面经，而非只支持LinkedIn
3. **面试资料与岗位绑定**：不是通用八股文，而是"针对这个岗位的这些技能"的定向资料
4. **Resume as Code**：YAML维护一份数据，AI生成N份定制简历
5. **OpenClaw原生**：直接养在小龙虾里，持续更新
6. **MiniMax包月友好**：利用M2.7包月额度，成本极低（每周处理3000-5600个岗位）

---

## 九、武汉 AI/Agent 实习岗位清单（已收录）

| 公司 | 岗位 | 地点 | 薪资 | 类型 | 投递 |
|------|------|------|------|------|------|
| 金山软件 | 应用算法实习生（LLM/Agent/RAG方向） | 武汉/北京 | 实习补贴+免费公寓 | 暑期实习 | https://campus.wps.cn/ |
| 腾讯青云计划 | 大模型/智能体方向实习 | 武汉/深圳/北京 | 腾讯实习标准 | 暑期实习 | https://join.qq.com/ |
| 智赋未来(武汉) | AI人工智能研发工程师实习生 | 武汉武昌区 | 150-200元/天 | 日常实习 | 智联招聘 |
| 光谷集团 | AI应用工程师 | 武汉光谷 | 15-25K/月 | 社招 | 猎聘 |
| 猎聘-武汉AI公司 | AI Agent 开发工程师实习 | 武汉光谷 | 200-300元/天 | 日常实习 | https://www.liepin.com/ |
| 字节跳动Seed | 大模型研究实习生 | 北京/杭州 | 400-600元/天 | 暑期实习 | https://jobs.bytedance.com/ |
| 淘天集团 | AI Agent应用开发工程师-2026暑期实习 | 杭州 | 300-600元/天 | 暑期实习 | https://www.nowcoder.com/jobs/detail/436118 |
| 天猫技术 | AI Agent算法工程师（大模型方向） | 杭州 | 300-400元/天 | 暑期实习 | https://www.nowcoder.com/jobs/detail/435213 |
| 阿里云 | AI Agent 开发工程师 | 杭州 | 500-510元/天 | 暑期实习 | https://www.nowcoder.com/jobs/detail/434896 |
| 中交第二公路院 | 大模型算法工程师（LLM/RAG/Agent） | 武汉蔡甸区 | 30-45K/月 | 社招(全职) | 智联招聘 |

---

## 十、Demo 输出文件清单（金山软件实例）

已生成文件位于 `data/outputs/`：

| 文件 | 大小 | 内容 |
|------|------|------|
| `resume_金山软件_*_20260404.pdf` | 145KB | LaTeX编译的定制简历 |
| `resume_金山软件_*_20260404.tex` | 7KB | LaTeX源文件 |
| `interview_*_eight_part.md` | 23KB | 针对岗位技能的八股文速查 |
| `interview_*_mock_interview.md` | 17KB | 15题模拟面试（项目拷打+技术+算法+行为） |
| `interview_*_study_path.md` | 23KB | 4周从零到面试的学习计划 |
| `interview_*_skill_tree.json` | 1.5KB | 结构化技能要求（必需/加分/基础） |
