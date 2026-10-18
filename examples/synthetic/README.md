# 合成离线示例

这些地点、路线、消费和来源是测试构造，不是小红书、点评或高德实测。日期只是固定夹具；即使时间碰巧未过，也不能拿去导航。amap-results.json 显式 synthetic=true，规划器会保留提示并降为 provisional。

在主仓环境中运行：

```powershell
uv run lazy-trip plan --request examples/synthetic/request.json --candidates examples/synthetic/candidates.json --maps examples/synthetic/amap-results.json --evidence examples/synthetic/evidence.json --out runtime/synthetic-report.json --html runtime/synthetic-itinerary.html
```

真实采集结果应留在自己的 ignored runtime 目录，公开仓不复制整篇用户笔记、评论、Cookie或签名访问令牌。
