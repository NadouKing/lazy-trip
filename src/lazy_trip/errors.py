"""Stable errors suitable for JSON CLI output, without request details or credentials."""


class TripError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


def public_error(error: Exception) -> dict:
    if isinstance(error, TripError):
        return {"code": error.code, "message": error.message}
    code = getattr(error, "code", "internal_error")
    # Browser/HTTP exceptions can embed complete signed URLs or profile paths.
    # Only translate known error codes; never dump arbitrary exception text.
    messages = {
        "login_required": "平台尚未登录，请先用平台工具登录。",
        "auth_required": "平台尚未登录，请先用平台工具登录。",
        "authentication_required": "平台尚未登录，请先用平台工具登录。",
        "verification_required": "平台要求人工验证，请在自己的浏览器中完成。",
        "profile_in_use": "专用浏览器目录正被其他进程使用，请先关闭对应会话。",
        "profile_locked": "专用浏览器目录正被其他进程使用，请先关闭对应会话。",
        "profile_busy": "专用浏览器目录正被其他进程使用，请先关闭对应会话。",
        "browser_not_found": "未找到 Chrome，请使用 --chrome 指定路径。",
        "chrome_not_found": "未找到 Chrome，请使用 --chrome 指定路径。",
        "timeout": "平台查询超时，已保留取得的其他证据。",
        "cdp_timeout": "平台浏览器操作超时，已保留取得的其他证据。",
        "navigation_timeout": "平台页面加载超时，已保留取得的其他证据。",
        "browser_timeout": "平台浏览器启动超时，已保留取得的其他证据。",
        "parse_error": "页面结构未能解析，需检查平台适配器。",
        "parsing_failed": "页面结构未能解析，需检查平台适配器。",
        "parser_unavailable": "平台页面结构未识别，不能当作空结果。",
        "page_data_unavailable": "平台页面未返回预期数据，请检查会话或页面适配。",
        "shop_identity_mismatch": "返回门店与请求不一致，未作为有效证据保存。",
        "note_unavailable": "笔记当前不可访问，未作为有效证据保存。",
        "session_unknown": "平台未提供可确认的会话状态。",
        "sort_refresh_timeout": "平台排序结果未确认刷新，未作为有效证据保存。",
    }
    return {"code": code if code in messages else "source_error",
            "message": messages.get(code, "查询未完成，已保留其他证据；请单独检查平台工具。")}
