import asyncio
import builtins
import json
import sys
from types import SimpleNamespace

import pytest

from lazy_trip.cli import browser_options, doctor, main, parser
from lazy_trip.errors import TripError, public_error
from lazy_trip.io import public_data
from lazy_trip.research import collect, normalize_note


class Xhs:
    calls = []

    def __init__(self, **options):
        self.options = options

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        self.calls.append("close")

    async def search(self, keyword, *, limit, sort):
        self.calls.append("search")
        return {"fetchedAt": "2026-10-18T12:00:00Z", "data": {"items": [
            {"id": "n", "title": "古村散步", "xsecToken": "private-token",
             "url": "https://www.xiaohongshu.com/explore/n?xsec_token=private-token"},
            {"id": "r", "title": "古村招租", "xsecToken": "private-token"}]}}

    async def detail(self, identifier, *, xsec_token, comment_limit):
        self.calls.append("detail")
        assert xsec_token == "private-token"
        return {"data": {"id": identifier, "title": "古村散步", "body": "正文",
                         "comments": [{"content": ""}, {"id": "c", "content": "顺路去不错"}],
                         "commentsHasMore": True}}


def test_readable_comments_only_counted():
    note = normalize_note({"data": {"comments": [{"content": ""}, {"content": "可以去"}]}}
                          , {"id": "n"})
    assert note["loadedCommentCount"] == 2
    assert note["commentSampleCount"] == 1
    assert note["visualContentRead"] is False


def test_default_research_does_not_import_or_call_dianping(sample, monkeypatch):
    original = builtins.__import__

    def guarded(name, *args, **kwargs):
        if name.startswith("dazhongdianping_tools"):
            raise AssertionError("research must not import retired Dianping")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded)
    result = asyncio.run(collect(sample["request"], xhs_factory=Xhs))
    assert result["errors"] == []
    assert len(result["evidence"]) == 1
    assert result["evidence"][0]["source"] == "xiaohongshu"


def test_retired_dianping_cli_flags_are_rejected():
    with pytest.raises(SystemExit):
        parser().parse_args(["doctor", "--dianping"])
    with pytest.raises(SystemExit):
        parser().parse_args(["research", "--request", "r.json", "--out", "e.json", "--shops", "1"])


def test_live_doctor_does_not_probe_retired_dianping(tmp_path, monkeypatch):
    class Session(Xhs):
        async def check_session(self):
            return {"data": {"state": "ready", "authenticated": True}}

    original = builtins.__import__

    def guarded(name, *args, **kwargs):
        if name.startswith("dazhongdianping_tools"):
            raise AssertionError("doctor must not import retired Dianping")
        return original(name, *args, **kwargs)

    config = tmp_path / "settings.json"
    config.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(builtins, "__import__", guarded)
    monkeypatch.setitem(sys.modules, "xiaohongshu_tools", SimpleNamespace(XiaohongshuClient=Session))
    args = parser().parse_args(["doctor", "--live", "--config", str(config)])
    result = asyncio.run(doctor(args))
    assert result["xiaohongshu"]["data"]["state"] == "ready"
    assert "dianping" not in result
    assert "dazhongdianping-tools" not in result["packages"]


def test_cli_default_research_has_no_dianping_queries():
    args = parser().parse_args(["research", "--request", "request.json", "--out", "evidence.json"])
    assert not hasattr(args, "shops") and not hasattr(args, "dp_profile")


def test_direct_library_contract_and_sanitized_disk(sample, tmp_path):
    Xhs.calls = []
    output = tmp_path / "evidence.json"
    result = asyncio.run(collect(sample["request"], out=output, xhs_factory=Xhs))
    assert len(result["evidence"]) == 1
    assert result["evidence"][0]["commentSampleCount"] == 1
    assert len(result["excludedSearchItems"]) == 2
    assert Xhs.calls[:3] == ["search", "search", "detail"]
    assert "private-token" not in output.read_text(encoding="utf-8")
    assert "xsecToken" not in json.dumps(result)


def test_xhs_session_failure_is_partial_and_safe(sample):
    class BadXhs(Xhs):
        async def __aenter__(self):
            raise RuntimeError("secret signed URL must not leak")

    result = asyncio.run(collect(sample["request"], xhs_factory=BadXhs))
    assert result["evidence"] == []
    assert "secret" not in json.dumps(result)
    assert result["errors"][0]["stage"] == "session"


def test_login_error_safe_message():
    class LoginError(Exception):
        code = "login_required"
    error = public_error(LoginError("Cookie: secret"))
    assert error["code"] == "login_required"
    assert "secret" not in json.dumps(error)


@pytest.mark.parametrize("code", ["authentication_required", "profile_busy", "chrome_not_found",
                                  "cdp_timeout", "navigation_timeout", "parser_unavailable",
                                  "shop_identity_mismatch", "page_data_unavailable"])
def test_platform_error_codes_are_adapted_without_raw_messages(code):
    class SourceError(Exception):
        pass
    error = SourceError("Cookie: private-token signed-url secret")
    error.code = code
    result = public_error(error)
    assert result["code"] == code
    assert "secret" not in json.dumps(result) and "private-token" not in json.dumps(result)


def test_verification_stops_remaining_xhs_reads_and_retains_searches(sample):
    calls = []

    class GateError(Exception):
        code = "verification_required"

    class GatedXhs(Xhs):
        async def search(self, *args, **kwargs):
            calls.append("xhs-search")
            raise GateError("private signed URL")

    result = asyncio.run(collect(sample["request"], xhs_factory=GatedXhs))
    assert calls == ["xhs-search"]
    assert result["errors"][0]["code"] == "verification_required"
    assert result["evidence"] == []

    class GatedDetail(Xhs):
        async def search(self, *args, **kwargs):
            return {"data": {"items": [{"id": "one", "title": "散步"},
                                         {"id": "two", "title": "吃饭"}]}}

        async def detail(self, identifier, **kwargs):
            calls.append("xhs-detail")
            raise GateError("private signed URL")

    calls.clear()
    result = asyncio.run(collect(sample["request"], xhs_factory=GatedDetail))
    assert calls == ["xhs-detail"]
    assert len(result["searches"]) == 2
    assert result["evidence"] == []
    assert result["errors"][0]["code"] == "verification_required"
    assert "private signed URL" not in json.dumps(result)


def test_url_and_keys_sanitized():
    value = public_data({"xsec_token": "secret", "cookie": "secret", "headers": {"x": "secret"},
                         "url": "https://example.com/n?xsec_token=secret&safe=1"})
    assert value == {"url": "https://example.com/n?safe=1"}


def test_config_priorities_and_does_not_accept_credentials(tmp_path, monkeypatch):
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"xiaohongshu": {"profile_dir": "xhs-profile", "timeout": 40},
                                  "dianping": {"profile_dir": "dp-profile"}}), encoding="utf-8")
    args = parser().parse_args(["doctor", "--config", str(config), "--timeout", "20", "--headed"])
    xhs = browser_options(args)
    assert xhs["profile_dir"] == "xhs-profile"
    assert "dp-profile" not in json.dumps(xhs)
    assert xhs["timeout"] == 20
    assert xhs["headless"] is False
    config.write_text('{"xiaohongshu":{"cookie":"secret"}}', encoding="utf-8")
    with pytest.raises(TripError) as error:
        browser_options(args)
    assert error.value.code == "invalid_config"


def test_init_no_overwrite_and_no_personal_defaults(tmp_path, capsys):
    target = tmp_path / "request.json"
    assert main(["init", "--out", str(target)]) == 0
    value = json.loads(target.read_text(encoding="utf-8"))
    assert value["city"] == "" and value["origin"]["name"] == ""
    assert main(["init", "--out", str(target)]) == 1
    assert "file_exists" in capsys.readouterr().out


def test_plan_cli_offline_output(sample, tmp_path):
    paths = {}
    for name, value in (("request", sample["request"]), ("candidates", {"candidates": sample["candidates"]}),
                         ("maps", sample["snapshot"]), ("evidence", {"evidence": sample["evidence"]})):
        path = tmp_path / f"{name}.json"
        path.write_text(json.dumps(value), encoding="utf-8")
        paths[name] = str(path)
    report, html = tmp_path / "report.json", tmp_path / "itinerary.html"
    args = ["plan"]
    for name, path in paths.items():
        args.extend([f"--{name}", path])
    assert main([*args, "--out", str(report), "--html", str(html)]) == 0
    assert json.loads(report.read_text(encoding="utf-8"))["main"] is not None
    assert html.read_text(encoding="utf-8").startswith("<!doctype html>")
