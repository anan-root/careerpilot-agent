---
name: CareerPilot Agent
version: 0.3.0
description: 面向中文招聘市场的个人求职智能体，支持目标驱动岗位搜索、简历匹配、推荐解释、行动建议和本地求职记忆
author: anan-root
triggers:
  - CareerPilot
  - CareerPilot Agent
  - 职航 Agent
  - 找工作
  - 求职
  - 简历匹配
  - 面试准备
  - 岗位推荐
  - job search
  - resume
  - interview prep
tools:
  - careerpilot_agent_search
  - careerpilot_agent_runs
  - careerpilot_agent_ask
  - careerpilot_match_resume
  - careerpilot_advise_resume
---

# CareerPilot Agent

CareerPilot Agent 是一个面向中文招聘市场的个人求职智能体。用户上传简历并说出求职目标后，Agent 会规划搜索、采集岗位、解释结果、给出推荐决策、生成简历优化和面试建议，并把每次任务保存为可复盘的本地记忆。

默认场景：

- 城市：上海
- 岗位类型：社招/全职
- 平台：智联、51job、猎聘、牛客
- 大模型：DeepSeek，OpenAI SDK 兼容调用方式
- 安全策略：默认不自动打开浏览器，不自动打开 Boss 登录页，不绕过登录、验证码或滑块

## 功能

### `careerpilot_agent_search` — 目标驱动岗位搜索

输入一句话目标，让 Agent 自动生成 SearchPlan 并执行多平台搜索。

能力：

- 解析城市、关键词、薪资、经验、学历、岗位类型和排除词。
- 默认上海、社招、智联/51job/猎聘/牛客。
- 默认排除实习和校招，除非用户明确选择。
- 返回平台抓取量、筛选量、字段完整度和结果质量说明。
- 生成 Markdown 搜索报告和 `run_id`。

示例：

```text
帮我找上海 AI Agent 社招，薪资 20K 以上，3 年以内，双休优先，不要实习不要校招。
```

CLI：

```powershell
python cli.py agent-search "帮我找上海 AI Agent 社招，薪资 20K 以上，3 年以内，双休优先，不要实习不要校招。"
```

### `careerpilot_agent_runs` — 查看 Agent 任务

查看最近的 Agent 运行记录。

能力：

- 展示 `run_id`。
- 展示任务状态。
- 展示推荐分布。
- 展示 Top 岗位摘要和报告路径。

CLI：

```powershell
python cli.py agent-runs --limit 5
```

### `careerpilot_agent_ask` — 基于搜索结果追问

围绕最近一次或指定 `run_id` 的 Agent 搜索结果提问。

常见问题：

- 为什么结果这么少？
- 哪个平台贡献最多？
- 为什么平台选多了最终结果没变多？
- 双休、经验、公司地址为什么获取不到？
- 优先投哪个岗位？
- 下一步怎么做？

CLI：

```powershell
python cli.py agent-ask "为什么结果这么少"
python cli.py agent-ask "优先投哪个" --run-id 20260518_223632_d1a35c2a
```

### `careerpilot_match_resume` — 简历精准匹配岗位

根据上传简历对数据库中的岗位进行排序。

能力：

- 提取 PDF、DOCX、TXT 简历文本。
- 基于技能、项目、经验、学历和岗位字段打分。
- 可选对 Top N 岗位调用 DeepSeek 精评。
- DeepSeek 不可用时回退到本地规则建议。

CLI：

```powershell
python cli.py match-resume .\resume.pdf --ai-top 0
```

### `careerpilot_advise_resume` — 单岗位简历优化和面试建议

针对一个岗位生成行动建议。

能力：

- 简历优化方向。
- 关键词补强建议。
- 面试准备重点。
- 项目追问方向。
- 投递前检查清单。

CLI：

```powershell
python cli.py advise-resume .\resume.pdf --job-id <job_id>
```

## 配置

真实 API Key 不写入代码。推荐使用 `config.local.yaml` 或环境变量。

示例：

```yaml
llm:
  provider: deepseek
  model: deepseek-v4-flash
  base_url: https://api.deepseek.com
  api_key: ${DEEPSEEK_API_KEY}
```

PowerShell：

```powershell
$env:DEEPSEEK_API_KEY="你的 DeepSeek API Key"
```

检查连通性：

```powershell
python cli.py llm-status --test
```

## 数据位置

本地运行数据默认保存在：

```text
data/
  jobs.db
  memory/
    profile.json
    search_history.jsonl
    job_feedback.jsonl
    applications.jsonl
    agent_runs/*.json
  outputs/
    agent_search_report.md
    agent_runs/*.md
```

这些数据默认不提交 GitHub。

## 安全边界

- 不上传真实 API Key。
- 不上传真实简历、岗位数据库、运行记录或浏览器 Cookie。
- 默认不打开交互式浏览器。
- 默认不做自动投递。
- 默认不自动代聊 HR。
- 不绕过登录、验证码、滑块或平台安全策略。
- 平台没有公开的字段必须标记未知，不能编造。
