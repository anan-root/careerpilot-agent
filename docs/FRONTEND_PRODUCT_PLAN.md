# CareerPilot Independent Frontend Plan

目标：在保留 Streamlit 工作台的同时，提供可运行的 Vite + Vue 独立前端，并让后续产品化界面复用稳定 API 契约。

当前代码入口：

- `frontend/package.json`
- `frontend/src/App.vue`
- `frontend/src/api.js`
- `frontend/src/styles.css`

## 页面结构

### 1. 岗位收件箱

用途：聚合平台采集、插件导入和手动 JD。

核心组件：

- 搜索条件栏：关键词、城市、平台、岗位类型。
- 导入栏：JD 文本、岗位链接、读取链接内容开关。
- 岗位列表：公司、岗位、薪资、地点、来源、字段质量、动作状态。
- 质量侧栏：无效候选、去重摘要、字段置信度。

API：

- `GET /meta/platforms`
- `POST /jobs/search`
- `GET /jobs`
- `POST /jobs/import`
- `GET /jobs/actions`

### 2. 简历匹配看板

用途：找到最匹配简历的岗位。

核心组件：

- 简历文本输入或文件解析结果。
- 匹配摘要：平均分、强匹配数量、平台分布、动作状态。
- Top 岗位表：推荐等级、分数、命中、缺口、风险。
- 缺口词面板：需要补强的技能或项目证据。

API：

- `POST /jobs/match`

### 3. 岗位详情

用途：围绕一个岗位做决策。

核心组件：

- JD 原文和标准字段。
- 匹配证据、缺口、风险、简历动作。
- 收藏、反馈、投递、沟通状态按钮。
- 来源链接和插件导入痕迹。

API：

- `POST /jobs/bookmark`
- `POST /jobs/feedback`
- `POST /jobs/application`

### 4. 求职行动记录

用途：复盘投递和反馈。

核心组件：

- 状态分布：收藏、感兴趣、已投递、已沟通、面试中、不合适。
- 公司维度记录。
- 下一步动作列表。

API：

- `GET /jobs/actions`

## 前端状态建议

- `capabilities`：启动时读取 `/meta/capabilities`。
- `platforms`：启动时读取 `/meta/platforms`。
- `jobs`：来自 `/jobs` 或 `/jobs/match`。
- `searchSummary`：来自 `/jobs/search.summary`。
- `matchSummary`：来自 `/jobs/match.summary`。
- `actions`：来自 `/jobs/actions`。
- `selectedJob`：当前详情岗位。

## 开发顺序

1. 已完成：能力发现和平台清单。
2. 已完成：多平台采集、手动 JD / 链接导入。
3. 已完成：简历匹配和匹配看板摘要。
4. 已完成：收藏、反馈和投递状态。
5. 后续：平台采集任务异步化、进度条和报告下载。

## 当前边界

- Streamlit 仍是当前可运行工作台。
- 独立前端优先复用本地 API，不直接读写 JSONL 或 SQLite。
- 浏览器插件只负责当前页读取和动作触发，不承担复杂匹配逻辑。
