# CareerPilot Browser Extension

这个目录是浏览器岗位导入插件雏形，用于把当前招聘页面的可见文本导入本地 CareerPilot API。

## 使用方式

1. 先启动 API：

```powershell
python api.py
```

2. 在 Chrome / Edge 打开扩展管理页，选择“加载解压缩的扩展”，目录选 `browser_extension`。
3. 打开一个岗位详情页，点击 CareerPilot 插件。
4. 检查岗位名称、公司、地点、薪资和 JD 文本。
5. 点击“导入”写入本地岗位库，或点击“收藏”先写入求职记忆。
6. 回到 Streamlit 工作台查看岗位结果。

插件只在用户点击时读取当前标签页文本，并发送到本地 API：

- `POST http://127.0.0.1:8000/jobs/import`
- `POST http://127.0.0.1:8000/jobs/bookmark`
