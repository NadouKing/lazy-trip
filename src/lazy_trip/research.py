"""Read-only Xiaohongshu evidence; the host uses official Amap for merchant checks."""

from collections.abc import Callable

from .errors import TripError, public_error
from .io import now, public_data, public_url, write_json
from .request import validate_request

SESSION_GATES = {"login_required", "auth_required", "authentication_required", "verification_required"}


def normalize_note(result: dict, feed: dict, comment_limit: int = 20) -> dict:
    data = result.get("data", {})
    comments = data.get("comments", [])
    if not isinstance(comments, list):
        comments = []
    text_comments = [item for item in comments if isinstance(item, dict)
                     and isinstance(item.get("content"), str) and item["content"].strip()]
    text_comments = text_comments[:comment_limit]
    body = data.get("body") or ""
    if not isinstance(body, str):
        body = ""
    identifier = data.get("id", feed["id"])
    return public_data({"id": f"xhs:{identifier}", "noteId": identifier,
                        "source": "xiaohongshu", "sourceUrl": public_url(
                            data.get("url") or feed.get("url") or
                            f"https://www.xiaohongshu.com/explore/{identifier}"),
                        "title": data.get("title") or feed.get("title"),
                        "body": body[:12000], "bodyTruncated": len(body) > 12000,
                        "publishedAt": data.get("publishedAt"), "fetchedAt": result.get("fetchedAt"),
                        "comments": text_comments, "loadedCommentCount": len(comments),
                        "commentSampleCount": len(text_comments),
                        "commentsHasMore": data.get("commentsHasMore"),
                        "commentScope": data.get("commentScope") or
                        f"仅本次读取的最多 {comment_limit} 条文字评论，不代表完整评论区",
                        "visualContentRead": False, "method": result.get("method"),
                        "elapsedMs": result.get("elapsedMs")})


def _items(result: dict) -> list[dict]:
    data = result.get("data", {})
    if not isinstance(data, dict) or not isinstance(data.get("items"), list):
        raise TripError("invalid_source_result", "平台搜索未返回约定的 items 数组。")
    return data["items"]


async def collect(request: dict, *, out=None, note_limit: int = 4,
                  comment_limit: int = 20, progress: Callable[[str], None] | None = None,
                  xhs_options: dict | None = None, xhs_factory=None) -> dict:
    request = validate_request(request)
    if type(note_limit) is not int or not 1 <= note_limit <= 6 \
            or type(comment_limit) is not int or not 0 <= comment_limit <= 100:
        raise TripError("invalid_limit", "notes 限 1–6，comments 限 0–100。")
    if xhs_factory is None:
        from xiaohongshu_tools import XiaohongshuClient
        xhs_factory = XiaohongshuClient
    progress = progress or (lambda _: None)
    bundle = {"schemaVersion": 1, "collectedAt": now(), "request": public_data(request),
              "searches": [], "evidence": [], "errors": [], "excludedSearchItems": []}

    def persist():
        if out:
            write_json(out, bundle)

    research = request.get("research", {})
    queries = research.get("queries") or [
        {"keyword": f"{request['city']} {request['area']} 攻略", "sort": "最多收藏"},
        {"keyword": f"{request['city']} {request['area']} 避坑", "sort": "最新"},
    ]
    if not isinstance(queries, list) or any(not isinstance(query, dict) or
                                          not isinstance(query.get("keyword"), str) or
                                          not query["keyword"].strip() for query in queries):
        raise TripError("invalid_queries", "research.queries 需要带 keyword 的对象数组。")
    # Retain in-memory access tokens only for this process. Public evidence never includes them.
    seen, feeds = set(), []
    xhs_blocked = False
    import re
    try:
        async with xhs_factory(**(xhs_options or {})) as xhs:
            for query in queries[:3]:
                progress("小红书搜索")
                try:
                    result = await xhs.search(query["keyword"], limit=20,
                                              sort=query.get("sort", "综合"))
                    items = _items(result)
                    bundle["searches"].append(public_data({
                        "source": "xiaohongshu", "keyword": query["keyword"],
                        "sort": query.get("sort", "综合"), "fetchedAt": result.get("fetchedAt"),
                        "method": result.get("method"), "elapsedMs": result.get("elapsedMs"),
                        "results": items}))
                    for feed in items:
                        title = feed.get("title") or ""
                        if re.search("招租|出租|整租|户型|房源|寻鸟|出沙发|招聘", title):
                            bundle["excludedSearchItems"].append({"id": feed.get("id"),
                                "title": title, "reason": "标题显示租赁、招聘或非游玩信息"})
                        elif feed.get("id") and feed["id"] not in seen and title:
                            seen.add(feed["id"])
                            feeds.append(feed)
                except Exception as error:
                    bundle["errors"].append({"source": "xiaohongshu", "stage": "search",
                                             **public_error(error)})
                    xhs_blocked = getattr(error, "code", None) in SESSION_GATES
                persist()
                if xhs_blocked:
                    break
            for feed in ([] if xhs_blocked else feeds[:note_limit]):
                progress("读取小红书正文与评论样本")
                try:
                    result = await xhs.detail(feed["id"], xsec_token=feed.get("xsecToken"),
                                              comment_limit=comment_limit)
                    bundle["evidence"].append(normalize_note(result, feed, comment_limit))
                except Exception as error:
                    bundle["errors"].append({"source": "xiaohongshu", "stage": "detail",
                                             "noteId": feed["id"], **public_error(error)})
                    xhs_blocked = getattr(error, "code", None) in SESSION_GATES
                persist()
                if xhs_blocked:
                    break
    except Exception as error:
        bundle["errors"].append({"source": "xiaohongshu", "stage": "session", **public_error(error)})
    persist()
    bundle["completedAt"] = now()
    bundle = public_data(bundle)
    if out:
        write_json(out, bundle)
    return bundle
