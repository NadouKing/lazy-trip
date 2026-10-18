import asyncio
import json

import pytest

from lazy_trip.cli import browser_options, main, parser
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


class Dp(Xhs):
    async def search(self, keyword, *, city, limit):
        return {"data": {"items": [{"id": "shop", "name": "餐馆"}]}}

    async def detail(self, identifier):
        return {"data": {"id": identifier, "name": "餐馆", "reviews": [],
                         "reviewsStatus": "not_visible_on_page"}}


def test_readable_comments_only_counted():
    note = normalize_note({"data": {"comments": [{"content": ""}, {"content": "可以去"}]}}
                          , {"id": "n"})
    assert note["loadedCommentCount"] == 2
    assert note["commentSampleCount"] == 1
    assert note["visualContentRead"] is False


def test_direct_library_contract_partial_sources_and_sanitized_disk(sample, tmp_path):
    Xhs.calls = []
    output = tmp_path / "evidence.json"
    result = asyncio.run(collect(sample["request"], out=output, xhs_factory=Xhs, dp_factory=Dp))
    assert len(result["evidence"]) == 2
    assert result["evidence"][0]["commentSampleCount"] == 1
    assert result["evidence"][1]["reviewsStatus"] == "not_visible_on_page"
    assert result["evidence"][1]["id"] == "dp:shop"
    assert result["evidence"][1]["shopId"] == "shop"
    assert len(result["excludedSearchItems"]) == 2
    assert Xhs.calls[:3] == ["search", "search", "detail"]
    assert "private-token" not in output.read_text(encoding="utf-8")
    assert "xsecToken" not in json.dumps(result)


def test_xhs_failure_still_gets_dianping(sample):
    class BadXhs(Xhs):
        async def __aenter__(self):
            raise RuntimeError("secret signed URL must not leak")

    result = asyncio.run(collect(sample["request"], xhs_factory=BadXhs, dp_factory=Dp))
    assert len(result["evidence"]) == 1
    assert result["evidence"][0]["source"] == "dianping"
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


def test_verification_stops_only_affected_source_and_retains_evidence(sample):
    calls = []

    class GateError(Exception):
        code = "verification_required"

    class GatedXhs(Xhs):
        async def search(self, *args, **kwargs):
            calls.append("xhs-search")
            raise GateError("private signed URL")

    result = asyncio.run(collect(sample["request"], xhs_factory=GatedXhs, dp_factory=Dp))
    assert calls == ["xhs-search"]
    assert result["errors"][0]["code"] == "verification_required"
    assert result["evidence"][0]["source"] == "dianping"

    class GatedDp(Dp):
        async def search(self, *args, **kwargs):
            return {"data": {"items": [{"id": "one"}, {"id": "two"}]}}

        async def detail(self, identifier):
            calls.append("dp-detail")
            raise GateError("private signed URL")

    calls.clear()
    result = asyncio.run(collect(sample["request"], xhs_factory=Xhs, dp_factory=GatedDp,
                                 shop_limit=2))
    assert calls == ["dp-detail"]
    assert len(result["evidence"]) == 1
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
    xhs, dp = browser_options(args)
    assert xhs["profile_dir"] == "xhs-profile"
    assert dp["profile_dir"] == "dp-profile"
    assert xhs["timeout"] == 20 and dp["timeout"] == 20
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
