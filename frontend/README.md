# CareerPilot Frontend

独立前端用于连接本地 CareerPilot API，覆盖岗位采集、手动导入、简历匹配和岗位动作记录。

## 启动

```powershell
cd frontend
npm.cmd install
npm.cmd run dev
```

默认访问：

```text
http://127.0.0.1:5173
```

后端默认地址：

```text
http://127.0.0.1:8000
```

如需修改后端地址：

```powershell
$env:VITE_API_BASE="http://127.0.0.1:8000"
npm.cmd run dev
```
