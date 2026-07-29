# CareerPilot API Reference

本地 API 默认监听 `http://127.0.0.1:8000`，面向浏览器插件、脚本和后续独立前端。

## 启动

```powershell
python api.py
```

## 能力发现

### `GET /health`

返回服务状态。

```json
{"status": "ok", "service": "career-pilot-api"}
```

### `GET /meta/capabilities`

返回当前 API 支持的能力和端点清单。独立前端可以先请求该接口，判断后端是否支持岗位导入、匹配、收藏、反馈和投递记录。

### `GET /meta/platforms`

返回当前可选招聘平台和默认平台。独立前端可以用它渲染平台多选控件。

```json
{
  "default": ["boss", "zhilian", "51job"],
  "items": [
    {"code": "boss", "label": "BOSS直聘", "default": true},
    {"code": "zhilian", "label": "智联招聘", "default": true}
  ]
}
```

## 多平台采集

### `POST /jobs/search`

调用已有多平台聚合采集器，把岗位写入本地库，并返回本次采集结果和质量摘要。

```json
{
  "keyword": "RAG",
  "location": "上海",
  "platforms": ["boss", "zhilian", "51job"],
  "max_pages": 2,
  "job_types": ["社招", "校招"],
  "expand_keywords": true,
  "max_keywords": 4,
  "enrich_details": true,
  "detail_limit": 20,
  "use_browser_crawlers": false,
  "allow_browser_login": false
}
```

返回包含：

- `items`：本次采集后入库的岗位。
- `total`：本次返回数量。
- `summary`：平台数量、关键词数量、字段完整度、过滤和去重摘要。

## 岗位导入

### `POST /jobs/import`

导入外部岗位。可以只传结构化字段，也可以传 `jd_text`。当 `fetch_url=true` 且有 `url` 时，会尝试读取链接页面正文。

```json
{
  "title": "AI 应用开发工程师",
  "company": "示例科技",
  "location": "上海",
  "salary": "12-18K",
  "url": "https://example.com/job/1",
  "jd_text": "任职要求：熟悉 Python、RAG、FastAPI。",
  "fetch_url": false
}
```

返回：

```json
{
  "job": {
    "platform": "manual",
    "title": "AI 应用开发工程师",
    "company": "示例科技",
    "field_quality_score": 80.0
  }
}
```

### `GET /jobs`

读取本地岗位列表。

查询参数：

- `limit`：返回数量，默认 `50`，范围 `1-500`。

## 简历匹配

### `POST /jobs/match`

根据简历文本匹配本地岗位。默认只使用本地快速匹配；`ai_top_n > 0` 时会对 Top 岗位调用模型精排。

```json
{
  "resume_text": "我做过 Python、RAG、FastAPI 和 Agent 项目。",
  "top_n": 20,
  "ai_top_n": 0,
  "job_types": ["社招", "校招"]
}
```

返回包含：

- `items`：排序后的岗位。
- `summary`：匹配看板摘要，包括平均分、平台分布、动作状态、Top 岗位、主要命中和主要缺口。

## 岗位动作

### `POST /jobs/bookmark`

收藏岗位。

```json
{
  "platform": "boss",
  "job_id": "abc",
  "company": "示例科技",
  "title": "RAG 工程师",
  "note": "优先看"
}
```

### `POST /jobs/feedback`

保存岗位反馈。常用状态：`感兴趣`、`不合适`、`已拒绝`。

```json
{
  "platform": "boss",
  "job_id": "abc",
  "company": "示例科技",
  "title": "RAG 工程师",
  "status": "不合适",
  "note": "经验要求偏高"
}
```

### `POST /jobs/application`

保存投递或沟通状态。常用状态：`已投递`、`已沟通`、`面试中`。

```json
{
  "platform": "boss",
  "job_id": "abc",
  "company": "示例科技",
  "title": "RAG 工程师",
  "status": "已投递",
  "next_action": "等待回复"
}
```

### `GET /jobs/actions`

读取反馈、投递记录和状态摘要。

查询参数：

- `limit`：返回数量，默认 `100`，范围 `1-500`。

## 插件调用流程

浏览器插件在岗位详情页执行：

1. 读取当前标签页可见文本。
2. 用户检查岗位名称、公司、地点、薪资和 JD。
3. 点击“导入”调用 `POST /jobs/import`。
4. 点击“收藏”调用 `POST /jobs/bookmark`。

## 前端接入建议

独立前端启动后建议按这个顺序调用：

1. `GET /meta/capabilities`
2. `GET /meta/platforms`
3. `GET /jobs`
4. `POST /jobs/search` 或 `POST /jobs/import`
5. `POST /jobs/match`
6. `POST /jobs/bookmark` / `POST /jobs/feedback` / `POST /jobs/application`
7. `GET /jobs/actions`
