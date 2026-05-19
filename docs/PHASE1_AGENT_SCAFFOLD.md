# Phase 1：Agent 骨架开发清单

目标：先把 CareerPilot 从“表单搜索工具”升级成“目标驱动 Agent”。这一阶段不追求全功能，只追求用户输入一句话目标后，系统能规划搜索、执行采集、解释结果。

当前状态：已完成，并继续补上了简历画像、岗位决策、本地建议和求职记忆的第一版。

## 输入示例

```text
帮我找上海 AI Agent 社招，薪资 20K 以上，3 年以内，双休优先，不要实习不要校招。
```

## 预期输出

```json
{
  "plan": {
    "keyword": "AI Agent",
    "expanded_keywords": ["AI Agent", "大模型应用", "RAG", "LLM", "AI应用开发"],
    "location": "上海",
    "platforms": ["zhilian", "51job", "liepin", "nowcoder"],
    "job_types": ["社招"],
    "criteria": {
      "min_salary_k": 20,
      "max_experience_years": 3,
      "degrees": ["不限", "大专", "本科", "硕士", "博士"],
      "weekend_only": true
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

## 必做文件

- `agents/search_strategy_agent.py`
- `agents/career_orchestrator.py`
- `data/memory/.gitkeep`
- `app.py`

## 任务 1：Search Strategy Agent

新增：

```python
def build_search_plan(goal_text: str, resume_profile: dict | None = None) -> dict:
    ...
```

规则：

- 默认城市：上海。
- 默认岗位类型：社招。
- 默认平台：智联、51job、猎聘、牛客。
- 默认不启动浏览器。
- 默认不允许 Boss 登录。
- 识别“不要实习/不要校招”。
- 识别薪资下限，例如 20K 以上。
- 识别经验上限，例如 3 年以内。
- 识别双休优先。

## 任务 2：Career Orchestrator

新增：

```python
def run_agent_search(goal_text: str, resume_text: str | None = None) -> dict:
    ...
```

它负责：

- 调用 `build_search_plan()`。
- 调用 `collect_all_jobs()`。
- 读取 `get_last_search_summary()`。
- 生成一段中文 Agent 总结。
- 给出下一步建议。

## 任务 3：前端接入

在 Streamlit 中新增：

- “告诉 Agent 你的求职目标”输入框。
- “让 Agent 制定计划并检索”按钮。
- 展示搜索计划。
- 展示 Agent 总结。

## 验收标准

- 输入一句话目标可以完成搜索。
- 不打开浏览器。
- 结果摘要能解释平台数量、类型分布、字段完整度。
- 没上传简历时也能工作。
- 上传简历后后续可接 Phase 2。

## 已追加完成

- `agents/profile_agent.py`：生成并保存简历画像。
- `agents/ranking_agent.py`：给岗位添加推荐等级、推荐分、风险和建议。
- `agents/advice_agent.py`：无需 LLM 的本地行动建议。
- `agents/memory_agent.py`：汇总画像、反馈、投递状态，形成求职记忆上下文。
- `agents/report_agent.py`：为每次 Agent 搜索生成可下载 Markdown 报告。
- `agents/conversation_agent.py`：基于当前搜索结果回答“为什么少、先投哪个、双休为什么缺、下一步做什么”等问题。
- `memory/store.py`：保存和导出本地求职记忆。
- `memory/store.py`：新增 Agent 任务运行记录，保存 `run_id`、阶段步骤、推荐分布、Top 岗位摘要和报告路径。
- `cli.py agent-search`：命令行启动 Agent 搜索。
- `cli.py agent-runs`：查看最近 Agent 任务。
- `cli.py agent-ask`：基于最近一次或指定 `run_id` 的 Agent 任务提问。
- `app.py`：新增 Agent 执行步骤、最近任务、Agent 问答、岗位卡片视图和报告下载。

