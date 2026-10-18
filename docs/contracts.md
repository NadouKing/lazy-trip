# 数据合同

JSON 使用 UTF-8，时间为含时区的 ISO8601。金额为元、路线距离为米、耗时为秒，停留为分钟。

## 需求

必填 city、area、origin.name、date(YYYY-MM-DD)、startTime/endTime(HH:mm)、budgetYuan（全组）、maxWalkingMeters。默认 people=1、mode=walking、bufferMinutes=10、maxStops=3、timezone=Asia/Shanghai。最多20人、4站、当天返回；overnight=true 拒绝。

`research.queries` 可给最多三个搜索策略，每项 keyword/sort；`research.foodKeyword` 是点评查询关键词。不含个人默认地址。

## 候选与证据

`{"candidates":[...]}`。每项 id（唯一，不能为 origin）、name、kind(food/play)、environment(indoor/outdoor/mixed)、stayMinutes、insideWalkingMeters、evidenceIds。

可选 amapId（规划前必选）、costYuan:{min,max,basis}（每人）、openingHours、priority、reason、availability(open/closed/uncertain)、verificationPending、verificationNotes。

evidence.json 为 `{"evidence":[...]}`，每项需要唯一 id、source、sourceUrl、fetchedAt，笔记附 body/comments/commentSampleCount/commentScope。输出仅代表实际读取的文字样本，不含访问令牌；visualContentRead=false。

## 官方高德交接

CLI 不调用外部地图 API。宿主 AI 执行已配置官方 MCP：

```json
{"results":[{
  "id":"poi:origin",
  "tool":"maps_search_detail",
  "arguments":{"id":"调用任务中选定的真实POI ID"},
  "receivedAt":"2026-10-18T12:00:00Z",
  "result":{"这里保存实际工具返回":"不得用此占位内容运行真实规划"}
}]}
```

上例仅结构说明。result 支持 JSON 对象、MCP structuredContent、MCP content 中的 JSON 文本。保留命名空间前缀也可，末尾需匹配 maps_search_detail/maps_weather/maps_direction_*。不要自编价格、坐标或路线。CLI 做结构和一致性校验，不能密码学证明回执来自高德。

索引：weather、poi:origin、poi:候选id、route:起点id:终点id。起点保留 id=origin。所有有向路段分别查询；公交方向参数带 city/cityd。

## Python 工具调用

```python
async with XiaohongshuClient(profile_dir=..., chrome_path=..., headless=True) as xhs:
    search = await xhs.search(keyword, limit=20, sort="综合")
    note = await xhs.detail(note_id, xsec_token=token, comment_limit=20)
async with DianpingClient(profile_dir=..., chrome_path=..., headless=True) as dp:
    search = await dp.search(keyword, city=city, limit=5)
    shop = await dp.detail(shop_id)
```

统一 envelope：schemaVersion/status/source/fetchedAt/method/elapsedMs/data；搜索 data.items/count/hasMore。会话 data.state=ready/login_required/verification_required，data.authenticated 为 bool。主仓保留平台详情字段，不会把 reviewsStatus=not_visible_on_page 变成“没有差评”。

CLI 错误是 `{"error":{"code":"...","message":"..."}}`，不输出请求头、Cookie、签名 URL 或完整堆栈。research 部分失败写 errors，其他证据继续保存。stderr 仅进度提示。
