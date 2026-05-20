# Phase 1：Agent 骨架实现记录

目标：把 CareerPilot 从“表单搜索工具”升级成“目标驱动 Agent”。这一阶段已经完成，并在后续迭代中继续补上了简历画像、岗位决策、行动建议、求职记忆、运行报告和 Agent 问答。

## 1. 输入示例

```text
帮我找上海 AI Agent 社招，薪资 20K 以上，3 年以内，双休优先，不要实习不要校招。
```

## 2. SearchPlan 输出示例

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
- 默认平台：智联、51job、猎聘、牛客。
- 默认不启动浏览器。
- 默认不允许 Boss 登录。
- 识别“不要实习/不要校招/不要外包”。
- 识别薪资下限，例如 20K 以上。
- 识别经验上限，例如 3 年以内。
- 识别学历要求。
- 识别双休优先。
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

Streamlit 已新增：

- “告诉 Agent 你的求职目标”输入框。
- “让 Agent 制定计划并检索”按钮。
- 搜索计划展示。
- Agent 总结展示。
- Agent 执行步骤。
- 最近 Agent 任务。
- Agent 问答。
- 岗位卡片视图。
- 报告下载。

## 7. 验收结果

Phase 1 验收标准：

- 输入一句话目标可以完成搜索。
- 默认不打开浏览器。
- 默认按上海、社招、智联/51job/猎聘/牛客执行。
- 结果摘要能解释平台数量、类型分布、字段完整度。
- 没上传简历时也能工作。
- 上传简历后可以进入精准匹配。

当前状态：已完成。

## 8. 后续追加完成

- `agents/profile_agent.py`：生成并保存简历画像。
- `agents/ranking_agent.py`：给岗位添加推荐等级、推荐分、风险和建议。
- `agents/advice_agent.py`：无需 LLM 的本地行动建议。
- `agents/memory_agent.py`：汇总画像、反馈、投递状态，形成求职记忆上下文。
- `agents/report_agent.py`：为每次 Agent 搜索生成可下载 Markdown 报告。
- `agents/conversation_agent.py`：基于当前搜索结果回答常见追问。
- `memory/store.py`：保存本地求职记忆和 Agent 任务运行记录。
- `cli.py agent-search`：命令行启动 Agent 搜索。
- `cli.py agent-runs`：查看最近 Agent 任务。
- `cli.py agent-ask`：基于最近一次或指定 `run_id` 的 Agent 任务提问。
- `cli.py llm-status --test`：检查 DeepSeek 默认配置和连通性。
- `app.py`：支持 Agent 执行步骤、最近任务、Agent 问答、岗位卡片视图和报告下载。

## 9. 当前模型策略

当前默认 LLM：

- provider：`deepseek`
- model：`deepseek-v4-flash`
- base_url：`https://api.deepseek.com`

真实 API Key 只放在本地 `config.local.yaml` 或环境变量中。DeepSeek 调用失败时，简历建议和岗位建议会回退到本地规则逻辑，保证核心流程不中断。
