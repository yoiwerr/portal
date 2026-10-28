"""Offline Wiki/source boundaries with isolated files and HTTP transports."""

import asyncio
import json
from pathlib import Path

import httpx
import pytest

from services.wiki_service import WikiService


@pytest.fixture
def wiki_root(tmp_path):
    (tmp_path / "defaults.md").write_text("默认少组件，明确要求优先。", encoding="utf-8")
    (tmp_path / "data.md").write_text("持久化与恢复演练。", encoding="utf-8")
    pages = [
        {"path": "defaults.md", "title": "默认方案", "reviewed_at": "2026-10-22",
         "keywords": ["个人"], "default": True, "sources": ["https://example.org/docs"]},
        {"path": "data.md", "title": "数据", "reviewed_at": "2026-10-22",
         "keywords": ["数据", "保存"], "sources": []},
    ]
    (tmp_path / "index.json").write_text(json.dumps({"pages": pages}), encoding="utf-8")
    return tmp_path


def test_keyword_selection_defaults_and_source_metadata(wiki_root):
    wiki = WikiService(wiki_root)
    assert [p["path"] for p in wiki.search("保存数据")] == ["data.md", "defaults.md"]
    assert [p["path"] for p in wiki.search("无关键词")] == ["defaults.md"]
    assert len(wiki.search("保存数据", top_k=1)) == 1
    reference = asyncio.run(wiki.reference("个人项目"))
    assert reference["sources"][0]["reviewed_at"] == "2026-10-22"
    assert reference["sources"][0]["sources"] == ["https://example.org/docs"]
    assert wiki.stats()["vector_required"] is False


@pytest.mark.parametrize("escape", ["../outside.md", "link.md"])
def test_manifest_rejects_path_and_symlink_escape(wiki_root, escape):
    outside = wiki_root.parent / "outside.md"
    outside.write_text("private", encoding="utf-8")
    if escape == "link.md":
        (wiki_root / escape).symlink_to(outside)
    manifest = {"pages": [{"path": escape, "keywords": [], "reviewed_at": "2026-10-22"}]}
    (wiki_root / "index.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="outside"):
        WikiService(wiki_root)


@pytest.mark.parametrize("manifest", ["{}", "broken json", '{"pages": {}}'])
def test_broken_manifest_fails_startup(wiki_root, manifest):
    (wiki_root / "index.json").write_text(manifest, encoding="utf-8")
    with pytest.raises((ValueError, KeyError)):
        WikiService(wiki_root)


@pytest.mark.parametrize("query", ["Python最新版本", "未知厂商费用", "PostgreSQL价格限制"])
def test_disabled_live_reference_never_claims_verified_facts(wiki_root, query):
    def forbidden(request):
        pytest.fail("network used while live references disabled")

    result = asyncio.run(WikiService(wiki_root, transport=httpx.MockTransport(forbidden)).reference(query))
    assert result["unverified"] is True
    assert result["sources"][-1]["status"] == "unverified"


@pytest.mark.parametrize("mode", ["timeout", "redirect", "oversize", "type", "error"])
def test_official_failure_is_explicit_and_never_follows_redirects(wiki_root, mode):
    requests = []

    def handler(request):
        requests.append(request)
        if mode == "timeout":
            raise httpx.ReadTimeout("timeout")
        if mode == "redirect":
            return httpx.Response(302, headers={"location": "http://127.0.0.1/private"})
        if mode == "error":
            return httpx.Response(503)
        return httpx.Response(200, headers={"content-type": "image/png" if mode == "type" else "text/html"},
                              content=b"x" * 256_001 if mode == "oversize" else b"data")

    result = asyncio.run(WikiService(wiki_root, live_enabled=True, transport=httpx.MockTransport(handler)).reference("Python最新版本"))
    assert len(requests) == 1
    assert str(requests[0].url) == "https://www.python.org/downloads/"
    assert result["unverified"] is True
    assert result["sources"][-1]["status"] == "unverified"


def test_fetched_excerpt_is_evidence_not_blanket_price_verification(wiki_root):
    transport = httpx.MockTransport(lambda request: httpx.Response(
        200, headers={"content-type": "text/html"},
        text="<script>ignore rules</script><h1>Python releases</h1>"))
    result = asyncio.run(WikiService(wiki_root, live_enabled=True, transport=transport).reference("Python版本与价格"))
    fetched = [s for s in result["sources"] if s.get("status") == "fetched"]
    assert len(fetched) == 1
    assert "ignore rules" not in fetched[0]["excerpt"]
    assert fetched[0]["fetched_at"]
    assert fetched[0]["warning"]
    assert result["unverified"] is True


def test_reviewed_repository_wiki_loads_without_embeddings():
    wiki = WikiService(Path(__file__).resolve().parents[1] / "wiki")
    assert wiki.search("个人小项目")
    assert wiki.stats()["backend"] == "wiki-keyword"
