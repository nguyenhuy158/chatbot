#!/usr/bin/env python
"""CLI to bulk-ingest documents from a directory.

Usage:
    python scripts/ingest.py --dir ./docs --collection faq --owner you@example.com
"""
import argparse
import asyncio
from pathlib import Path
from uuid import UUID

from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.rag import ingest_file


async def main(args: argparse.Namespace) -> None:
    root = Path(args.dir).resolve()
    if not root.is_dir():
        raise SystemExit(f"Not a directory: {root}")

    tenant_id = UUID(args.tenant) if args.tenant else settings.DEFAULT_TENANT_ID
    files = sorted(p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in {
        ".pdf", ".docx", ".md", ".txt", ".html"
    })
    print(f"Found {len(files)} files in {root}")

    ok = 0
    for path in files:
        try:
            async with AsyncSessionLocal() as db:
                doc = await ingest_file(
                    db=db,
                    path=path,
                    tenant_id=tenant_id,
                    collection=args.collection,
                    owner_email=args.owner,
                    source_url=str(path),
                )
                await db.commit()
                print(f"  OK  {path.name} -> {doc.id}")
                ok += 1
        except Exception as e:
            print(f"  ERR {path.name}: {e}")

    print(f"\nIngested {ok}/{len(files)} files")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", required=True, help="Directory containing docs")
    parser.add_argument("--collection", required=True, help="Collection name")
    parser.add_argument("--owner", default=None, help="Owner email")
    parser.add_argument("--tenant", default=None, help="Tenant UUID (default: env)")
    args = parser.parse_args()

    asyncio.run(main(args))
