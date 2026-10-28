"""Wiki lifecycle tests: isolated tmp dirs, no live LLM/network or existing DB."""
import asyncio
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from services.published_wiki import PublishedWikiService
from wiki_tools.bundle import canonical, sha, read_bundle, page_path, render, validate
from wiki_tools.compiler import (ingest, compile_wiki, publish, rollback, review_candidate,
                                 refresh_official, registry, write_candidate)
from wiki_tools.seed import seed_bundle


@pytest.fixture
def corpus(tmp_path):
    work, published = tmp_path / "work", tmp_path / "published"
    ingest(work, "defaults", "小项目先完成核心流程，跨设备持久化需要数据库。", kind="note", origin="reviewed-note:defaults")
    ingest(work, "access", "每个资源检查归属；备份必须验证恢复。", kind="note", origin="reviewed-note:access")
    return work, published


def response_pages():
    return [
        {"id": "small-projects", "title": "小项目", "category": "topic", "summary": "先完成核心流程。",
         "body": "网站和数据库先支持核心流程，权限与恢复同时考虑。", "sources": ["defaults", "access"],
         "links": ["ownership"], "keywords": ["网站", "数据库"], "default": True,
         "confidence": "medium", "volatility": "warm"},
        {"id": "ownership", "title": "数据归属", "category": "concept", "summary": "每份数据有主人。",
         "body": "用户只能访问自己的资源，备份必须验证恢复。", "sources": ["access"],
         "links": ["small-projects"], "keywords": ["权限", "备份"], "default": False,
         "confidence": "high", "volatility": "cold"},
    ]


class Model:
    def __init__(self, pages=None, fail=False):
        self.pages = response_pages() if pages is None else pages
        self.fail = fail
        self.messages = []

    async def ainvoke(self, messages):
        self.messages = messages
        if self.fail:
            raise RuntimeError("model unavailable")
        return SimpleNamespace(content=json.dumps({"pages": self.pages}, ensure_ascii=False))


def compile_fixture(work, pages=None):
    return asyncio.run(compile_wiki(work, Model(pages), model_name="offline-test-model"))


def publish_fixture(work, published, digest):
    return publish(work, published, digest, reviewer="test-admin", confirm=digest)


def test_compile_review_publish_and_provenance(corpus):
    work, published = corpus
    model = Model()
    digest = asyncio.run(compile_wiki(work, model, model_name="offline-test"))
    assert not published.exists()
    supplied = json.loads(model.messages[1].content)
    assert {item["id"] for item in supplied} == {"defaults", "access"}
    bundle = review_candidate(work, digest)
    assert bundle["mode"] == "llm"
    assert "verified:" not in render(bundle["pages"][0], bundle)
    assert "[[ownership|" in render(bundle["pages"][0], bundle)
    publish_fixture(work, published, digest)
    service = PublishedWikiService(published, allow_seed=False)
    pack = asyncio.run(service.reference("网站需要权限"))
    assert pack["sources"][0]["release"] == digest
    assert pack["sources"][0]["sources"][0]["sha256"]
    assert {p["path"] for p in pack["sources"]} == {
        "wiki/topics/small-projects.md", "wiki/concepts/ownership.md"}
    assert service.stats()["backend"] == "llm-wiki"
    assert not service.stats()["vector_required"]
    assert not (published / "releases" / digest / "raw").exists()
    assert "reviewed_at" in service.search("网站")[0]


@pytest.mark.parametrize("bad", ["citation", "link", "path", "verified", "missing-source", "html"])
def test_invalid_generation_never_becomes_candidate(corpus, bad):
    work, published = corpus
    pages = response_pages()
    if bad == "citation": pages[0]["sources"] = ["made-up"]
    if bad == "link": pages[0]["links"] = ["made-up"]
    if bad == "path": pages[0]["id"] = "../../escape"
    if bad == "verified": pages[0]["verified"] = "2026-10-26"
    if bad == "missing-source": pages[0]["sources"] = ["access"]
    if bad == "html": pages[0]["body"] = '<script>do_bad()</script>'
    with pytest.raises(ValueError):
        compile_fixture(work, pages)
    assert not published.exists()
    assert not (work / "candidates").exists()


def test_model_failure_and_bad_confirmation_preserve_release(corpus):
    work, published = corpus
    digest = compile_fixture(work)
    publish_fixture(work, published, digest)
    before = (published / "current.json").read_bytes()
    with pytest.raises(RuntimeError):
        asyncio.run(compile_wiki(work, Model(fail=True), model_name="test"))
    with pytest.raises(ValueError):
        publish(work, published, digest, reviewer="test-admin", confirm="yes")
    with pytest.raises(ValueError):
        publish(work, published, digest, reviewer="", confirm=digest)
    assert (published / "current.json").read_bytes() == before


@pytest.mark.parametrize("target", ["bundle", "page", "raw"])
def test_candidate_tampering_rejected(corpus, target):
    work, published = corpus
    digest = compile_fixture(work)
    bundle = review_candidate(work, digest)
    root = work / "candidates" / digest
    file = root / ({"bundle": "bundle.json", "page": page_path(bundle["pages"][0]),
                    "raw": next(iter(bundle["sources"].values()))["path"]}[target])
    file.write_text("{}", encoding="utf-8")
    with pytest.raises((ValueError, KeyError)):
        publish_fixture(work, published, digest)
    assert not (published / "current.json").exists()


def test_release_hot_reload_rollback_and_cold_fallback(corpus):
    work, published = corpus
    first = compile_fixture(work)
    publish_fixture(work, published, first)
    service = PublishedWikiService(published, allow_seed=False)
    pages = response_pages()
    pages[0]["body"] = "第二版本新增明确的验收说明。"
    second = compile_fixture(work, pages)
    publish_fixture(work, published, second)
    assert service.stats()["release"] == second
    assert "第二版本" in asyncio.run(service.reference("网站"))["context"]
    rollback(published, first, reviewer="test-admin", confirm=first)
    assert service.stats()["release"] == first
    publish_fixture(work, published, second)
    (published / "releases" / second / "bundle.json").write_text("{}")
    assert service.stats()["release"] == first
    assert service.stats()["degraded"]
    restarted = PublishedWikiService(published, allow_seed=False)
    assert restarted.stats()["release"] == first
    assert restarted.stats()["degraded"]
    assert asyncio.run(restarted.reference("网站"))["unverified"]


def test_broken_pointer_keeps_memory_but_fails_cold(corpus):
    work, published = corpus
    digest = compile_fixture(work)
    publish_fixture(work, published, digest)
    service = PublishedWikiService(published, allow_seed=False)
    (published / "current.json").write_text("broken")
    assert service.stats()["degraded"]
    with pytest.raises(ValueError):
        PublishedWikiService(published, allow_seed=False)


def test_first_install_seed_is_explicit_and_can_be_disabled(tmp_path):
    root = Path(__file__).resolve().parents[1] / "wiki"
    service = PublishedWikiService(tmp_path / "empty", seed_root=root)
    assert service.stats()["mode"] == "maintainer-seed"
    assert not service.stats()["published"]
    with pytest.raises(ValueError):
        PublishedWikiService(tmp_path / "empty", seed_root=root, allow_seed=False)


def test_seed_candidate_can_be_reviewed_and_published(tmp_path):
    bundle, raw = seed_bundle(Path(__file__).resolve().parents[1] / "wiki")
    work, published = tmp_path / "work", tmp_path / "published"
    digest = write_candidate(work, bundle, raw)
    publish_fixture(work, published, digest)
    assert PublishedWikiService(published, allow_seed=False).stats()["mode"] == "maintainer-seed"


def test_source_updates_immutable_and_no_query_network(corpus, monkeypatch):
    work, published = corpus
    transport = httpx.MockTransport(lambda req: httpx.Response(200, headers={"content-type": "text/html"},
                                                               text="<h1>Python release</h1><script>secret()</script>"))
    source = asyncio.run(refresh_official(work, "python", transport=transport))
    assert "secret" not in (work / source["path"]).read_text()
    before = (work / "sources.json").read_bytes()
    for status in (302, 500):
        bad = httpx.MockTransport(lambda req: httpx.Response(status))
        with pytest.raises(ValueError):
            asyncio.run(refresh_official(work, "python", transport=bad))
        assert (work / "sources.json").read_bytes() == before
    updated = ingest(work, "python", "New official content", kind="official", origin=source["origin"])
    assert updated["path"] != source["path"] and (work / source["path"]).exists()
    # Select only the seed notes for this deterministic fixture.
    digest = asyncio.run(compile_wiki(work, Model(), model_name="test", source_ids=["defaults", "access"]))
    publish_fixture(work, published, digest)
    def forbidden(*args, **kwargs):
        raise AssertionError("Online reader must not use HTTP")
    monkeypatch.setattr(httpx, "AsyncClient", forbidden)
    service = PublishedWikiService(published, allow_seed=False)
    assert asyncio.run(service.reference("最新 Python version 价格"))["unverified"]


@pytest.mark.parametrize("kind", ["oversized", "timeout", "type"])
def test_official_failures_do_not_write_registry(corpus, kind):
    work, _ = corpus
    def fetch(req):
        if kind == "timeout": raise httpx.ReadTimeout("timeout")
        return httpx.Response(200, headers={"content-type": "image/png" if kind == "type" else "text/plain"},
                              text="x" * 256001)
    before = (work / "sources.json").read_bytes()
    with pytest.raises((ValueError, httpx.ReadTimeout)):
        asyncio.run(refresh_official(work, "python", transport=httpx.MockTransport(fetch)))
    assert (work / "sources.json").read_bytes() == before


def test_path_and_symlink_escape(corpus, tmp_path):
    work, published = corpus
    digest = compile_fixture(work)
    bundle = review_candidate(work, digest)
    page = work / "candidates" / digest / page_path(bundle["pages"][0])
    outside = tmp_path / "outside.md"
    outside.write_bytes(page.read_bytes())
    page.unlink()
    page.symlink_to(outside)
    with pytest.raises(ValueError):
        publish_fixture(work, published, digest)
    with pytest.raises(ValueError):
        review_candidate(work, "../outside")
    with pytest.raises(ValueError):
        rollback(published, "../outside", reviewer="test-admin", confirm="../outside")


def test_context_pack_bounded_and_deterministic(corpus):
    work, published = corpus
    pages = response_pages()
    for page in pages:
        page["body"] = "可验证的参考知识。" * 800
    # Add large related pages, each valid but collectively bigger than the pack.
    for i in range(2):
        p = deepcopy(pages[0])
        p["id"] = f"extra-{i}"
        p["links"] = ["small-projects"]
        pages[0]["links"].append(p["id"])
        pages.append(p)
    digest = compile_fixture(work, pages)
    publish_fixture(work, published, digest)
    service = PublishedWikiService(published, allow_seed=False)
    first = asyncio.run(service.reference("网站"))
    assert len(first["context"]) <= 18_000
    assert first == asyncio.run(service.reference("网站"))
    assert "[页面节选已截断]" in first["context"]


def test_hash_source_corruption_rejected_before_model(corpus):
    work, _ = corpus
    source = registry(work)["defaults"]
    (work / source["path"]).write_text("changed")
    model = Model()
    with pytest.raises(ValueError):
        asyncio.run(compile_wiki(work, model, model_name="test"))
    assert not model.messages


def test_uncovered_selected_source_fails_and_prior_sources_not_silently_carried(corpus):
    work, _ = corpus
    ingest(work, "extra", "An explicitly selected additional source", kind="note", origin="curated:extra")
    with pytest.raises(ValueError, match="Uncovered"):
        compile_fixture(work)
    digest = asyncio.run(compile_wiki(work, Model(), model_name="test", source_ids=["defaults", "access"]))
    assert set(review_candidate(work, digest)["sources"]) == {"defaults", "access"}


def test_published_context_and_hashes_reach_real_planner_and_writer(corpus):
    from core.graph import create_graph
    from tests.test_planning_flow import Model as PlanningModel, initial_state
    work, published = corpus
    digest = compile_fixture(work)
    publish_fixture(work, published, digest)
    service = PublishedWikiService(published, allow_seed=False)
    class CapturingModel(PlanningModel):
        planner_prompt = ""

        async def ainvoke(self, messages):
            if "你是内部规划节点" in messages[0].content:
                self.planner_prompt = messages[0].content
            return await super().ainvoke(messages)
    model = CapturingModel()
    graph = create_graph(model=model, knowledge_service=service)
    result = asyncio.run(graph.ainvoke(initial_state()))
    assert result["delivery_validated"]
    references = result["plan"]["contract"]["references"]
    assert references[0]["release"] == digest
    assert references[0]["sources"][0]["sha256"]
    assert digest in model.planner_prompt
    assert digest in model.writer_prompts[0]
    assert "reviewed-note:" in model.writer_prompts[0]


def test_concurrent_publishers_leave_complete_pointer_chain(corpus):
    from concurrent.futures import ThreadPoolExecutor
    work, published = corpus
    first = compile_fixture(work)
    pages = response_pages()
    pages[0]["body"] = "Another complete candidate."
    second = compile_fixture(work, pages)
    with ThreadPoolExecutor(max_workers=2) as pool:
        jobs = [pool.submit(publish_fixture, work, published, d) for d in (first, second)]
        for job in jobs:
            job.result(timeout=10)
    pointer = json.loads((published / "current.json").read_bytes())
    assert {pointer["active"], pointer["previous"]} == {first, second}
    assert len(list((published / "history").glob("*.json"))) == 2
    assert not PublishedWikiService(published, allow_seed=False).stats()["degraded"]


def test_interrupted_publication_does_not_activate_partial_release(corpus, monkeypatch):
    from wiki_tools import compiler
    work, published = corpus
    first = compile_fixture(work)
    publish_fixture(work, published, first)
    pages = response_pages()
    pages[0]["body"] = "Another candidate."
    second = compile_fixture(work, pages)
    before = (published / "current.json").read_bytes()
    original = compiler.atomic_json

    def fail_pointer(path, value):
        if Path(path).name == "current.json":
            raise OSError("simulated disk error before pointer replacement")
        return original(path, value)
    monkeypatch.setattr(compiler, "atomic_json", fail_pointer)
    with pytest.raises(OSError):
        publish_fixture(work, published, second)
    assert (published / "current.json").read_bytes() == before
    assert PublishedWikiService(published, allow_seed=False).stats()["release"] == first


def test_raw_directory_never_needed_by_online_reader(corpus):
    import shutil
    work, published = corpus
    digest = compile_fixture(work)
    publish_fixture(work, published, digest)
    shutil.rmtree(work)
    service = PublishedWikiService(published, allow_seed=False)
    assert asyncio.run(service.reference("权限"))["sources"][0]["release"] == digest


def test_cli_lifecycle_and_failed_publish_exit(tmp_path):
    import subprocess
    import sys
    project = Path(__file__).resolve().parents[1]
    prefix = [sys.executable, "-m", "wiki_tools.cli", "--work", str(tmp_path / "work"),
              "--published", str(tmp_path / "published")]
    def call(*arguments):
        return subprocess.run(prefix + list(arguments), cwd=project, text=True, capture_output=True, timeout=15)
    initialized = call("init")
    assert initialized.returncode == 0, initialized.stderr
    candidate = call("seed-candidate")
    assert candidate.returncode == 0, candidate.stderr
    digest = json.loads(candidate.stdout)["candidate"]
    checked = call("check", digest)
    assert checked.returncode == 0
    assert json.loads(checked.stdout)["semantic_review"] == "required"
    failed = call("publish", digest, "--reviewer", "test-admin", "--confirm", "yes")
    assert failed.returncode != 0 and "Confirmation" in failed.stderr
    assert not (tmp_path / "published/current.json").exists()
    result = call("publish", digest, "--reviewer", "test-admin", "--confirm", digest)
    assert result.returncode == 0, result.stderr
    status = call("status")
    assert json.loads(status.stdout)["release"] == digest
    assert json.loads(status.stdout)["published"]
