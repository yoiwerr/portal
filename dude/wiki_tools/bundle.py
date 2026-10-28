"""Bounded, content-addressed Wiki format shared by compiler and read-only runtime.

Inspired by nvk/llm-wiki's source-backed, linked articles; intentionally a small
dude adapter, not an implementation of the entire upstream plugin protocol.
"""
import hashlib
import json
from pathlib import Path
import re

UPSTREAM = "https://github.com/nvk/llm-wiki/tree/d60674ff785e5c6d35322657d7839a7c0bdd3ca7"
SCHEMA = 1
SLUG = re.compile(r"[a-z][a-z0-9-]{0,59}\Z")
DIGEST = re.compile(r"[a-f0-9]{64}\Z")
CATEGORIES = {"concept": "concepts", "topic": "topics", "reference": "references"}


class WikiValidationError(ValueError):
    """Safe local diagnostic without provider bodies, credentials or source text."""


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def require(condition, message):
    if not condition:
        raise WikiValidationError(message)


def text_field(value, limit):
    return isinstance(value, str) and 0 < len(value.strip()) <= limit and "\x00" not in value


def validate(bundle):
    require(isinstance(bundle, dict) and bundle.get("schema") == SCHEMA, "Unsupported Wiki schema")
    require(len(canonical(bundle)) <= 256_000, "Wiki bundle exceeds limit")
    require(bundle.get("mode") in ("llm", "maintainer-seed"), "Invalid compilation mode")
    for key in ("created_at", "compiler", "model", "upstream"):
        require(text_field(bundle.get(key), 300), f"Missing {key}")
    sources, pages = bundle.get("sources"), bundle.get("pages")
    require(isinstance(sources, dict) and 1 <= len(sources) <= 24, "Expected 1–24 sources")
    require(isinstance(pages, list) and 2 <= len(pages) <= 16, "Expected 2–16 linked pages")
    for name, source in sources.items():
        require(bool(SLUG.fullmatch(name)) and isinstance(source, dict), "Invalid source ID")
        require(bool(DIGEST.fullmatch(source.get("sha256", ""))), "Invalid source hash")
        require(source.get("kind") in ("note", "official"), "Unapproved source kind")
        for key in ("origin", "captured_at", "path"):
            require(text_field(source.get(key), 400), f"Missing source {key}")
        expected = f"raw/{'notes' if source['kind'] == 'note' else 'articles'}/{name}-{source['sha256']}.md"
        require(source["path"] == expected, "Source path must be content-addressed")
    ids = [p.get("id") for p in pages if isinstance(p, dict)]
    require(len(ids) == len(pages) and all(isinstance(x, str) and SLUG.fullmatch(x) for x in ids)
            and len(set(ids)) == len(ids), "Invalid or duplicate page ID")
    covered = set()
    for page in pages:
        require(page.get("category") in CATEGORIES, "Invalid category")
        for key, limit in (("title", 120), ("summary", 600), ("body", 8000)):
            require(text_field(page.get(key), limit), f"Invalid page {key}")
        require(page.get("confidence") in ("high", "medium-high", "medium", "medium-low", "low"), "Invalid confidence")
        require(page.get("volatility") in ("hot", "warm", "cold"), "Invalid volatility")
        require("verified" not in page, "Compilation must not claim human verification")
        for key in ("sources", "links", "keywords"):
            values = page.get(key)
            require(isinstance(values, list) and 1 <= len(values) <= 24
                    and all(text_field(v, 100) for v in values)
                    and len(values) == len(set(values)), f"Invalid page {key}")
        require(set(page["sources"]) <= sources.keys(), "Unknown source citation")
        require(set(page["links"]) <= set(ids) - {page["id"]}, "Broken or self Wiki link")
        require(isinstance(page.get("default"), bool), "default must be boolean")
        # Links are renderer-owned, so generated text cannot hide uncatalogued citations.
        require(not re.search(r"\]\(|\[\[|<\s*(?:script|iframe|img)\b", page["body"], re.I),
                "Put citations/links in structured fields, not body")
        covered.update(page["sources"])
    require(covered == sources.keys(), "Uncovered source; explicitly remove it from selection or cite it")
    require(any(p["default"] for p in pages), "At least one default page is required")
    by_id = {p["id"]: p for p in pages}
    for page in pages:
        require(all(page["id"] in by_id[other]["links"] for other in page["links"]), "Links must be bidirectional")
    return bundle


def page_path(page):
    return f"wiki/{CATEGORIES[page['category']]}/{page['id']}.md"


def render(page, bundle):
    # JSON scalars are valid YAML scalars; no YAML parser/dependency is needed.
    scalar = lambda value: json.dumps(value, ensure_ascii=False)
    lines = ["---", f"title: {scalar(page['title'])}", f"category: {page['category']}", "sources:"]
    lines += [f"  - {scalar(bundle['sources'][key]['path'])}" for key in page["sources"]]
    lines += [f"updated: {scalar(bundle['created_at'][:10])}", f"confidence: {page['confidence']}",
              f"volatility: {page['volatility']}", f"summary: {scalar(page['summary'])}", "---",
              "", f"# {page['title']}", "", f"> {page['summary']}", "", page["body"], "", "## See Also", ""]
    by_id = {p["id"]: p for p in bundle["pages"]}
    for key in page["links"]:
        target = by_id[key]
        lines.append(f"- [[{key}|{target['title']}]] ([{target['title']}](../{CATEGORIES[target['category']]}/{key}.md))")
    lines += ["", "## Sources", ""]
    lines += [f"- [{key}](../../{bundle['sources'][key]['path']})" for key in page["sources"]]
    return "\n".join(lines) + "\n"


def contained_file(root, name, limit=256_000):
    root = Path(root).resolve()
    relative = Path(name)
    require(not relative.is_absolute() and ".." not in relative.parts, "Unsafe Wiki path")
    path = root / relative
    require(not any(p.is_symlink() for p in [path, *path.parents] if p != root and p.is_relative_to(root)),
            "Wiki symlinks are not allowed")
    require(path.resolve().is_relative_to(root) and path.is_file(), "Missing or escaping Wiki file")
    require(path.stat().st_size <= limit, "Wiki file exceeds limit")
    return path.read_bytes()


def read_bundle(root, digest):
    require(isinstance(digest, str) and bool(DIGEST.fullmatch(digest)), "Invalid release digest")
    root = Path(root)
    require(not root.is_symlink(), "Release cannot be a symlink")
    data = contained_file(root, "bundle.json")
    bundle = validate(json.loads(data))
    require(sha(canonical(bundle)) == digest, "Release digest mismatch")
    for page in bundle["pages"]:
        require(contained_file(root, page_path(page), 40_000).decode("utf-8") == render(page, bundle),
                "Rendered page differs from reviewed bundle")
    return bundle
