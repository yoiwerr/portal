"""Linux/WSL administrator entrypoint: python -m wiki_tools.cli --help."""
import argparse
import asyncio
import json
import os
from pathlib import Path
import sys

from wiki_tools.bundle import SLUG, contained_file, require, WikiValidationError
from wiki_tools.compiler import (ingest, refresh_official, compile_wiki, write_candidate,
                                 review_candidate, publish, rollback, OFFICIAL)
from wiki_tools.seed import seed_bundle

PROJECT = Path(__file__).resolve().parent.parent


def parser():
    p = argparse.ArgumentParser(description="dude LLM Wiki: admin compilation, review, publish and rollback")
    p.add_argument("--work", type=Path, default=PROJECT / "var/wiki-work")
    p.add_argument("--published", type=Path, default=PROJECT / "var/wiki-published")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("init", help="Snapshot the two bundled maintainer notes; no model or publication")
    note = sub.add_parser("ingest-note", help="Snapshot reviewed wiki_sources/notes/ID.md only")
    note.add_argument("id")
    refresh = sub.add_parser("refresh", help="Fetch one allowlisted official source; does not publish")
    refresh.add_argument("id", choices=sorted(OFFICIAL))
    compile_parser = sub.add_parser("compile", help="Call configured chat model; write candidate only")
    compile_parser.add_argument("--source", action="append", help="Select source ID; repeat. Default: all current sources")
    sub.add_parser("seed-candidate", help="Create explicitly labelled maintainer seed candidate without an LLM")
    check = sub.add_parser("check", help="Verify candidate and raw hashes; print review paths")
    check.add_argument("digest")
    for action in ("publish", "rollback"):
        ap = sub.add_parser(action)
        ap.add_argument("digest")
        ap.add_argument("--reviewer", required=True)
        ap.add_argument("--confirm", required=True, help="Repeat the complete reviewed digest")
    sub.add_parser("status", help="Read published status; never load model or database")
    return p


async def run(args):
    work, published = args.work.resolve(), args.published.resolve()
    require(not work.is_relative_to(published) and not published.is_relative_to(work),
            "Admin work and published directories must be separate")
    if args.command == "init":
        bundle, raw = seed_bundle(PROJECT / "wiki")
        for key, source in bundle["sources"].items():
            ingest(work, key, raw[key].decode(), kind="note", origin=source["origin"])
        return {"work": str(work), "sources": list(raw), "published": False}
    if args.command == "ingest-note":
        require(bool(SLUG.fullmatch(args.id)), "Note ID must be a simple slug")
        text = contained_file(PROJECT / "wiki_sources/notes", f"{args.id}.md", 64_000).decode("utf-8")
        return ingest(work, args.id, text, kind="note", origin=f"curated-note:wiki_sources/notes/{args.id}.md")
    if args.command == "refresh":
        return await refresh_official(work, args.id)
    if args.command == "compile":
        # Only this command loads secret model settings; no keys or response errors are printed.
        from config import config
        from core.llm_client import create_model
        model = create_model(config)
        name = getattr(model, "model_name", None) or getattr(model, "model", None) or config.llm_model
        digest = await compile_wiki(work, model, model_name=str(name), source_ids=args.source)
        return {"candidate": digest, "path": str(work / "candidates" / digest), "published": False}
    if args.command == "seed-candidate":
        bundle, raw = seed_bundle(PROJECT / "wiki")
        return {"candidate": write_candidate(work, bundle, raw), "mode": "maintainer-seed", "published": False}
    if args.command == "check":
        bundle = review_candidate(work, args.digest)
        return {"digest": args.digest, "structural_checks": "passed", "semantic_review": "required",
                "pages": len(bundle["pages"]), "sources": len(bundle["sources"]),
                "review_directory": str(work / "candidates" / args.digest)}
    if args.command == "publish":
        return publish(work, published, args.digest, reviewer=args.reviewer, confirm=args.confirm)
    if args.command == "rollback":
        return rollback(published, args.digest, reviewer=args.reviewer, confirm=args.confirm)
    from services.published_wiki import PublishedWikiService
    return PublishedWikiService(published, seed_root=PROJECT / "wiki",
                                allow_seed=os.getenv("DUDE_WIKI_ALLOW_SEED", os.getenv("ALFRED_WIKI_ALLOW_SEED", "true")).lower() == "true").stats()


def main():
    args = parser().parse_args()
    try:
        result = asyncio.run(run(args))
    except Exception as error:
        # Provider exceptions can include URLs, response bodies and authentication data.
        # Validation errors from our code are safe; model/provider text is never emitted.
        detail = str(error) if isinstance(error, WikiValidationError) else type(error).__name__
        print(f"Wiki {args.command} failed: {detail}. "
              "Check inputs/configuration; after a publication error, inspect status before retrying.", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
