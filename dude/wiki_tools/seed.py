"""Explicit human-maintained bootstrap. Never presented as an LLM compilation."""
from wiki_tools.bundle import SCHEMA, UPSTREAM, contained_file, sha, validate

SEED_PAGES = (
    ("defaults", "小规模新项目的默认方案", ["默认", "技术", "网站", "数据库", "部署"]),
    ("access-and-data", "访问、数据与费用的取舍", ["权限", "账号", "备份", "费用", "手机"]),
)


def seed_bundle(root):
    sources, pages, raw = {}, [], {}
    for key, title, keywords in SEED_PAGES:
        data = contained_file(root, f"{key}.md", 64_000)
        digest = sha(data)
        sources[key] = {"kind": "note", "origin": f"bundled-maintainer-note:wiki/{key}.md",
                        "captured_at": "2026-10-22", "sha256": digest,
                        "path": f"raw/notes/{key}-{digest}.md"}
        raw[key] = data
        pages.append({"id": key, "title": title, "category": "topic", "summary": title,
                      "body": data.decode("utf-8"), "sources": [key],
                      "links": [other[0] for other in SEED_PAGES if other[0] != key],
                      "keywords": keywords, "default": True, "confidence": "medium", "volatility": "warm"})
    bundle = {"schema": SCHEMA, "mode": "maintainer-seed", "created_at": "2026-10-22",
              "compiler": "dude-wiki/1", "model": "none", "upstream": UPSTREAM,
              "sources": sources, "pages": pages}
    return validate(bundle), raw
