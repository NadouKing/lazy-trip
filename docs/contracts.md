# 数据合同

JSON 使用 UTF-8，时间为含时区的 ISO8601。金额为元、路线距离为米、耗时为秒，停留为分钟。

## 需求

必填 city、area、origin.name、date(YYYY-MM-DD)、startTime/endTime(HH:mm)、budgetYuan（全组）、maxWalkingMeters。默认 people=1、mode=walking、bufferMinutes=10、maxStops=3、timezone=Asia/Shanghai。最多20人、4站、当天返回；overnight=true 拒绝。

`research.queries` 可给最多三个搜索策略，每项 keyword/sort；美食也放在小红书 keyword 中，旧 `research.foodKeyword` 不再触发其他平台查询。不含个人默认地址。

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
```

小红书结果约定：envelope 为 schemaVersion/status/source/fetchedAt/method/elapsedMs/data；搜索 data.items/count/hasMore。会话 data.state=ready/login_required/verification_required，data.authenticated 为 bool。会话可用不保证每篇笔记可读；遇验证停止小红书后续请求。

| 合同归属 | 小红书 |
| --- | --- |
| 工具拥有的查询参数 | `sort`、`xsec_token`、`comment_limit` |
| 工具拥有的详情字段 | 笔记、正文、一级评论样本与范围 |
| Trip 拥有的适配 | `normalize_note` 生成 `xhs:` 证据、限定正文/评论与公开脱敏 |

小红书库和 CLI 可独立安装使用；Trip 直接 import，由本仓承担兼容与业务适配。点评的库、参数和适配已移除。官方高德详情可能包含评分、人均和营业时间，宿主 AI 保留查询时刻、原始字段与缺失状态；评分不代表已经读取完整评论。

CLI 错误是 `{"error":{"code":"...","message":"..."}}`，不输出请求头、Cookie、签名 URL 或完整堆栈。research 部分失败写 errors，其他证据继续保存。stderr 仅进度提示。

Trip 显式适配工具的已知错误码，保留登录/验证、超时、解析未知和身份不符的区别，消息使用本仓安全文本；不转发原始异常。某来源出现登录或人工验证门禁后停止该来源的后续查询，其他来源与已取得证据保留。未知错误仍使用 `source_error`，不把任意异常字段视作可信公开文本。
