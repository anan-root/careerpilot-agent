# CareerPilot Agent 设计与开发 Trace

## 0. 从零开发逐步 Trace

这一节按“从 0 到 1 开发项目”的顺序写。目标不是只介绍最终功能，而是说明一个项目是怎么一步步搭起来的：每一步做什么、为什么做、用了什么技术、产生了什么文件，以及这一步在面试中能体现什么能力。

项目定位：

```text
CareerPilot Agent 是一个面向中文招聘市场的个人求职智能体。
用户上传简历并输入求职目标后，系统自动规划搜索、多平台采集岗位、统一字段、匹配简历、生成推荐解释、输出 JD 差距分析和面试准备包，并保存本地求职记忆。
```

项目边界：

- 这是个人项目 / 本地 MVP / GitHub 展示系统。
- 已实现核心 Agent 求职流程。
- 没有包装成生产级商业系统。
- 文档里提到的 RAG、NL2SQL、向量库、异步任务队列等，如果当前没有实现，会明确写成“后续扩展思路”。

---

### Step 0.1: 创建项目仓库

执行动作：

```powershell
mkdir career-pilot
cd career-pilot
git init
```

这一步做了什么：

- 创建项目目录。
- 初始化 Git 仓库。
- 后续可以用 Git 记录每个阶段的代码变化。

为什么第一步要做 Git：

- 项目会不断迭代，Git 可以保留开发历史。
- 出问题时可以通过 diff 定位是哪一步引入的改动。
- 求职项目放到 GitHub 时，提交历史也能体现工程习惯。

产生的文件或目录：

```text
.git/
```

面试可讲：

```text
我从项目初期就用 Git 管理版本，避免代码和文档改动没有记录。这个项目后续涉及 crawler、Agent、LLM、前端和文档，多阶段开发必须用版本控制。
```

---

### Step 0.2: 编写 `.gitignore`

创建文件：

```text
.gitignore
```

这一步做了什么：

- 忽略虚拟环境、缓存文件、数据库文件、本地配置和运行输出。
- 避免真实 API Key、简历、岗位数据库、报告文件被提交。

典型忽略内容：

```text
__pycache__/
.venv/
config.local.yaml
data/jobs.db
data/memory/
data/outputs/
*.log
```

为什么要做：

- `config.local.yaml` 可能保存 DeepSeek API Key。
- `data/` 里可能包含简历画像、投递记录、岗位反馈，属于隐私数据。
- 数据库和输出报告是运行产物，不属于源代码。

面试可讲：

```text
我把真实配置和运行数据排除在 Git 外，API Key 通过本地配置或环境变量读取，避免把隐私数据提交到 GitHub。
```

---

### Step 0.3: 明确项目目标

项目一开始不是做“招聘网站爬虫”，而是做“AI 求职 Agent”。

目标拆解：

- 用户可以输入自然语言求职目标。
- 系统把目标解析成结构化 SearchPlan。
- 系统从多个招聘平台采集岗位。
- 不同平台岗位字段要统一。
- 上传简历后，系统能解析简历画像。
- 岗位要根据简历进行排序和解释。
- DeepSeek 只放在高价值语义任务上，避免全量调用。
- 每次搜索要保存报告和本地记忆。

为什么先定目标：

- 如果只做爬虫，项目亮点会很弱。
- 如果直接让大模型回答，又容易变成套壳。
- 目标定成 Agent 后，可以体现“计划、工具、记忆、解释、报告”的完整链路。

对应文档：

```text
README.md
docs/PRODUCT_DESIGN.md
docs/PHASE1_AGENT_SCAFFOLD.md
```

面试可讲：

```text
这个项目的核心不是把岗位抓下来，而是帮助用户完成求职决策。系统先规划搜索，再采集岗位，再结合简历匹配，最后给出推荐理由和下一步行动。
```

---

### Step 0.4: 设计项目目录结构

创建目录：

```text
agents/
crawlers/
memory/
prompts/
docs/
data/
templates/
export/
mcp_server/
skill/
```

每个目录职责：

- `agents/`：Agent 编排、搜索策略、简历画像、推荐排序、报告、对话问答。
- `crawlers/`：招聘平台采集器。
- `memory/`：本地求职记忆。
- `prompts/`：大模型 Prompt。
- `docs/`：产品设计、开发记录、面试文档、trace。
- `data/`：本地岗位库、运行记录、报告输出。
- `templates/`：导出模板。
- `skill/`：给 Agent/Skill 系统使用的项目说明。

为什么这样分：

- 前端、Agent、采集、存储、Prompt 分离。
- 后续 CLI 和 Streamlit 可以复用同一套后端逻辑。
- Prompt 单独管理，方便调优。

当前关键文件：

```text
app.py
cli.py
db.py
job_filters.py
llm_client.py
platform_registry.py
pipeline.py
```

面试可讲：

```text
我没有把所有逻辑写在 app.py 里，而是按采集、Agent、匹配、记忆、Prompt、前端展示拆模块。这样后续无论接 CLI、Streamlit 还是 FastAPI，都能复用核心逻辑。
```

---

### Step 0.5: 先搭配置层

创建文件：

```text
config.yaml
config.local.yaml
llm_client.py
```

这一步做了什么：

- `config.yaml` 保存默认配置。
- `config.local.yaml` 保存本地私密配置。
- `llm_client.py` 统一读取配置并封装 DeepSeek 调用。

当前默认模型配置：

```yaml
llm:
  provider: deepseek
  model: deepseek-v4-flash
  base_url: https://api.deepseek.com
  api_key: ${DEEPSEEK_API_KEY}
```

为什么要先搭配置：

- 模型、数据库、平台开关都不应该写死在业务代码里。
- API Key 不能提交到 GitHub。
- 后续切换模型时，只改配置或 client 层，不改业务层。

`llm_client.py` 主要能力：

- 加载配置。
- 解析环境变量。
- 创建 OpenAI 兼容 client。
- 提供 `chat()`。
- 提供 `chat_json()`。
- 提供 `llm-status --test` 检查能力。

面试可讲：

```text
我把 DeepSeek 调用封装在 llm_client.py 里，业务代码只调用 chat 或 chat_json。这样模型供应商和业务逻辑解耦，后续切模型成本低。
```

---

### Step 0.6: 设计 SQLite 岗位库

创建文件：

```text
db.py
data/jobs.db
```

这一步做了什么：

- 用 SQLite 保存岗位数据。
- 设计 jobs 表。
- 提供插入、更新、查询岗位的函数。
- 对 `platform + job_id` 做唯一约束。

核心字段：

```text
platform
job_id
title
company
location
salary
job_type
description
requirements
url
posted_date
score
status
```

为什么用 SQLite：

- 这是本地 MVP，SQLite 不需要额外安装数据库服务。
- 简单、轻量、适合个人项目演示。
- 后续可以迁移到 PostgreSQL 或 MySQL。

为什么要唯一约束：

- 同一个岗位可能被多次采集。
- 如果不去重，数据库会越来越乱。
- 有唯一约束后，重复采集时可以更新已有记录。

面试可讲：

```text
项目当前用 SQLite 是为了降低本地运行门槛。岗位数据用 platform + job_id 做唯一键，重复采集时更新字段而不是重复插入。
```

后续扩展：

- 多用户版本迁移到 PostgreSQL。
- 增加用户表、简历表、投递表、反馈表。
- 使用 Alembic 管理数据库迁移。

---

### Step 0.7: 设计平台注册表

创建文件：

```text
platform_registry.py
```

这一步做了什么：

- 统一平台 code 和中文名称。
- 维护平台别名。
- 提供平台名称归一化函数。

为什么要做：

- 用户可能输入“Boss”“BOSS直聘”“boss”。
- 代码里需要统一成稳定的 platform code。
- 前端展示时又需要转换成中文名。

面试可讲：

```text
我把平台名称和别名放到 platform_registry.py 统一管理，避免不同模块各自写一套平台映射。
```

---

### Step 0.8: 先做旧式岗位采集能力

创建文件：

```text
crawlers/boss.py
crawlers/zhilian.py
crawlers/job51.py
crawlers/liepin.py
crawlers/nowcoder.py
crawlers/generic_platforms.py
crawlers/ids.py
```

这一步做了什么：

- 为不同招聘平台写采集适配器。
- 每个平台返回统一结构的岗位 dict。
- 对无法稳定实时采集的平台，准备 curated fallback。
- 使用 `stable_job_id()` 为缺少 ID 的岗位生成稳定 ID。

为什么要先做采集：

- Agent 后续所有推荐都依赖真实岗位数据。
- 如果没有岗位数据，大模型只能空谈。
- 多平台采集是项目从“聊天工具”变成“业务工具”的基础。

统一岗位结构：

```python
{
    "platform": "zhilian",
    "job_id": "...",
    "title": "...",
    "company": "...",
    "location": "上海",
    "salary": "15-25K",
    "experience": "1-3年",
    "degree": "本科",
    "welfare": "...",
    "url": "...",
    "requirements": "..."
}
```

面试可讲：

```text
我没有让模型直接编岗位，而是先从平台拿岗位数据，并统一成标准字段。后续筛选、排序、报告都基于这些真实字段。
```

---

### Step 0.9: 编写多平台聚合器

创建文件：

```text
crawlers/aggregator.py
```

核心函数：

```python
collect_all_jobs(...)
```

这一步做了什么：

- 接收关键词、城市、平台、页数、筛选条件。
- 根据平台分发到不同 crawler。
- 支持扩展关键词检索。
- 统计每个平台抓取数量。
- 平台内去重。
- 合并所有平台结果。
- 字段增强。
- 筛选。
- 最终去重。
- 保存到 SQLite。

为什么要做聚合器：

- 前端和 Agent 不应该关心每个平台怎么采集。
- 多平台采集需要统一入口。
- 后续平台增加时，只要在 aggregator 里注册即可。

当前 summary 记录：

```text
selected_platforms
search_keywords
search_platform_fetch_counts
search_raw_platform_counts
search_filtered_platform_counts
search_final_platform_counts
search_field_counts
search_raw_total
search_filtered_total
search_final_total
```

这些 summary 的作用：

- 解释为什么结果少。
- 解释哪个平台贡献最多。
- 解释字段缺失情况。
- 生成搜索报告。

面试可讲：

```text
aggregator 是采集层的统一入口。它不仅负责调用各平台 crawler，还负责去重、筛选、字段完整度统计和结果落库。
```

---

### Step 0.10: 设计岗位字段清洗和筛选

创建文件：

```text
job_filters.py
```

这一步做了什么：

- 统一岗位类型。
- 解析薪资范围。
- 解析经验要求。
- 解析学历等级。
- 推断双休信息。
- 根据条件过滤岗位。

核心函数：

```python
normalize_job_type()
parse_salary_monthly_k()
parse_experience_years()
parse_degree_level()
infer_weekend_policy()
enrich_job_fields()
filter_jobs()
```

为什么要单独做：

- 采集器拿到的是平台原始文本。
- 推荐排序需要可比较的结构化字段。
- 字段清洗应该和采集逻辑解耦。

关键设计：

- 缺失字段不直接当负面事实。
- 薪资解析失败时保留原始文本。
- “未知”字段会进入风险提示，而不是编造。

面试可讲：

```text
岗位字段缺失是招聘平台常见问题。我没有把未知字段直接过滤掉，而是保留岗位并在风险点里提示字段缺失，避免误删候选。
```

---

### Step 0.11: 先做普通 Streamlit 页面

创建文件：

```text
app.py
```

这一步做了什么：

- 搭建 Streamlit 本地工作台。
- 支持岗位搜索。
- 支持展示岗位表格。
- 支持筛选平台、城市、岗位类型和页数。
- 支持从 SQLite 读取岗位。

为什么先用 Streamlit：

- 快速验证项目闭环。
- 不需要额外写前后端接口。
- 适合个人项目演示。

早期页面目标：

```text
用户输入关键词 -> 选择平台 -> 执行采集 -> 展示岗位表格
```

面试可讲：

```text
MVP 阶段我选择 Streamlit，是为了先验证 AI 求职流程，而不是把大量时间花在前端工程上。后续如果生产化，可以拆 FastAPI + Vue/React。
```

---

### Step 0.12: 增加 CLI 命令

创建文件：

```text
cli.py
```

这一步做了什么：

- 提供命令行入口。
- 支持普通 crawl。
- 支持简历匹配。
- 支持 Agent 搜索。
- 支持查看最近 Agent run。
- 支持 LLM 连通性测试。

典型命令：

```powershell
python cli.py crawl -k "AI Agent" -l "上海"
python cli.py agent-search "帮我找上海 AI Agent 岗位"
python cli.py match-resume .\resume.pdf --ai-top 3
python cli.py llm-status --test
```

为什么要 CLI：

- 不启动前端也能验证后端逻辑。
- 方便调试 crawler、LLM 和匹配模块。
- 说明业务能力不是写死在 UI 里。

面试可讲：

```text
我保留了 CLI 入口，方便测试 Agent 搜索、简历匹配和模型连通性，也说明核心能力和 Streamlit 前端是解耦的。
```

---

## 1. Agent 化改造 Trace

前面步骤已经能完成“搜索岗位”。但这还只是工具，不是 Agent。接下来开始把项目从“表单搜索工具”升级成“目标驱动 Agent”。

---

### Step 1.1: 设计 SearchPlan

创建文件：

```text
agents/search_strategy_agent.py
```

核心函数：

```python
build_search_plan(goal_text, resume_profile=None)
```

这一步做了什么：

- 把自然语言目标解析成结构化 SearchPlan。
- 默认城市上海。
- 默认平台 BOSS、智联、前程无忧。
- 默认岗位类型社招。
- 识别城市、关键词、薪资、经验、学历、双休、排除词。
- 识别是否允许 Boss 登录浏览器。

SearchPlan 示例：

```json
{
  "keyword": "AI Agent",
  "expanded_keywords": ["AI Agent", "智能体", "大模型应用", "RAG", "LLM"],
  "location": "上海",
  "platforms": ["boss", "zhilian", "51job"],
  "job_types": ["社招"],
  "criteria": {
    "salary_preferred_max_k": 20,
    "experience_preferred_max_years": 1,
    "weekend_preferred": true,
    "weekend_only": false
  },
  "safety": {
    "use_browser_crawlers": false,
    "allow_browser_login": false
  }
}
```

为什么用规则解析：

- 城市、薪资、学历、平台是规则性强的信息。
- 规则更稳定、成本更低。
- 初级开发面试时更容易解释。

关键设计：

- `不要实习` 是硬条件。
- `只看双休` 是硬条件。
- `双休优先` 是软偏好。
- `20K 以内` 默认是偏好，不直接硬过滤。

面试可讲：

```text
SearchPlan 是 Agent 的第一步。它把用户一句话拆成后续 crawler 和 ranking 能执行的结构化条件。
```

后续扩展：

- 使用 LLM 解析复杂目标，但必须输出 JSON。
- 做规则优先 + LLM 补充。
- 为 SearchPlan 增加 schema 校验。

---

### Step 1.2: 设计 Career Orchestrator

创建文件：

```text
agents/career_orchestrator.py
```

核心函数：

```python
run_agent_search(goal_text, resume_text=None, allow_browser_login=None)
```

这一步做了什么：

- 创建 Agent run。
- 读取简历画像。
- 读取本地记忆。
- 调用 `build_search_plan()`。
- 调用 `collect_all_jobs()`。
- 上传简历时调用 `rank_jobs_for_resume()`。
- 调用 `rank_jobs_with_decisions()`。
- 生成 Agent message。
- 生成下一步行动。
- 生成 Markdown 报告。
- 保存运行记录。

整体链路：

```text
用户目标
-> run_agent_search
-> 读取简历画像
-> 读取求职记忆
-> build_search_plan
-> collect_all_jobs
-> rank_jobs_for_resume
-> rank_jobs_with_decisions
-> build_agent_search_report
-> 保存 run record
```

为什么要做 Orchestrator：

- `app.py` 不应该承载全部业务流程。
- CLI 和前端都可以复用同一个 Agent 入口。
- 后续要做 LangGraph，也可以把这些步骤拆成节点。

面试可讲：

```text
career_orchestrator.py 是项目的 Agent 主编排层，它把搜索计划、岗位采集、简历匹配、推荐排序、报告和记忆串成一个闭环。
```

---

### Step 1.3: 记录 Agent 运行步骤

涉及文件：

```text
memory/store.py
agents/career_orchestrator.py
```

这一步做了什么：

- 每次 Agent 搜索生成 `run_id`。
- 保存每个阶段的执行步骤。
- 成功时保存结果和报告路径。
- 失败时记录失败原因。

为什么要记录：

- Agent 链路长，需要可追踪。
- 出问题时能定位是搜索计划、采集、匹配还是报告失败。
- 面试展示时可以说明系统是可复盘的。

面试可讲：

```text
每次 Agent 搜索都有 run_id 和执行步骤，这样不是黑盒生成，而是可以看到计划、采集、精排和报告每一步做了什么。
```

---

## 2. 简历画像 Trace

### Step 2.1: 支持简历上传和文本提取

涉及文件：

```text
app.py
agents/resume_matcher.py
```

核心函数：

```python
extract_resume_text(file_path)
```

这一步做了什么：

- 支持上传 PDF、DOCX、TXT、MD、TEX。
- 根据文件后缀选择解析方式。
- 提取简历文本。
- 对文本做 normalize。

为什么要提取文本：

- LLM 不能直接稳定理解各种文件格式。
- 后续画像、匹配、差距分析都基于简历文本。

面试可讲：

```text
我先把简历统一转换成纯文本，再进入画像和匹配流程，这样后续模块不用关心原始文件格式。
```

---

### Step 2.2: 生成简历画像

涉及文件：

```text
agents/profile_agent.py
agents/resume_matcher.py
prompts/resume_profile.md
memory/store.py
```

这一步做了什么：

- 用 Prompt 要求 DeepSeek 输出 JSON。
- 提取姓名、目标岗位、教育经历、技能、项目、优势和风险。
- 对模型输出做 normalize。
- 模型失败时使用本地规则 fallback。
- 画像保存到本地 memory。

简历画像结构：

```json
{
  "name": "",
  "target_role": "",
  "education": [],
  "skills": [],
  "projects": [],
  "strengths": [],
  "risks": []
}
```

为什么要画像：

- 搜索策略可以参考目标岗位。
- 推荐排序可以参考技能和项目。
- 面试建议可以结合真实经历。

面试可讲：

```text
上传简历后，系统不是直接把全文丢给每个岗位，而是先抽取结构化画像。这样后续排序和建议更稳定，也能缓存复用。
```

---

### Step 2.3: 简历缓存

涉及文件：

```text
app.py
agents/resume_matcher.py
```

这一步做了什么：

- 根据文件名和简历文本生成 cache key。
- 同一份简历刷新页面后不重复解析。
- 岗位精排时使用简历 hash 参与 cache key。

为什么要缓存：

- 简历画像调用 LLM 有成本。
- 用户刷新页面不应该重复请求。
- 精排同一岗位时也不应该重复调用模型。

面试可讲：

```text
我用简历 hash 做缓存，同一份简历不会重复解析；精排时还会把简历 hash 和岗位 hash 拼成 key，避免重复调用 DeepSeek。
```

---

## 3. 推荐排序 Trace

### Step 3.1: 本地快速粗排

涉及文件：

```text
agents/resume_matcher.py
```

核心函数：

```python
rank_jobs_for_resume()
_score_job_against_resume()
```

这一步做了什么：

- 从简历文本中提取关键词和技术词。
- 从岗位标题、描述、要求、技能字段中提取关键词。
- 计算简历和岗位的关键词重合。
- 计算技能命中。
- 计算岗位标题方向匹配。
- 给所有候选岗位生成本地匹配分。

为什么先做本地粗排：

- 速度快。
- 覆盖全部岗位。
- 不依赖大模型。
- 页面能先展示结果。

面试可讲：

```text
我没有对每个岗位都调用 DeepSeek，而是先用本地规则给全部岗位粗排，保证页面能快速返回，也给后续精排缩小候选集。
```

---

### Step 3.2: DeepSeek Top N 精排

涉及文件：

```text
agents/resume_matcher.py
prompts/job_match.md
```

核心函数：

```python
deep_match_resume_to_job()
rank_jobs_for_resume(..., ai_top_n=3)
```

这一步做了什么：

- 本地分数排序后，取 Top N。
- 默认 N=3。
- 对 Top N 调用 DeepSeek。
- Prompt 要求输出合法 JSON。
- 输出推荐分、推荐等级、匹配证据、缺失能力、风险点、简历动作和面试重点。

`ai_match` 结构：

```json
{
  "score": 82,
  "level": "推荐",
  "matched_evidence": [],
  "missing_requirements": [],
  "risk_points": [],
  "resume_actions": [],
  "interview_focus": [],
  "reasoning": ""
}
```

为什么默认 Top 3：

- 如果 30 个岗位全量调用模型，要 30 次请求。
- Top 3 精排只需要 3 次。
- 理论调用量减少约 90%。
- 成本、速度和效果更平衡。

面试可讲：

```text
项目里的 rerank 是两阶段策略：本地规则先全量粗排，再让 DeepSeek 对 Top 3 做结构化精排。最终分数按本地 25%、AI 75% 融合。
```

---

### Step 3.3: 分数融合和推荐解释

涉及文件：

```text
agents/resume_matcher.py
agents/ranking_agent.py
```

当前融合公式：

```python
final_score = local_score * 0.25 + ai_score * 0.75
```

`ranking_agent.py` 继续综合：

- 技能命中。
- 项目关键词。
- 岗位方向。
- 薪资偏好。
- 经验要求。
- 学历要求。
- 双休信息。
- 字段完整度。
- 排除词。
- 历史反馈。
- DeepSeek 匹配结果。

输出字段：

```text
score
level
matched_reasons
missing_requirements
risks
resume_actions
interview_focus
ai_match_used
```

为什么不只给分数：

- 用户不只想知道排名，还想知道为什么推荐。
- 面试准备需要缺口和风险。
- 可解释性是 AI 应用的重要部分。

面试可讲：

```text
我没有只给一个分数，而是把推荐拆成匹配证据、缺失能力、风险点、简历动作和面试重点。这样推荐结果是可解释、可行动的。
```

---

### Step 3.4: Rerank 后续扩展思路

当前实现：

```text
本地规则粗排 + DeepSeek Top 3 精排
```

如果要扩展成更标准的检索排序链路，可以做：

```text
SQL/平台召回
-> BM25 关键词召回
-> embedding 向量召回
-> cross-encoder rerank
-> LLM Top 3 精排
```

可选 reranker：

- `bge-reranker-base`
- `bge-reranker-large`
- 其他中文 cross-encoder reranker

扩展后的好处：

- embedding 解决语义召回。
- BM25 保留关键词精确匹配。
- reranker 提升排序质量。
- LLM 只负责最终解释和高价值判断。

面试可讲：

```text
当前项目的 rerank 是 LLM rerank。后续如果做标准 RAG/检索系统，我会在 LLM 精排前增加 embedding 召回和 cross-encoder rerank，把 LLM 调用控制在更小候选集上。
```

---

## 4. Prompt 工程 Trace

### Step 4.1: Prompt 文件化

创建目录：

```text
prompts/
```

创建文件：

```text
prompts/resume_profile.md
prompts/job_match.md
prompts/job_gap_analysis.md
prompts/interview_pack.md
agents/prompt_loader.py
```

这一步做了什么：

- 简历画像 Prompt 单独管理。
- 岗位匹配 Prompt 单独管理。
- JD 差距分析 Prompt 单独管理。
- 面试准备包 Prompt 单独管理。
- `prompt_loader.py` 负责加载和渲染 Prompt。

为什么要这样做：

- Prompt 很长，不适合写死在 Python 代码里。
- 不同任务的输入和输出不同。
- Prompt 文件可以独立调优和版本管理。

面试可讲：

```text
我把核心 Prompt 拆成文件，而不是散落在业务代码里。每个 Prompt 都写清楚输入字段和输出格式，这样更像工程化 AI 应用。
```

---

### Step 4.2: 结构化 JSON 输出

涉及文件：

```text
prompts/resume_profile.md
prompts/job_match.md
llm_client.py
agents/resume_matcher.py
```

这一步做了什么：

- 简历画像要求 JSON。
- 岗位匹配要求 JSON。
- 代码里通过 `chat_json()` 解析。
- 解析失败时 fallback。

为什么要 JSON：

- 前端需要稳定展示字段。
- 推荐排序需要读取 `score` 和 `level`。
- 报告需要读取匹配证据和风险点。
- 纯自然语言输出不稳定。

面试可讲：

```text
DeepSeek 不是随便生成一段建议，而是输出结构化 ai_match。这样前端可以把它拆成推荐分、匹配证据、缺失能力和风险点展示。
```

---

## 5. 生成建议 Trace

### Step 5.1: 生成 JD 差距分析

涉及文件：

```text
agents/resume_matcher.py
prompts/job_gap_analysis.md
```

这一步做了什么：

- 用户选择一个岗位。
- 系统把简历原文和岗位 JSON 填入 Prompt。
- DeepSeek 输出 JD/简历差距分析。

输出结构：

```text
岗位核心要求
简历已覆盖内容
简历缺失内容
可补充项目表达
技术栈补强建议
投递风险提醒
```

为什么只对单岗位生成：

- 每个岗位都生成成本太高。
- 用户真正需要深挖的是少数目标岗位。
- 单岗位上下文更聚焦，质量更好。

---

### Step 5.2: 生成面试准备包

涉及文件：

```text
agents/resume_matcher.py
prompts/interview_pack.md
```

输出结构：

```text
岗位理解
简历追问预测
技术面试题
项目深挖问题
行为面问题
反问面试官建议
7 天准备清单
```

为什么要做：

- 求职不是只投简历，还要准备面试。
- 面试问题必须结合简历和目标岗位。
- 这个功能能把“岗位推荐”延伸到“行动建议”。

面试可讲：

```text
项目不只告诉用户投哪个岗位，还能针对目标岗位生成 JD 差距分析和面试准备包，形成从检索到准备的闭环。
```

---

### Step 5.3: 本地 fallback 建议

涉及文件：

```text
agents/resume_matcher.py
agents/advice_agent.py
```

这一步做了什么：

- DeepSeek 不可用时，生成本地规则建议。
- 根据简历关键词和岗位关键词的交集、差集生成建议。
- 给出简历优化动作和面试准备重点。

为什么要 fallback：

- LLM 可能超时、限流、返回非法 JSON。
- 用户不应该因为模型失败看到空白页面。
- 本地规则虽然不如 LLM 细，但能保证主流程可用。

面试可讲：

```text
我没有让项目完全依赖大模型。DeepSeek 失败时，系统会回退到本地规则评分和建议，保证核心流程不中断。
```

---

## 6. 本地记忆 Trace

### Step 6.1: 保存求职记忆

创建文件：

```text
memory/store.py
agents/memory_agent.py
```

保存内容：

```text
data/memory/profile.json
data/memory/search_history.jsonl
data/memory/job_feedback.jsonl
data/memory/applications.jsonl
data/memory/agent_runs/*.json
```

这一步做了什么：

- 保存简历画像。
- 保存搜索历史。
- 保存岗位反馈。
- 保存投递状态。
- 保存 Agent run。

为什么要记忆：

- 求职是连续过程，不是一次性搜索。
- 用户可能标记某些岗位不合适。
- 下一次搜索应该参考历史反馈。

面试可讲：

```text
我把用户画像、搜索历史、岗位反馈和投递状态保存成本地记忆。这样 Agent 下次搜索时可以参考过往偏好，而不是每次从零开始。
```

---

### Step 6.2: 记忆参与搜索和排序

涉及文件：

```text
agents/memory_agent.py
agents/search_strategy_agent.py
agents/ranking_agent.py
```

这一步做了什么：

- `memory_agent.py` 汇总负反馈词、不喜欢的公司、感兴趣公司。
- `search_strategy_agent.py` 将记忆中的负反馈词合并到排除词。
- `ranking_agent.py` 根据历史反馈调整岗位分数。

例子：

- 用户曾标记某公司“不合适”，后续该公司降权。
- 用户备注“外包不考虑”，后续包含外包的岗位进入风险提示。
- 用户对某公司感兴趣，后续同公司岗位略微加权。

面试可讲：

```text
记忆不是简单保存文件，而是参与下一次计划和排序。比如历史负反馈会进入排除词或风险提示。
```

后续扩展：

- Redis 保存短期会话。
- PostgreSQL 保存长期记忆。
- 向量库保存历史问答和岗位反馈摘要。
- 增加定时 heartbeat，每天自动检查新岗位。

---

## 7. 报告 Trace

### Step 7.1: 生成 Agent 搜索报告

创建文件：

```text
agents/report_agent.py
```

这一步做了什么：

- 每次 Agent 搜索后生成 Markdown 报告。
- 报告保存到本地。
- 前端支持下载。

报告包含：

- 搜索计划。
- 简历画像。
- 求职记忆。
- 平台质量。
- 字段完整度。
- 推荐分布。
- Top 岗位。
- 匹配证据。
- 风险点。
- 简历动作。
- 面试重点。
- 下一步行动。

为什么要报告：

- 用户可以复盘搜索。
- 面试时可以展示 Agent 的执行结果。
- 让系统产出可交付物，而不只是页面展示。

面试可讲：

```text
每次 Agent 搜索都会生成 Markdown 报告，记录搜索计划、平台质量、字段完整度、推荐分布和 Top 岗位，这样结果可以复盘和下载。
```

---

## 8. 对话问答 Trace

### Step 8.1: 基于搜索结果做本地问答

创建文件：

```text
agents/conversation_agent.py
```

这一步做了什么：

- 读取最近一次 Agent 搜索记录。
- 根据用户问题回答常见追问。
- 支持解释结果少、平台贡献、优先投递、双休缺失、下一步行动等。

为什么先做本地问答：

- 可控。
- 不容易幻觉。
- 能直接基于当前搜索 summary 和 jobs 回答。

支持问题：

```text
为什么结果这么少？
哪个平台贡献最多？
优先投哪个？
双休为什么获取不到？
下一步怎么做？
```

面试可讲：

```text
Agent 问答不是开放式闲聊，而是围绕当前搜索结果和报告做上下文问答，回答更可控。
```

后续扩展：

- 接入 LLM 做更自然的多轮回答。
- 回答中附带岗位引用。
- 将历史问答加入记忆。

---

## 9. 前端产品化 Trace

### Step 9.1: 从表格展示升级为工作台

涉及文件：

```text
app.py
```

这一步做了什么：

- 顶部展示 CareerPilot Agent。
- 侧边栏配置平台、岗位类型、页数和模型状态。
- 主区支持目标输入、简历上传、岗位结果、行动建议和报告。
- 支持表格视图和卡片视图。
- 卡片分页，默认每页 10 条。
- 开发者调试信息默认折叠。

为什么这样设计：

- 表格适合快速比较岗位。
- 卡片适合看推荐理由和行动建议。
- 普通用户不需要直接看 JSON。
- 分页避免页面过长和卡顿。

面试可讲：

```text
我把前端从简单表格升级成工作台。普通用户看到的是中文可读卡片，原始 JSON 只放在开发者调试区。
```

---

### Step 9.2: 使用 `st.session_state` 管理状态

涉及文件：

```text
app.py
```

保存状态：

```text
current_jobs
ranked_jobs
search_summary
resume_profile
agent_result
result_page_v1
agent_chat
```

为什么需要：

- Streamlit 每次交互都会重新执行脚本。
- 如果不用 session_state，搜索结果、简历画像和分页会丢。

面试可讲：

```text
Streamlit 是脚本式运行，所以我用 session_state 保存搜索结果、简历画像、分页页码和匹配结果，避免用户每次点击都丢状态。
```

---

## 10. BOSS 登录安全 Trace

### Step 10.1: 默认不打开登录浏览器

涉及文件：

```text
crawlers/boss_real.py
crawlers/boss_cookie.py
crawlers/boss_drission.py
crawlers/aggregator.py
```

这一步做了什么：

- BOSS 默认走非交互 fallback。
- 只有用户明确允许时才打开浏览器登录路径。
- 不绕过验证码、滑块或短信验证。

为什么要这样做：

- 避免一运行就弹浏览器。
- 避免触碰平台风控。
- 用户必须知道并授权交互式登录。

面试可讲：

```text
BOSS 登录浏览器默认关闭，只有用户显式授权才启用。项目不会绕过验证码或平台安全策略。
```

---

### Step 10.2: 复用浏览器会话

这一步做了什么：

- 同一轮多个关键词尽量复用同一个浏览器会话。
- 登录成功后在同一窗口搜索多个关键词。
- 减少重复开窗和重复登录。

为什么要做：

- 之前每个关键词可能重新打开页面，体验差。
- BOSS 登录态不稳定，复用会话能减少误判。

面试可讲：

```text
我优化了 BOSS 登录路径，同一轮多个关键词复用同一个浏览器会话，减少重复开窗和重复登录。
```

---

## 11. 文档与面试材料 Trace

### Step 11.1: 编写 README

创建文件：

```text
README.md
```

README 内容：

- 项目介绍。
- 当前能力。
- 快速开始。
- DeepSeek 配置。
- Streamlit 启动方式。
- CLI 使用方式。
- Agent 工作流。
- 数据输出位置。
- 主要模块说明。
- 安全策略。
- 常见问题。

为什么要写：

- GitHub 项目需要快速说明。
- 面试官可以直接看懂项目。
- README 是项目交付的一部分。

---

### Step 11.2: 编写产品设计文档

创建文件：

```text
docs/PRODUCT_DESIGN.md
```

内容：

- 产品定位。
- 与传统岗位工具的区别。
- 当前已落地功能。
- 核心用户流程。
- Agent 设计。
- 数据结构。
- 页面结构。
- 风险和边界。

为什么要写：

- 说明项目不是随便堆功能。
- 体现需求分析和产品化思考。

---

### Step 11.3: 编写面试文档

创建文件：

```text
docs/career_pilot_项目简历与面试题整理.md
```

内容：

- 简历项目写法。
- 30 秒 / 1 分钟 / 3 分钟介绍。
- 高频面试问答。
- 初级开发技术追问题库。
- Python、RAG、Agent、微调、机器学习、后端常见问题。

为什么要写：

- 方便面试前复盘。
- 统一项目口径。
- 避免把没做过的能力说成已实现。

---

## 12. 当前没有实现但可以扩展的能力

这一部分不是从零已经完成的步骤，而是后续路线。面试时要明确说“当前项目没有完整实现，但我了解扩展思路”。

---

### Step 12.1: 扩展标准 RAG

当前状态：

- CareerPilot 没有完整向量知识库。
- 当前更准确说法是“基于岗位检索和简历证据的生成”。

可扩展文件：

```text
rag/chunker.py
rag/embeddings.py
rag/vector_store.py
rag/retriever.py
rag/reranker.py
rag/evaluator.py
```

可扩展流程：

```text
历史岗位/面试题/公司信息
-> 文档解析
-> 分块
-> embedding
-> 向量库
-> SQL + BM25 + Dense 混合召回
-> rerank
-> evidence-grounded 生成
```

分块策略：

- 简历按项目、技能、教育经历分块。
- JD 按职责、要求、加分项分块。
- 面试题一题一块。
- 长文档按标题和段落分块，500-800 token，保留 overlap。

向量库选择：

- 小规模本地：FAISS 或 ChromaDB。
- 服务化：Milvus。
- PostgreSQL 技术栈：pgvector。

---

### Step 12.2: 扩展 NL2SQL

当前状态：

- CareerPilot 没有完整 NL2SQL。
- 当前查询主要是固定条件查询。

可扩展问题：

```text
上海 20K 以内的 AI Agent 岗位有哪些？
哪个平台贡献最多？
最近 7 天我投递了多少岗位？
哪些公司被我标记为不合适？
```

设计流程：

```text
用户问题
-> 提供 schema 和字段注释
-> LLM 生成 SELECT SQL
-> SQL 安全校验
-> 执行 SQL
-> 失败重试
-> 结果总结
```

安全要求：

- 只允许 SELECT。
- 表名白名单。
- 自动加 LIMIT。
- 禁止 UPDATE、DELETE、DROP。
- 记录生成 SQL 和执行结果。

---

### Step 12.3: 扩展 SQL + 向量双联动

方案一：

```text
SQL 先过滤城市、薪资、平台、岗位类型
-> 向量检索筛选后 JD
-> rerank
-> 生成解释
```

方案二：

```text
SQL 召回
BM25 召回
向量召回
-> 合并去重
-> rerank
-> 生成
```

适合 CareerPilot 的问题：

```text
哪些岗位虽然标题不叫 AI Agent，但 JD 很匹配我的简历？
哪些岗位最看重 RAG 和工具调用能力？
历史上哪些公司岗位和我最匹配？
```

---

### Step 12.4: 扩展异步和高并发

当前状态：

- 当前主要是同步流程。
- 适合本地 MVP。

后续设计：

```text
FastAPI 接口
Redis 保存任务状态
Celery/RQ 后台任务
前端轮询任务进度
```

可以异步化的步骤：

- 多平台采集。
- 详情页补全。
- DeepSeek 精排。
- 报告生成。

---

### Step 12.5: 扩展评测体系

当前已有质量信号：

- 平台抓取数量。
- 筛选后数量。
- 最终展示数量。
- 字段完整度。
- DeepSeek 精排成功数。
- 推荐等级分布。

后续评测：

- SearchPlan 准确率。
- 薪资解析准确率。
- Recall@K。
- Precision@K。
- MRR。
- nDCG。
- 生成忠实度。
- 幻觉率。
- 平均耗时。
- P95 延迟。
- 缓存命中率。

---

## 13. 项目主线总结

如果面试官让你从头讲这个项目，可以按这个顺序：

```text
1. 我先明确项目不是爬虫，而是 AI 求职 Agent。
2. 然后搭项目结构，把采集、Agent、Prompt、记忆、前端分开。
3. 先做 SQLite 岗位库和多平台 crawler。
4. 再做 aggregator，统一多平台采集、筛选、去重和质量统计。
5. 然后做 SearchPlan，把自然语言目标变成结构化搜索计划。
6. 再做 Orchestrator，把搜索计划、岗位采集、简历画像、匹配排序、报告串起来。
7. 简历上传后，先解析画像，再做本地粗排。
8. 为了控制成本，只让 DeepSeek 精排 Top 3。
9. 最后把结果做成中文卡片、Markdown 报告和本地记忆。
10. 当前没有完整 RAG、NL2SQL 和向量库，但我知道后续怎么扩展。
```

一句话总结：

```text
CareerPilot Agent 是一个从岗位检索走向求职决策的 AI 应用项目，重点不是抓取岗位，而是把目标解析、多平台采集、简历匹配、推荐解释、面试准备和本地记忆串成可复盘的 Agent 工作流。
```

