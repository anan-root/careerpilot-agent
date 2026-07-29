# Phase 1：Agent 骨架实现记录

目标：把 CareerPilot 从“表单搜索工具”升级成“目标驱动 Agent”。这一阶段已经完成，并在后续迭代中继续补上了简历画像、岗位决策、行动建议、求职记忆、运行报告、Agent 问答、自然语言求职任务和 BOSS 受控沟通。

## 1. 输入示例

```text
帮我找上海 AI Agent 岗位，我是去年毕业的，薪资 20K 以内，社招和校招都可以，双休优先，不要实习。
```

## 2. SearchPlan 输出示例

```json
{
  "plan": {
    "keyword": "AI Agent",
    "expanded_keywords": ["AI Agent", "智能体", "大模型应用", "RAG", "LLM", "AI应用开发"],
    "location": "上海",
    "platforms": ["boss", "zhilian", "51job"],
    "job_types": ["社招", "校招"],
  "criteria": {
    "salary_preferred_max_k": 20,
    "experience_preferred_max_years": 1,
      "degrees": ["不限", "大专", "本科", "硕士", "博士"],
      "weekend_preferred": true,
      "weekend_only": false
    },
    "safety": {
      "use_browser_crawlers": false,
      "allow_browser_login": false
    }
  },
  "jobs": [],
  "summary": {},
  "agent_message": "",
  "next_actions": []
}
```

## 3. Phase 1 已完成文件

- `agents/search_strategy_agent.py`
- `agents/career_orchestrator.py`
- `app.py`

说明：`data/` 目录只保留 `data/.gitkeep`，真实运行产生的 `data/memory/`、`data/outputs/`、`data/jobs.db` 均被 `.gitignore` 忽略，不提交 GitHub。

## 4. Search Strategy Agent

核心函数：

```python
def build_search_plan(goal_text: str, resume_profile: dict | None = None) -> dict:
    ...
```

已实现规则：

- 默认城市：上海。
- 默认岗位类型：社招。
- 默认平台：BOSS直聘、智联招聘、前程无忧。
- 默认不启动浏览器。
- 默认不允许 Boss 登录；目标里明确写“允许 Boss 登录浏览器”时再启用。
- 识别“不要实习/不要校招/不要外包”。
- 识别薪资上限或下限，例如 20K 以内、20K 以上。
- 识别经验上限，例如 3 年以内。
- 从“去年毕业”等描述推断经验偏好，但只用于排序提示，不在展示前硬过滤。
- 识别学历要求。
- 识别双休偏好；“双休优先”只做排序提示，“只看双休”才进入硬筛选。
- 生成数据风险说明。

## 5. Career Orchestrator

核心函数：

```python
def run_agent_search(goal_text: str, resume_text: str | None = None) -> dict:
    ...
```

它负责：

- 创建 Agent 任务并生成 `run_id`。
- 读取或生成简历画像。
- 读取本地求职记忆。
- 调用 `build_search_plan()`。
- 调用多平台采集。
- 调用岗位决策排序。
- 生成中文 Agent 总结。
- 生成 Markdown 报告。
- 保存运行记录。
- 出错时保存失败状态。

## 6. 前端接入

Streamlit 当前已拆成 4 个工作区：

- `任务配置`：简历上传、自然语言任务、快速 Agent 检索、手动搜索。
- `岗位结果`：搜索摘要、岗位统计、表格视图、卡片视图。
- `沟通行动`：目标岗位选择、匹配结论、岗位详情、BOSS 沟通草稿、简历优化和面试准备。
- `记录记忆`：Agent 解释、最近任务、Agent 问答、本地求职记忆导出。

这样处理后，搜索配置、结果查看、岗位行动和历史记录不会同时堆在一个页面里。

## 7. 验收结果

Phase 1 验收标准：

- 输入一句话目标可以完成搜索。
- 默认不打开浏览器。
- 默认按上海、社招、BOSS直聘/智联招聘/前程无忧执行。
- 结果摘要能解释平台数量、类型分布、字段完整度。
- 没上传简历时也能工作。
- 上传简历后可以进入精准匹配。

当前状态：已完成。

## 8. 后续追加完成

- `agents/profile_agent.py`：生成并保存简历画像。
- `agents/ranking_agent.py`：给岗位添加推荐等级、推荐分、风险和建议。
- `agents/advice_agent.py`：无需 LLM 的本地行动建议。
- `agents/outreach_agent.py`：根据岗位、简历画像、匹配结论和用户边界生成 BOSS 打招呼/回复草稿。
- `agents/memory_agent.py`：汇总画像、反馈、投递状态，形成求职记忆上下文。
- `agents/report_agent.py`：为每次 Agent 搜索生成可下载 Markdown 报告。
- `agents/conversation_agent.py`：基于当前搜索结果回答常见追问。
- `agents/search_strategy_agent.py`：新增自然语言求职任务解析，把职位、城市、薪资、学历、活跃 HR、匹配阈值和沟通边界解析为任务配置。
- `crawlers/boss_outreach.py`：复用 BOSS 登录浏览器配置，支持单岗位干跑检查和确认发送。
- `memory/store.py`：保存本地求职记忆、自然语言任务配置、沟通记录和 Agent 任务运行记录。
- `cli.py agent-search`：命令行启动 Agent 搜索。
- `cli.py agent-runs`：查看最近 Agent 任务。
- `cli.py agent-ask`：基于最近一次或指定 `run_id` 的 Agent 任务提问。
- `cli.py llm-status --test`：检查 DeepSeek 默认配置和连通性。
- `app.py`：支持工作区式 UI、Agent 执行步骤、最近任务、Agent 问答、岗位卡片视图、报告下载、求职任务配置和 BOSS 沟通区。

## 9. BOSS 受控沟通边界

当前 BOSS 沟通不是自动投递系统，只是岗位行动区里的受控执行层：

- 先生成打招呼或回复草稿。
- 用户可以编辑草稿。
- 有沟通链接时可以做干跑检查。
- 只有用户确认后才发送。
- 每次只处理一个岗位。
- 不自动上传简历，不批量发送，不自动代聊。
- 页面需要人工处理时，记录状态并交给用户继续处理。

## 10. 当前模型策略

当前默认 LLM：

- provider：`deepseek`
- model：`deepseek-v4-flash`
- base_url：`https://api.deepseek.com`

真实 API Key 只放在本地 `config.local.yaml` 或环境变量中。DeepSeek 调用失败时，简历建议和岗位建议会回退到本地规则逻辑，保证核心流程不中断。
